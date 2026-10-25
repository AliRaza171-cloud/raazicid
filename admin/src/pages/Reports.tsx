import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../components/Layout";
import LocationSelect from "../components/LocationSelect";
import { api, type ChunkTag, type RagStatus, type ReportChunk, type ReportDetail, type ReportItem } from "../lib/api";
import { date } from "../lib/format";

const STATUS: Record<string, { label: string; chip: string }> = {
  tagged: { label: "Ready", chip: "ok" },
  needs_review: { label: "No places found", chip: "warn" },
  new: { label: "New", chip: "info" },
  archived: { label: "Archived", chip: "wait" },
};

type Filter = "all" | "needs_review" | "links" | "archived";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Check places" },
  { key: "links", label: "Links without text" },
  { key: "archived", label: "Archived" },
];

export default function Reports() {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [reports, setReports] = useState<ReportItem[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState<"file" | "link" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (filter === "needs_review" || filter === "archived") p.set("status", filter);
    if (q.trim()) p.set("q", q.trim());
    api<ReportItem[]>(`/admin/reports?${p}`).then(setReports).catch((e) => setError(e.message));
    api<RagStatus>("/admin/rag/status").then(setStatus).catch(() => undefined);
  }, [filter, q]);

  useEffect(load, [load]);

  const say = (msg: string) => {
    setFlash(msg);
    load();
    window.setTimeout(() => setFlash(null), 5000);
  };

  const embedMissing = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ done: number; note: string }>("/admin/rag/embed-missing", { method: "POST" });
      say(r.note);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const shown = (reports ?? []).filter((r) => filter !== "links" || !r.has_text);
  const missingVectors = status ? status.chunks - status.chunks_with_vectors : 0;

  return (
    <>
      <PageHeader title="Report library" sub="Everything the need finder reads: uploaded reports, news links and ReliefWeb. Each passage is tagged with the places it talks about.">
        <button className="btn ghost" onClick={() => { setSelected(null); setAdding("link"); }}>+ Add a link</button>
        <button className="btn" onClick={() => { setSelected(null); setAdding("file"); }}>+ Upload a report</button>
      </PageHeader>
      <main className="page">
        <section className="grid-kpi">
          <div className="card">
            <div className="kpi-label">Reports</div>
            <div className="kpi-value">{status?.reports ?? "–"}</div>
            <div className="muted small">{status ? `${status.chunks} passages` : ""}</div>
          </div>
          <div className="card">
            <div className="kpi-label">Search</div>
            <div style={{ fontSize: 18, fontWeight: 800, marginTop: 6 }}>{status?.search === "keyword" ? "Keywords" : status ? "Meaning + keywords" : "–"}</div>
            <div className="muted small">{status?.embeddings.note}</div>
            {status?.embeddings.available && missingVectors > 0 && (
              <button className="btn ghost small" style={{ marginTop: 8 }} disabled={busy} onClick={embedMissing}>
                {busy ? "Working…" : `Add vectors to ${missingVectors} passages`}
              </button>
            )}
          </div>
          <div className="card">
            <div className="kpi-label">Claude answers</div>
            <div style={{ marginTop: 8 }}>{status ? <span className={`chip ${status.claude ? "ok" : "bad"}`}>{status.claude ? "Ready" : "Add ANTHROPIC_API_KEY"}</span> : null}</div>
          </div>
          <div className="card">
            <div className="kpi-label">ReliefWeb</div>
            <div style={{ marginTop: 8 }}>{status ? <span className={`chip ${status.reliefweb ? "ok" : "wait"}`}>{status.reliefweb ? "Every 6 hours" : "Waiting for appname"}</span> : null}</div>
          </div>
        </section>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div className="tabs" role="tablist">
            {FILTERS.map((f) => (
              <button key={f.key} role="tab" aria-selected={filter === f.key} className={filter === f.key ? "btn small" : "btn ghost small"} onClick={() => setFilter(f.key)}>{f.label}</button>
            ))}
          </div>
          <input className="input" style={{ maxWidth: 260, height: 38, marginLeft: "auto" }} placeholder="Search titles" aria-label="Search titles" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>

        {flash && <div className="flash ok" role="status">{flash}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "2 1 520px", padding: 0, overflowX: "auto" }}>
            {reports === null ? (
              <p className="muted" style={{ padding: 18 }}>Loading…</p>
            ) : shown.length === 0 ? (
              <p className="muted" style={{ padding: 18 }}>
                {filter === "all" ? "The library is empty. Upload a situation report or needs assessment (PDF), or add a news link." : "Nothing here."}
              </p>
            ) : (
              <table className="table">
                <thead><tr><th>Report</th><th>Places</th><th>Passages</th><th>Status</th></tr></thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.id} className="click" onClick={() => { setAdding(null); setSelected(r.id); }} style={selected === r.id ? { background: "var(--green-50)" } : undefined}>
                      <td>
                        <strong>{r.title}</strong>
                        <div className="muted small">{r.publisher ?? r.source} · {date(r.published_at ?? r.created_at)} · {r.source}</div>
                      </td>
                      <td className="small">{r.places.join(", ") || <span className="muted">–</span>}</td>
                      <td>{r.has_text ? r.chunks : <span className="chip wait">Link only</span>}</td>
                      <td><span className={`chip ${STATUS[r.status].chip}`}>{STATUS[r.status].label}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {adding === "file" && <UploadPanel onClose={() => setAdding(null)} onDone={(r) => { setAdding(null); setSelected(r.id); say(`Added ${r.title}: ${r.chunks} passages`); }} />}
          {adding === "link" && <LinkPanel onClose={() => setAdding(null)} onDone={(r) => { setAdding(null); setSelected(r.id); say(`Added ${r.title}: ${r.chunks} passages`); }} />}
          {selected && !adding && <ReportPanel key={selected} id={selected} onClose={() => setSelected(null)} onChanged={say} />}
        </div>
      </main>
    </>
  );
}

