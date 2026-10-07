"""Upload corpus/documents/*.pdf into the running API and wait for ingestion.

Uploads are accepted with 202 and ingested in a FastAPI background task
(extract -> chunk -> embed -> store), so this polls /documents until every
record settles. Serial by default: ingestion embeds on CPU and parallel
uploads just queue behind the same worker while making failures harder to read.

Expect 99 of 100 to reach `ready`. inspection_cert_scanned.pdf is image-only
and _extract_pdf raises on it by design — see document-spec.yaml, tier special.

    make db-up && make api          # in another terminal
    .venv/bin/python corpus/generate/ingest.py
"""
import pathlib, sys, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "corpus/documents"
API = "http://localhost:18001"


def poll_initial(c, attempts=10):
    for n in range(attempts):
        try:
            return c.get("/documents").json()
        except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            print(f"  API busy ({type(e).__name__}), retry {n+1}/{attempts} ...", flush=True)
            time.sleep(10)
    sys.exit("API never answered on the initial listing.")


def main(api=API):
    pdfs = sorted(DOCS.glob("*.pdf"))
    if not pdfs:
        sys.exit("no PDFs in corpus/documents — run corpus/render/render.py first")

    # Generous read timeout, and the poll retries rather than dying. MiniLM
    # holds the GIL while encoding and ingestion runs in a background task in
    # the same single-worker uvicorn process, so the whole API stops answering
    # for a minute or more at a time. That is expected, not a hang.
    timeout = httpx.Timeout(600.0, connect=10.0)
    with httpx.Client(base_url=api, timeout=timeout) as c:
        try:
            health = c.get("/health").json()
        except httpx.ConnectError:
            sys.exit(f"no API at {api} — start it with `make api`")
        print(f"api healthy: {health}\n")

        existing = {d["filename"] for d in poll_initial(c)}
        if existing:
            print(f"{len(existing)} document(s) already present; skipping those\n")

        sent = 0
        for p in pdfs:
            if p.name in existing:
                continue
            with p.open("rb") as fh:
                r = c.post("/documents", files={"file": (p.name, fh, "application/pdf")})
            if r.status_code != 202:
                print(f"  ! {p.name}: {r.status_code} {r.text[:90]}")
                continue
            sent += 1
            print(f"  [{sent:3}/{len(pdfs)}] {p.name}")
        print(f"\nuploaded {sent}; waiting for ingestion ...\n")

        def poll(attempts=10):
            for n in range(attempts):
                try:
                    return c.get("/documents").json()
                except (httpx.ReadTimeout, httpx.ConnectError,
                        httpx.RemoteProtocolError, httpx.ReadError) as e:
                    print(f"\n  API busy ({type(e).__name__}), retry {n+1}/{attempts} ...",
                          flush=True)
                    time.sleep(10)
            sys.exit("\nAPI never answered. Ingestion may still be running — "
                     "re-run this script, it skips what is already uploaded.")

        started = time.time()
        while True:
            docs = poll()
            by = {}
            for d in docs:
                by.setdefault(d["status"], []).append(d)
            pending = by.get("processing", [])
            line = "  ".join(f"{k}={len(v)}" for k, v in sorted(by.items()))
            print(f"\r  {line}   {time.time()-started:5.0f}s", end="", flush=True)
            if not pending:
                break
            time.sleep(3)

        print("\n")
        docs = poll()
        ready = [d for d in docs if d["status"] == "ready"]
        failed = [d for d in docs if d["status"] != "ready"]
        chunks = sum(d.get("chunk_count", 0) for d in ready)
        print(f"ready   : {len(ready)} documents, {chunks} chunks")
        for d in failed:
            print(f"failed  : {d['filename']} — {d.get('error','')[:70]}")
        print(f"\n{'INGESTION COMPLETE' if len(failed) <= 1 else 'UNEXPECTED FAILURES'}")
        return 0 if len(failed) <= 1 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else API))
