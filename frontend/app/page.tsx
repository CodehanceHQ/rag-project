"use client";

import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type DocumentRecord = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  stage: string;
  progress: number;
  character_count: number;
  chunk_count: number;
  vector_count: number;
  embedding_dimensions: number | null;
  raw_file_id: string;
  created_at: string;
  error?: string | null;
};

type Chunk = {
  id: string;
  chunk_index: number;
  page?: number;
  section?: string;
  content: string;
  embedding_dimensions: number;
  embedding_preview: number[];
};

type SearchResult = {
  id: string;
  document_id: string;
  filename: string;
  chunk_index: number;
  page?: number;
  section?: string;
  content: string;
  score: number;
  embedding_preview: number[];
};

type Health = {
  status: string;
  database: string;
  vector_index: string;
  embedding_model: string;
  embedding_dimensions: number;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json();
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function VectorPreview({ values }: { values: number[] }) {
  return (
    <code className="vector-preview">
      [{values.map((value) => value.toFixed(4)).join(", ")}{values.length ? ", …" : ""}]
    </code>
  );
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => documents.find((document) => document.id === selectedId) ?? null,
    [documents, selectedId],
  );

  const refresh = useCallback(async () => {
    try {
      const [healthResult, documentResult] = await Promise.all([
        api<Health>("/health"),
        api<DocumentRecord[]>("/documents"),
      ]);
      setHealth(healthResult);
      setDocuments(documentResult);
      setSelectedId((current) => current || documentResult[0]?.id || "");
    } catch (caught) {
      setHealth(null);
      setError(caught instanceof Error ? caught.message : "The API is unavailable.");
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 2500);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setChunks([]);
      return;
    }
    api<Chunk[]>(`/documents/${selectedId}/chunks?limit=6`)
      .then(setChunks)
      .catch(() => setChunks([]));
  }, [selectedId, selected?.status, selected?.chunk_count]);

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length) return;
    setUploading(true);
    setError("");
    try {
      for (const file of list) {
        const form = new FormData();
        form.append("file", file);
        const created = await api<DocumentRecord>("/documents", { method: "POST", body: form });
        setSelectedId(created.id);
      }
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    uploadFiles(event.dataTransfer.files);
  }

  function handleFileInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) uploadFiles(event.target.files);
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setError("");
    try {
      const response = await api<{ results: SearchResult[] }>("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          limit: 8,
          document_id: scope === "all" ? null : scope,
        }),
      });
      setResults(response.results);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand-mark">R</div>
        <div>
          <p className="eyebrow">LOCAL KNOWLEDGE WORKBENCH</p>
          <h1>RAG Studio</h1>
        </div>
        <div className={`connection ${health ? "online" : "offline"}`}>
          <span />
          {health ? `MongoDB ${health.vector_index}` : "API offline"}
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")} aria-label="Dismiss error">×</button>
        </div>
      )}

      <section className="hero">
        <div>
          <p className="kicker">Turn files into searchable knowledge</p>
          <h2>See every step from<br />raw document to vector.</h2>
          <p className="hero-copy">
            Drop in a document, inspect its extracted chunks and embeddings, then retrieve the most relevant passages in natural language.
          </p>
        </div>
        <div className="model-card">
          <span>EMBEDDING ENGINE</span>
          <strong>{health?.embedding_model.split("/").pop() ?? "Loading…"}</strong>
          <small>{health?.embedding_dimensions ?? 384} dimensions · runs locally</small>
        </div>
      </section>

      <section className="workspace-grid">
        <div className="left-column">
          <div
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" multiple onChange={handleFileInput} hidden />
            <div className="upload-icon">↥</div>
            <h3>{uploading ? "Uploading…" : "Drop documents here"}</h3>
            <p>or click to browse · up to 50 MB each</p>
            <small>PDF · DOCX · PPTX · XLSX · TXT · MD · CSV · JSON · HTML · source code</small>
          </div>

          <div className="panel documents-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">LIBRARY</p>
                <h3>Documents</h3>
              </div>
              <span className="count">{documents.length}</span>
            </div>
            <div className="document-list">
              {!documents.length && <p className="empty">Your stored documents will appear here.</p>}
              {documents.map((document) => (
                <button
                  key={document.id}
                  className={`document-row ${selectedId === document.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(document.id)}
                >
                  <span className="file-badge">{document.filename.split(".").pop()?.slice(0, 4).toUpperCase()}</span>
                  <span className="document-main">
                    <strong>{document.filename}</strong>
                    <small>{formatBytes(document.size_bytes)} · {document.chunk_count} chunks</small>
                  </span>
                  <span className={`status-pill ${document.status}`}>{document.stage}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="right-column">
          <div className="panel inspector">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">INGESTION INSPECTOR</p>
                <h3>{selected?.filename ?? "Select a document"}</h3>
              </div>
              {selected && (
                <a className="raw-link" href={`${API_URL}/documents/${selected.id}/raw`}>Download raw ↗</a>
              )}
            </div>

            {selected ? (
              <>
                <div className="progress-track"><span style={{ width: `${selected.progress}%` }} /></div>
                <div className="stage-grid">
                  {[
                    ["01", "Raw stored", 8],
                    ["02", "Text extracted", 40],
                    ["03", "Chunks created", 56],
                    ["04", "Vectors generated", 80],
                    ["05", "MongoDB indexed", 100],
                  ].map(([number, label, threshold]) => (
                    <div key={String(number)} className={selected.progress >= Number(threshold) ? "stage complete" : "stage"}>
                      <span>{number}</span><small>{label}</small>
                    </div>
                  ))}
                </div>
                {selected.error && <p className="inline-error">{selected.error}</p>}
                <div className="metrics">
                  <div><span>Raw file</span><strong>{formatBytes(selected.size_bytes)}</strong><small>GridFS · {selected.raw_file_id.slice(-8)}</small></div>
                  <div><span>Extracted</span><strong>{selected.character_count.toLocaleString()}</strong><small>characters</small></div>
                  <div><span>Vectors</span><strong>{selected.vector_count.toLocaleString()}</strong><small>{selected.embedding_dimensions ?? 384} dimensions each</small></div>
                </div>
                <div className="chunk-heading">
                  <strong>Stored chunk samples</strong>
                  <small>Text and vector preview from MongoDB</small>
                </div>
                <div className="chunk-list">
                  {!chunks.length && <p className="empty">Chunks appear here when vectorization completes.</p>}
                  {chunks.map((chunk) => (
                    <article className="chunk-card" key={chunk.id}>
                      <div className="chunk-meta">
                        <span>CHUNK {String(chunk.chunk_index + 1).padStart(3, "0")}</span>
                        <span>{chunk.page ? `PAGE ${chunk.page}` : chunk.section ?? "DOCUMENT"}</span>
                      </div>
                      <p>{chunk.content}</p>
                      <VectorPreview values={chunk.embedding_preview} />
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="empty large">Upload a document to inspect how it is stored.</p>
            )}
          </div>
        </div>
      </section>

      <section className="retrieval-section">
        <div className="retrieval-intro">
          <p className="eyebrow">SEMANTIC RETRIEVAL</p>
          <h2>Ask in your own words.</h2>
          <p>We embed your question and return the closest passages. Scores show semantic similarity—not keyword frequency.</p>
        </div>
        <form className="search-box" onSubmit={handleSearch}>
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="What does the document say about…?"
            rows={3}
          />
          <div className="search-controls">
            <select value={scope} onChange={(event) => setScope(event.target.value)} aria-label="Search scope">
              <option value="all">All ready documents</option>
              {documents.filter((document) => document.status === "ready").map((document) => (
                <option value={document.id} key={document.id}>{document.filename}</option>
              ))}
            </select>
            <button type="submit" disabled={searching || query.trim().length < 2}>
              {searching ? "Searching…" : "Retrieve passages →"}
            </button>
          </div>
        </form>

        <div className="results">
          {results.map((result, index) => (
            <article className="result-card" key={result.id}>
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="result-body">
                <div className="result-meta">
                  <strong>{result.filename}</strong>
                  <span>{result.page ? `Page ${result.page}` : result.section ?? `Chunk ${result.chunk_index + 1}`}</span>
                  <span className="score">{(result.score * 100).toFixed(1)}% match</span>
                </div>
                <p>{result.content}</p>
                <VectorPreview values={result.embedding_preview} />
              </div>
            </article>
          ))}
          {!results.length && <p className="empty result-empty">Retrieved passages will appear here with their source and similarity score.</p>}
        </div>
      </section>

      <footer>
        <span>LOCAL RAG STUDIO</span>
        <span>Raw files + vectors in MongoDB · Embeddings on device</span>
      </footer>
    </main>
  );
}