function UploadPanel({ onClose, onDone }: { onClose: () => void; onDone: (r: ReportDetail) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [publisher, setPublisher] = useState("");
  const [published, setPublished] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return setError("Choose a PDF or .txt file");
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    if (publisher.trim()) form.append("publisher", publisher.trim());
    if (published) form.append("published_at", published);
    setBusy(true);
    setError(null);
    try {
      onDone(await api<ReportDetail>("/admin/reports/upload", { method: "POST", body: form }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 360px" }} aria-label="Upload a report">
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 18, marginRight: "auto" }}>Upload a report</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
        </div>
        <p className="muted small" style={{ margin: 0 }}>NDMA / PDMA situation reports, IPC analyses, NGO needs assessments or your own field notes. PDF or .txt, up to 15 MB. Scanned PDFs (photos of pages) cannot be read.</p>
        <input type="file" accept=".pdf,.txt,.md,application/pdf,text/plain" aria-label="File" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div>
          <label htmlFor="rtitle">Title (optional)</label>
          <input id="rtitle" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Uses the file name if empty" />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="rpub">Published by</label>
            <input id="rpub" className="input" value={publisher} onChange={(e) => setPublisher(e.target.value)} placeholder="PDMA Sindh" />
          </div>
          <div style={{ flex: 1 }}>
            <label htmlFor="rdate">Date</label>
            <input id="rdate" type="date" className="input" value={published} onChange={(e) => setPublished(e.target.value)} />
          </div>
        </div>
        {error && <div className="flash bad" role="alert">{error}</div>}
        <button className="btn" type="submit" disabled={busy}>{busy ? "Reading the report…" : "Upload and read"}</button>
      </form>
    </aside>
  );
}

function LinkPanel({ onClose, onDone }: { onClose: () => void; onDone: (r: ReportDetail) => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api<ReportDetail>("/admin/reports/link", { method: "POST", body: JSON.stringify({ url: url.trim() }) }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 360px" }} aria-label="Add a link">
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 18, marginRight: "auto" }}>Add a link</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
        </div>
        <p className="muted small" style={{ margin: 0 }}>A news article, an NDMA / PDMA page or an online PDF. Some sites block automatic reading; then download the PDF and upload it.</p>
        <div>
          <label htmlFor="rurl">Link</label>
          <input id="rurl" className="input" value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://www.dawn.com/news/..." />
        </div>
        {error && <div className="flash bad" role="alert">{error}</div>}
        <button className="btn" type="submit" disabled={busy}>{busy ? "Reading the page…" : "Read and add"}</button>
      </form>
    </aside>
  );
}

