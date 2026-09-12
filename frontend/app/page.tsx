"use client";

import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type DocumentRecord = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed" | "deleting" | "delete_failed";
  stage: string;
  progress: number;
  character_count: number;
  chunk_count: number;
  vector_count: number;
  embedding_dimensions: number | null;
  raw_file_id: string;
  created_at: string;
  error?: string | null;
  source_metadata: {
    record_id?: string;
    owner?: string;
    source_status?: string;
    effective_date?: string;
    superseded_date?: string;
  };
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
  vector_score?: number;
  text_score?: number;
  fused_score?: number;
  reranker_score?: number;
  signals: string[];
  record_id?: string;
  source_status: string;
  effective_date?: string;
  embedding_preview: number[];
};

type SearchResponse = {
  mode: "vector" | "hybrid";
  abstained: boolean;
  decision: "answer" | "abstain" | "clarify";
  message?: string | null;
  clarification?: {
    reason: string;
    question: string;
    options: Array<{ label: string; refined_query: string; evidence_ids: string[] }>;
  } | null;
  pipeline: {
    vector_candidates: number;
    text_candidates: number;
    fused_candidates: number;
    reranked_candidates: number;
    minimum_score?: number | null;
    top_reranker_score?: number | null;
    ambiguity_status: "not_applicable" | "not_configured" | "skipped" | "checked" | "error";
  };
  results: SearchResult[];
};

type EvaluationResponse = {
  passed: number;
  failed: number;
  total: number;
  duration_ms: number;
  cases: Array<{
    suite: string;
    id: string;
    question: string;
    expected_behavior: string;
    passed: boolean;
    detail: string;
    abstained: boolean;
    decision: string;
    ambiguity_status: string;
    top_results: Array<{ filename: string; score: number }>;
  }>;
};

type Health = {
  status: string;
  database: string;
  vector_index: string;
  text_index: string;
  embedding_model: string;
  embedding_dimensions: number;
  reranker_model: string;
  minimum_relevance_score: number;
  ambiguity_llm_configured: boolean;
  ambiguity_model: string;
};

type InspectorTab = "overview" | "chunks" | "storage";
type AppView = "documents" | "retrieve";