function ReportPanel({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: (msg: string) => void }) {
  const [r, setR] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<ReportDetail>(`/admin/reports/${id}`).then(setR).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  const act = async (path: string, msg: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/admin/reports/${id}/${path}`, { method: "POST" });
      load();
      onChanged(msg);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!r) {
    return <aside className="card" style={{ flex: "1 1 420px" }}>{error ? <div className="flash bad">{error}</div> : <p className="muted">Loading…</p>}</aside>;
  }

  return (
    <aside className="card" style={{ flex: "1 1 420px", display: "flex", flexDirection: "column", gap: 12, maxHeight: "80vh", overflowY: "auto" }} aria-label="Report">
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <div style={{ marginRight: "auto" }}>
          <span className={`chip ${STATUS[r.status].chip}`}>{STATUS[r.status].label}</span>
          <h2 style={{ margin: "8px 0 2px", fontSize: 18 }}>{r.title}</h2>
          <div className="muted small">{r.publisher ?? r.source} · {date(r.published_at ?? r.created_at)} · {r.source}</div>
          {r.url && <a className="small" href={r.url} target="_blank" rel="noreferrer">Open the original</a>}
        </div>
        <button onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
      </div>
      {error && <div className="flash bad" role="alert">{error}</div>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {!r.has_text && r.url && <button className="btn small" disabled={busy} onClick={() => act("fetch", "Read the article")}>{busy ? "Reading…" : "Read the article text"}</button>}
        {r.status === "archived" ? (
          <button className="btn ghost small" disabled={busy} onClick={() => act("restore", "Restored")}>Restore</button>
        ) : (
          <button className="btn danger small" disabled={busy} onClick={() => act("archive", "Archived: the need finder will not use it")}>Archive (out of date)</button>
        )}
      </div>
      {!r.has_text ? (
        <p className="muted" style={{ margin: 0 }}>Only the link is saved (from the news scan or GDACS). Read the article text so the need finder can use it.</p>
      ) : (
        <>
          <p className="muted small" style={{ margin: 0 }}>{r.chunks} passages. Check the places: the need finder uses them to answer questions about an area.</p>
          {r.chunk_list.map((c) => <Passage key={c.id} c={c} onSaved={(nc) => setR({ ...r, chunk_list: r.chunk_list.map((x) => (x.id === nc.id ? nc : x)) })} />)}
        </>
      )}
    </aside>
  );
}

function Passage({ c, onSaved }: { c: ReportChunk; onSaved: (c: ReportChunk) => void }) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newId, setNewId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async (tags: string[]) => {
    setError(null);
    try {
      onSaved(await api<ReportChunk>(`/admin/chunks/${c.id}/places`, { method: "PUT", body: JSON.stringify({ location_ids: tags }) }));
      setAdding(false);
      setNewId(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const ids = c.places.map((p) => p.id);
  const chip = (t: ChunkTag) => (
    <span key={t.id} className={`chip ${t.confirmed ? "ok" : t.confidence < 1 ? "warn" : "info"}`} title={`${t.path.join(" › ")}${t.confidence < 1 ? " (from the title)" : ""}`} style={{ gap: 4 }}>
      {t.name}
      <button onClick={() => save(ids.filter((x) => x !== t.id))} aria-label={`Remove ${t.name}`} style={{ border: 0, background: "none", cursor: "pointer", color: "inherit", padding: 0, fontWeight: 800 }}>×</button>
    </span>
  );

  return (
    <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="muted small">Passage {c.index + 1}{c.page ? ` · page ${c.page}` : ""}{c.has_embedding ? " · vector" : ""}</div>
      <div style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>
        {open || c.text.length <= 320 ? c.text : `${c.text.slice(0, 320)}…`}
        {c.text.length > 320 && (
          <button onClick={() => setOpen(!open)} style={{ border: 0, background: "none", color: "var(--green-700)", fontWeight: 700, cursor: "pointer" }}>{open ? "Less" : "More"}</button>
        )}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
        {c.places.length ? c.places.map(chip) : <span className="muted small">No places</span>}
        {!adding && <button className="btn ghost small" onClick={() => setAdding(true)}>+ Place</button>}
      </div>
      {adding && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <LocationSelect compact allLabel="Choose" onChange={(id) => setNewId(id)} />
          <button className="btn small" disabled={!newId} onClick={() => newId && save([...ids, newId])}>Add</button>
          <button className="btn ghost small" onClick={() => setAdding(false)}>Cancel</button>
        </div>
      )}
      {error && <div className="flash bad" role="alert">{error}</div>}
    </div>
  );
}