const ingestionStages = [
  ["Stored", 8],
  ["Extracted", 40],
  ["Chunked", 56],
  ["Embedded", 80],
  ["Indexed", 100],
] as const;

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

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function VectorPreview({ values }: { values: number[] }) {
  return (
    <code className="vector-preview">
      [{values.map((value) => value.toFixed(5)).join(", ")}{values.length ? ", …" : ""}]
    </code>
  );
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [searchMode, setSearchMode] = useState<"vector" | "hybrid">("hybrid");
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [searching, setSearching] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState("");
  const [activeView, setActiveView] = useState<AppView>("documents");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");
  const [expandedVectors, setExpandedVectors] = useState<Set<string>>(new Set());

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
      setSelectedId((current) =>
        current && documentResult.some((document) => document.id === current)
          ? current
          : documentResult[0]?.id || "",
      );
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
    api<Chunk[]>(`/documents/${selectedId}/chunks?limit=20`)
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
      setActiveView("documents");
      setInspectorTab("overview");
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

  async function performSearch(searchQuery: string) {
    if (searchQuery.trim().length < 2) return;
    setSearching(true);
    setError("");
    try {
      const response = await api<SearchResponse>("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: searchQuery.trim(),
          limit: 8,
          document_id: scope === "all" ? null : scope,
          mode: searchMode,
          include_superseded: includeSuperseded,
        }),
      });
      setResults(response.results);
      setSearchResponse(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    await performSearch(query);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError("");
    try {
      await api(`/documents/${deleteTarget.id}`, { method: "DELETE" });
      const remaining = documents.filter((document) => document.id !== deleteTarget.id);
      setDocuments(remaining);
      setResults((current) => current.filter((result) => result.document_id !== deleteTarget.id));
      if (selectedId === deleteTarget.id) {
        setSelectedId(remaining[0]?.id ?? "");
        setChunks([]);
      }
      setDeleteTarget(null);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Deletion failed.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleEvaluation() {
    setEvaluating(true);
    setError("");
    try {
      const response = await api<EvaluationResponse>("/evaluations/run", { method: "POST" });
      setEvaluation(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evaluation failed.");
    } finally {
      setEvaluating(false);
    }
  }

  function selectDocument(documentId: string) {
    setSelectedId(documentId);
    setActiveView("documents");
    setInspectorTab("overview");
  }

  function toggleVector(id: string) {
    setExpandedVectors((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="product-name">
          <span className="product-icon">R</span>
          <div>
            <h1>RAG Studio</h1>
            <p>Local document retrieval</p>
          </div>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          <button className={activeView === "documents" ? "active" : ""} onClick={() => setActiveView("documents")}>Documents</button>
          <button className={activeView === "retrieve" ? "active" : ""} onClick={() => setActiveView("retrieve")}>Retrieve</button>
        </nav>
        <div className={`connection ${health ? "online" : "offline"}`}>
          <span />
          {health ? `MongoDB ${health.vector_index}` : "API offline"}
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")} aria-label="Dismiss error">Close</button>
        </div>
      )}

      <div className="workspace">
        <aside className="document-sidebar">
          <div className="sidebar-heading">
            <h2>Documents</h2>
            <span>{documents.length}</span>
          </div>

          <div
            className={`upload-control ${dragging ? "dragging" : ""}`}
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
            <span className="add-icon">+</span>
            <div>
              <strong>{uploading ? "Uploading files" : "Add documents"}</strong>
              <small>Drop files or browse</small>
            </div>
          </div>

          <div className="document-list">
            {!documents.length && <p className="empty-sidebar">No documents stored.</p>}
            {documents.map((document) => (
              <button
                key={document.id}
                className={`document-row ${selectedId === document.id ? "selected" : ""}`}
                onClick={() => selectDocument(document.id)}
              >
                <span className="file-type">{document.filename.split(".").pop()?.slice(0, 4).toUpperCase()}</span>
                <span className="document-summary">
                  <strong title={document.filename}>{document.filename}</strong>
                  <small>{formatBytes(document.size_bytes)} · {document.chunk_count} chunks</small>
                </span>
                <span className={`status-dot ${document.status}`} title={document.stage} />
              </button>
            ))}
          </div>

          <div className="sidebar-footer">
            <span>Embedding model</span>
            <strong>{health?.embedding_model.split("/").pop() ?? "Unavailable"}</strong>
            <small>{health?.embedding_dimensions ?? 384} dimensions · local</small>
            <small>Ambiguity: {health?.ambiguity_llm_configured ? health.ambiguity_model : "OpenRouter key not configured"}</small>
          </div>
        </aside>

        <section className="main-panel">
          {activeView === "documents" ? (
            selected ? (
              <div className="document-view">
                <header className="content-header">
                  <div>
                    <p className="section-label">Document inspector</p>
                    <h2>{selected.filename}</h2>
                    <p>{formatBytes(selected.size_bytes)} · uploaded {formatDate(selected.created_at)}</p>
                  </div>
                  <div className="document-actions">
                    <a className="secondary-button" href={`${API_URL}/documents/${selected.id}/raw`}>Download raw</a>
                    <button
                      className="danger-button"
                      disabled={selected.status === "processing" || selected.status === "deleting"}
                      onClick={() => setDeleteTarget(selected)}
                    >
                      Delete
                    </button>
                  </div>
                </header>

                <div className="ingestion-status">
                  <div className="status-summary">
                    <span className={`status-dot ${selected.status}`} />
                    <strong>{selected.stage}</strong>
                    <span>{selected.progress}%</span>
                  </div>
                  <div className="progress-track"><span style={{ width: `${selected.progress}%` }} /></div>
                  <div className="process-steps">
                    {ingestionStages.map(([label, threshold]) => (
                      <div className={selected.progress >= threshold ? "complete" : ""} key={label}>
                        <span>{selected.progress >= threshold ? "✓" : "○"}</span>
                        {label}
                      </div>
                    ))}
                  </div>
                  {selected.error && <p className="inline-error">{selected.error}</p>}
                </div>

                <div className="inspector-tabs" role="tablist">
                  {(["overview", "chunks", "storage"] as InspectorTab[]).map((tab) => (
                    <button
                      role="tab"
                      aria-selected={inspectorTab === tab}
                      className={inspectorTab === tab ? "active" : ""}
                      onClick={() => setInspectorTab(tab)}
                      key={tab}
                    >
                      {tab[0].toUpperCase() + tab.slice(1)}
                      {tab === "chunks" && <span>{selected.chunk_count}</span>}
                    </button>
                  ))}
                </div>

                {inspectorTab === "overview" && (
                  <div className="tab-content">
                    <h3>Document details</h3>
                    <dl className="property-list">
                      <div><dt>Status</dt><dd><span className={`status-dot ${selected.status}`} />{selected.stage}</dd></div>
                      <div><dt>Content type</dt><dd>{selected.content_type}</dd></div>
                      <div><dt>Extracted text</dt><dd>{selected.character_count.toLocaleString()} characters</dd></div>
                      <div><dt>Chunks</dt><dd>{selected.chunk_count.toLocaleString()}</dd></div>
                      <div><dt>Vectors</dt><dd>{selected.vector_count.toLocaleString()}</dd></div>
                      <div><dt>Vector dimensions</dt><dd>{selected.embedding_dimensions ?? health?.embedding_dimensions ?? 384}</dd></div>
                      <div><dt>Source status</dt><dd>{selected.source_metadata.source_status ?? "current"}</dd></div>
                      {selected.source_metadata.record_id && <div><dt>Record ID</dt><dd><code>{selected.source_metadata.record_id}</code></dd></div>}
                      {selected.source_metadata.effective_date && <div><dt>Effective date</dt><dd>{selected.source_metadata.effective_date}</dd></div>}
                      <div><dt>GridFS file ID</dt><dd><code>{selected.raw_file_id}</code></dd></div>
                      <div><dt>Document ID</dt><dd><code>{selected.id}</code></dd></div>
                    </dl>
                  </div>
                )}

                {inspectorTab === "chunks" && (
                  <div className="tab-content">
                    <div className="tab-heading">
                      <div><h3>Extracted chunks</h3><p>Text segments stored in the MongoDB chunks collection.</p></div>
                    </div>
                    <div className="chunk-table">
                      {!chunks.length && <p className="empty-state">Chunks appear when vectorization completes.</p>}
                      {chunks.map((chunk) => (
                        <article className="chunk-row" key={chunk.id}>
                          <div className="chunk-index">{chunk.chunk_index + 1}</div>
                          <div className="chunk-body">
                            <div className="chunk-meta">
                              <span>{chunk.page ? `Page ${chunk.page}` : chunk.section ?? "Document"}</span>
                              <span>{chunk.embedding_dimensions} dimensions</span>
                              <button onClick={() => toggleVector(chunk.id)}>
                                {expandedVectors.has(chunk.id) ? "Hide vector" : "Inspect vector"}
                              </button>
                            </div>
                            <p>{chunk.content}</p>
                            {expandedVectors.has(chunk.id) && <VectorPreview values={chunk.embedding_preview} />}
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                )}

                {inspectorTab === "storage" && (
                  <div className="tab-content">
                    <h3>MongoDB storage map</h3>
                    <p className="tab-description">This shows where each representation of the selected document lives.</p>
                    <table className="storage-table">
                      <thead><tr><th>Collection</th><th>Stored data</th><th>Records</th></tr></thead>
                      <tbody>
                        <tr><td><code>documents</code></td><td>Status, metadata, and GridFS reference</td><td>1</td></tr>
                        <tr><td><code>raw_files.files</code></td><td>Original filename and file metadata</td><td>1</td></tr>
                        <tr><td><code>raw_files.chunks</code></td><td>Original binary file content</td><td>GridFS managed</td></tr>
                        <tr><td><code>chunks</code></td><td>Extracted text, sources, and vectors</td><td>{selected.chunk_count}</td></tr>
                        <tr><td><code>chunk_vector_index</code></td><td>Search index over stored embeddings</td><td>{selected.vector_count}</td></tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              <div className="blank-state">
                <h2>No document selected</h2>
                <p>Add a document from the sidebar to inspect its stored data.</p>
                <button className="primary-button" onClick={() => inputRef.current?.click()}>Add document</button>
              </div>
            )
          ) : (
            <div className="retrieval-view">
              <header className="content-header compact">
                <div>
                  <p className="section-label">Retrieval pipeline</p>
                  <h2>Retrieve passages</h2>
                  <p>Compare vector-only retrieval with filtering, hybrid search, rank fusion, reranking and abstention.</p>
                </div>
                <div className="evaluation-action">
                  <button className="secondary-button" disabled={evaluating || searching} onClick={handleEvaluation}>
                    {evaluating ? "Running 19 checks…" : "Run evaluation"}
                  </button>
                  <small>{health?.ambiguity_llm_configured ? "May call OpenRouter" : "Ambiguity check disabled"}</small>
                </div>
              </header>

              {evaluation && (
                <section className="evaluation-panel" aria-live="polite">
                  <div className="evaluation-summary">
                    <div>
                      <p className="section-label">Behavioural evaluation</p>
                      <strong>{evaluation.passed} of {evaluation.total} passed</strong>
                      <span>{(evaluation.duration_ms / 1000).toFixed(1)} seconds · current indexed corpus</span>
                    </div>
                    <span className={evaluation.failed ? "evaluation-warning" : "evaluation-success"}>
                      {evaluation.failed} failed
                    </span>
                  </div>
                  <div className="evaluation-cases">
                    {evaluation.cases.map((item) => (
                      <details className={item.passed ? "passed" : "failed"} key={`${item.suite}-${item.id}`}>
                        <summary>
                          <span>{item.passed ? "✓" : "×"}</span>
                          <strong>{item.id}</strong>
                          <small>{item.detail}</small>
                        </summary>
                        <p>{item.question}</p>
                        <div>
                          Expected: {item.expected_behavior.replaceAll("_", " ")}
                          {item.top_results.length
                            ? ` · Top results: ${item.top_results.map((result) => `${result.filename} (${result.score.toFixed(3)})`).join(", ")}`
                            : " · No passages returned"}
                        </div>
                      </details>
                    ))}
                  </div>
                </section>
              )}

              <form className="search-form" onSubmit={handleSearch}>
                <label htmlFor="retrieval-query">Question or search phrase</label>
                <textarea
                  id="retrieval-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="What do the documents say about annual leave?"
                  rows={3}
                />
                <div className="search-controls">
                  <label>
                    Retrieval mode
                    <select value={searchMode} onChange={(event) => setSearchMode(event.target.value as "vector" | "hybrid")}>
                      <option value="hybrid">Enhanced hybrid pipeline</option>
                      <option value="vector">Vector-only baseline</option>
                    </select>
                  </label>
                  <label>
                    Search scope
                    <select value={scope} onChange={(event) => setScope(event.target.value)}>
                      <option value="all">All ready documents</option>
                      {documents.filter((document) => document.status === "ready").map((document) => (
                        <option value={document.id} key={document.id}>{document.filename}</option>
                      ))}
                    </select>
                  </label>
                  {searchMode === "hybrid" && (
                    <label className="checkbox-control">
                      <input
                        type="checkbox"
                        checked={includeSuperseded}
                        onChange={(event) => setIncludeSuperseded(event.target.checked)}
                      />
                      Include superseded sources
                    </label>
                  )}
                  <button className="primary-button" type="submit" disabled={searching || query.trim().length < 2}>
                    {searching ? "Searching" : "Retrieve"}
                  </button>
                </div>
              </form>

              {searchResponse && (
                <div className="pipeline-summary" aria-live="polite">
                  {searchResponse.mode === "vector" ? (
                    <span>Vector-only baseline · {searchResponse.pipeline.vector_candidates} candidates returned</span>
                  ) : (
                    <>
                      <span>Metadata filter</span><b>→</b>
                      <span>{searchResponse.pipeline.vector_candidates} vector + {searchResponse.pipeline.text_candidates} text</span><b>→</b>
                      <span>{searchResponse.pipeline.fused_candidates} fused</span><b>→</b>
                      <span>{searchResponse.pipeline.reranked_candidates} reranked</span><b>→</b>
                      <span>
                        threshold {searchResponse.pipeline.minimum_score?.toFixed(2)}
                        {searchResponse.pipeline.top_reranker_score != null
                          ? ` · top ${searchResponse.pipeline.top_reranker_score.toFixed(3)}`
                          : ""}
                      </span>
                      <span>ambiguity {searchResponse.pipeline.ambiguity_status.replaceAll("_", " ")}</span>
                    </>
                  )}
                </div>
              )}

              {searchResponse?.abstained && <div className="abstention" role="status">{searchResponse.message}</div>}

              {searchResponse?.decision === "clarify" && searchResponse.clarification && (
                <section className="clarification" aria-live="polite">
                  <p className="section-label">Clarification needed</p>
                  <h3>{searchResponse.clarification.question}</h3>
                  <p>{searchResponse.clarification.reason}</p>
                  <div>
                    {searchResponse.clarification.options.map((option) => (
                      <button
                        className="secondary-button"
                        key={option.refined_query}
                        disabled={searching}
                        onClick={() => {
                          setQuery(option.refined_query);
                          void performSearch(option.refined_query);
                        }}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              <div className="result-header">
                <h3>Results</h3>
                <span>{results.length ? `${results.length} passages` : "Run a search to see matches"}</span>
              </div>
              <div className="result-list">
                {results.map((result, index) => (
                  <article className="result-row" key={result.id}>
                    <div className="result-rank">{index + 1}</div>
                    <div className="result-body">
                      <div className="result-meta">
                        <button onClick={() => selectDocument(result.document_id)}>{result.filename}</button>
                        <span>{result.page ? `Page ${result.page}` : result.section ?? `Chunk ${result.chunk_index + 1}`}</span>
                        <span className="signal-list">{result.signals.map((signal) => <em key={signal}>{signal}</em>)}</span>
                        <strong>{result.score.toFixed(3)} {searchResponse?.mode === "hybrid" ? "reranker" : "vector"}</strong>
                      </div>
                      <p>{result.content}</p>
                      {searchResponse?.mode === "hybrid" && (
                        <div className="score-breakdown">
                          <span>vector {result.vector_score?.toFixed(3) ?? "—"}</span>
                          <span>text {result.text_score?.toFixed(3) ?? "—"}</span>
                          <span>fusion {result.fused_score?.toFixed(3) ?? "—"}</span>
                          <span>reranker {result.reranker_score?.toFixed(3) ?? "—"}</span>
                          <span>{result.source_status}{result.record_id ? ` · ${result.record_id}` : ""}</span>
                        </div>
                      )}
                      <button className="vector-toggle" onClick={() => toggleVector(result.id)}>
                        {expandedVectors.has(result.id) ? "Hide vector preview" : "Inspect vector preview"}
                      </button>
                      {expandedVectors.has(result.id) && <VectorPreview values={result.embedding_preview} />}
                    </div>
                  </article>
                ))}
                {!results.length && !searchResponse?.abstained && <div className="empty-state">Retrieved passages will appear here with their ranking signals.</div>}
              </div>
            </div>
          )}
        </section>
      </div>

      {deleteTarget && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !deleting && setDeleteTarget(null)}>
          <section
            className="delete-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-description"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="warning-mark">!</div>
            <h2 id="delete-title">Delete this document?</h2>
            <p id="delete-description">
              <strong>{deleteTarget.filename}</strong> will be permanently removed. This action cannot be undone.
            </p>
            <ul>
              <li>The original {formatBytes(deleteTarget.size_bytes)} file in GridFS</li>
              <li>{deleteTarget.chunk_count} extracted text chunks</li>
              <li>{deleteTarget.vector_count} embedding vectors and search index entries</li>
              <li>All document metadata and ingestion history</li>
            </ul>
            <div className="modal-actions">
              <button className="secondary-button" disabled={deleting} onClick={() => setDeleteTarget(null)}>Keep document</button>
              <button className="confirm-delete" disabled={deleting} onClick={handleDelete}>
                {deleting ? "Deleting everything" : "Delete permanently"}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
