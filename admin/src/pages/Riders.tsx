import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../components/Layout";
import { api, type RiderDetail, type RiderItem, type RiderStatus } from "../lib/api";

type Counts = Record<RiderStatus, number>;
type Action = "approve" | "reject" | "suspend" | "request_document";

const TABS: { key: RiderStatus; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Active" },
  { key: "rejected", label: "Rejected" },
  { key: "suspended", label: "Suspended" },
];

const DOC_LABELS: Record<string, string> = {
  cnic_front: "CNIC front",
  cnic_back: "CNIC back",
  driving_licence: "Driving licence",
  vehicle_registration: "Vehicle registration",
};

const VEHICLE: Record<string, string> = { motorbike: "Motorbike", rickshaw: "Rickshaw", pickup: "Pickup" };

const ACTIONS: Record<Action, { label: string; done: string; needsNote: boolean; danger?: boolean }> = {
  approve: { label: "Approve", done: "Rider approved", needsNote: false },
  request_document: { label: "Ask for a document", done: "Request sent to rider", needsNote: true },
  reject: { label: "Reject", done: "Rider rejected", needsNote: true, danger: true },
  suspend: { label: "Suspend", done: "Rider suspended", needsNote: true, danger: true },
};

/** Which actions make sense for each status. */
const ALLOWED: Record<RiderStatus, Action[]> = {
  pending: ["approve", "request_document", "reject"],
  approved: ["suspend"],
  rejected: ["approve"],
  suspended: ["approve"],
};

const PAGE = 20;

function StatusChip({ s }: { s: RiderStatus }) {
  const cls = s === "approved" ? "ok" : s === "pending" ? "wait" : "bad";
  const label = s === "approved" ? "Active" : s[0].toUpperCase() + s.slice(1);
  return <span className={`chip ${cls}`}>{label}</span>;
}

const date = (iso: string) => new Date(iso).toLocaleDateString("en-PK", { day: "numeric", month: "short", year: "numeric" });

export default function Riders() {
  const [tab, setTab] = useState<RiderStatus>("pending");
  const [counts, setCounts] = useState<Counts | null>(null);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<RiderItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadCounts = useCallback(() => {
    api<Counts>("/admin/riders/counts").then(setCounts).catch(() => undefined);
  }, []);

  const loadList = useCallback(() => {
    setLoading(true);
    setError(null);
    const p = new URLSearchParams({ status: tab, limit: String(PAGE), offset: String(offset) });
    if (search) p.set("q", search);
    api<{ items: RiderItem[]; total: number }>(`/admin/riders?${p}`)
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tab, offset, search]);

  useEffect(loadCounts, [loadCounts]);
  useEffect(loadList, [loadList]);

  const changeTab = (t: RiderStatus) => {
    setTab(t);
    setOffset(0);
    setSelected(null);
  };

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setSearch(q.trim());
  };

  const onDecided = (msg: string) => {
    setFlash(msg);
    setSelected(null);
    loadCounts();
    loadList();
    window.setTimeout(() => setFlash(null), 4000);
  };

  return (
    <>
      <PageHeader title="Riders" sub="Check documents, then approve riders before they can take pickups.">
        <form onSubmit={submitSearch} style={{ display: "flex", gap: 8 }}>
          <input className="input" style={{ width: 260 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone or vehicle no." aria-label="Search riders" />
          <button className="btn" type="submit">Search</button>
        </form>
      </PageHeader>
      <main className="page">
        <div role="tablist" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => changeTab(t.key)}
              className="btn"
              style={tab === t.key ? undefined : { background: "#fff", color: "var(--ink)", border: "1px solid var(--line-2)" }}
            >
              {t.label}
              <span style={{ marginLeft: 8, opacity: 0.8 }}>{counts ? counts[t.key] : "–"}</span>
            </button>
          ))}
        </div>

        {flash && (
          <div role="status" className="card" style={{ background: "var(--green-50)", borderColor: "#b6dccf", color: "#0b5e50", fontWeight: 700 }}>
            {flash}
          </div>
        )}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "1 1 420px", padding: 0, overflowX: "auto" }}>
            {error ? (
              <p style={{ padding: 18, color: "var(--urgent)", fontWeight: 600 }}>{error}</p>
            ) : loading ? (
              <p style={{ padding: 18, color: "var(--muted)" }}>Loading riders…</p>
            ) : items.length === 0 ? (
              <p style={{ padding: 18, color: "var(--muted)" }}>{search ? `No ${TABS.find((t) => t.key === tab)!.label.toLowerCase()} riders match "${search}".` : `No ${TABS.find((t) => t.key === tab)!.label.toLowerCase()} riders.`}</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--muted)", fontSize: 12 }}>
                    <th style={th}>Rider</th>
                    <th style={th}>Vehicle</th>
                    <th style={th}>Area</th>
                    <th style={th}>Docs</th>
                    <th style={th}>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setSelected(r.id)}
                      style={{ cursor: "pointer", background: selected === r.id ? "var(--green-50)" : undefined, borderTop: "1px solid var(--line)" }}
                    >
                      <td style={td}>
                        <button onClick={() => setSelected(r.id)} style={linkBtn}>{r.full_name}</button>
                        <div style={{ color: "var(--muted)", fontSize: 12 }}>{r.phone}</div>
                      </td>
                      <td style={td}>
                        {VEHICLE[r.vehicle_type]}
                        <div style={{ color: "var(--muted)", fontSize: 12 }}>{r.vehicle_number}</div>
                      </td>
                      <td style={td}>{r.location_path.slice(-2).join(", ") || "–"}</td>
                      <td style={td}>
                        <span className={`chip ${r.documents_count >= 4 ? "ok" : "wait"}`}>{r.documents_count}/4</span>
                      </td>
                      <td style={td}>{date(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {total > PAGE && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 18px", borderTop: "1px solid var(--line)" }}>
                <span style={{ color: "var(--muted)", fontSize: 13 }}>
                  {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
                </span>
                <span style={{ display: "flex", gap: 8 }}>
                  <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                  <button className="btn" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</button>
                </span>
              </div>
            )}
          </section>

          {selected && <RiderPanel id={selected} onClose={() => setSelected(null)} onDecided={onDecided} />}
        </div>
      </main>
    </>
  );
}

function RiderPanel({ id, onClose, onDecided }: { id: string; onClose: () => void; onDecided: (msg: string) => void }) {
  const [r, setR] = useState<RiderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const aiCheck = async () => {
    setChecking(true);
    setError(null);
    try {
      setR(await api<RiderDetail>(`/admin/riders/${id}/ai-review`, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    setR(null);
    setError(null);
    setAction(null);
    setNote("");
    api<RiderDetail>(`/admin/riders/${id}`).then(setR).catch((e) => setError(e.message));
  }, [id]);

  const decide = async () => {
    if (!action) return;
    setBusy(true);
    setError(null);
    try {
      await api<RiderDetail>(`/admin/riders/${id}/decision`, { method: "POST", body: JSON.stringify({ action, note: note.trim() || null }) });
      onDecided(`${ACTIONS[action].done}${r ? `: ${r.full_name}` : ""}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: 14 }} aria-label="Rider details">
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ marginRight: "auto" }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>{r?.full_name ?? "Loading…"}</h2>
          {r && <span style={{ color: "var(--muted)", fontSize: 13 }}>{r.phone}{r.email ? ` · ${r.email}` : ""}</span>}
        </div>
        {r && <StatusChip s={r.status} />}
        <button onClick={onClose} aria-label="Close" style={{ ...linkBtn, fontSize: 20, lineHeight: 1 }}>×</button>
      </div>

      {r && (
        <>
          <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 14px", margin: 0, fontSize: 14 }}>
            <dt style={dt}>Vehicle</dt>
            <dd style={{ margin: 0 }}>{VEHICLE[r.vehicle_type]} · {r.vehicle_number}</dd>
            <dt style={dt}>Area</dt>
            <dd style={{ margin: 0 }}>{r.location_path.join(" › ") || "–"}</dd>
            <dt style={dt}>Joined</dt>
            <dd style={{ margin: 0 }}>{date(r.created_at)}</dd>
            {r.reviewed_at && (
              <>
                <dt style={dt}>Last review</dt>
                <dd style={{ margin: 0 }}>{date(r.reviewed_at)}{r.review_note ? ` — "${r.review_note}"` : ""}</dd>
              </>
            )}
          </dl>

          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>Documents ({r.documents.length}/4)</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
              {Object.keys(DOC_LABELS).map((t) => {
                const d = r.documents.find((x) => x.doc_type === t);
                return (
                  <figure key={t} style={{ margin: 0, border: "1px solid var(--line)", borderRadius: 10, overflow: "hidden", background: "#fafbf9" }}>
                    {d ? (
                      <button onClick={() => setZoom(d.file_url)} style={{ display: "block", padding: 0, border: 0, width: "100%", cursor: "zoom-in", background: "none" }} aria-label={`Open ${DOC_LABELS[t]}`}>
                        <img src={d.file_url} alt={DOC_LABELS[t]} style={{ display: "block", width: "100%", height: 100, objectFit: "cover" }} />
                      </button>
                    ) : (
                      <div style={{ height: 100, display: "grid", placeItems: "center", color: "var(--muted)", fontSize: 12 }}>Not uploaded</div>
                    )}
                    <figcaption style={{ padding: "6px 8px", fontSize: 12, fontWeight: 600 }}>{DOC_LABELS[t]}</figcaption>
                  </figure>
                );
              })}
            </div>
          </div>

          <section style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h3 style={{ margin: 0, fontSize: 14, flex: 1 }}>AI document check</h3>
              <button className="btn ghost small" disabled={checking || r.documents.length === 0} onClick={aiCheck}>
                {checking ? "Checking… (up to 30 s)" : r.ai_review ? "Check again" : "Run AI check"}
              </button>
            </div>
            {r.ai_review ? (
              <>
                <p style={{ margin: 0, fontSize: 14 }}>{r.ai_review.summary}</p>
                <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
                  {r.ai_review.checks.map((c) => (
                    <li key={c.label} style={{ display: "flex", gap: 8 }}>
                      <span aria-label={c.ok === true ? "Looks fine" : c.ok === false ? "Problem" : "Could not tell"}
                        style={{ fontWeight: 800, width: 16, color: c.ok === true ? "var(--green-700)" : c.ok === false ? "var(--urgent)" : "var(--warn)" }}>
                        {c.ok === true ? "✓" : c.ok === false ? "✗" : "?"}
                      </span>
                      <span>
                        <strong>{c.label}</strong>
                        {c.detail ? <span className="muted"> · {c.detail}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
                <span className="muted small">{r.ai_review.model} · {date(r.ai_review.created_at)} · advisory only, you decide</span>
              </>
            ) : (
              <span className="muted small">Claude reads the 4 photos and checks name, vehicle number and signs of editing. You still make the decision.</span>
            )}
          </section>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {ALLOWED[r.status].map((a) => (
              <button
                key={a}
                className="btn"
                onClick={() => {
                  setAction(a);
                  setError(null);
                }}
                style={
                  action === a
                    ? { outline: "3px solid var(--green-50)" }
                    : ACTIONS[a].danger
                    ? { background: "#fff", color: "var(--urgent)", border: "1px solid #edb49e" }
                    : a === "approve"
                    ? undefined
                    : { background: "#fff", color: "var(--ink)", border: "1px solid var(--line-2)" }
                }
              >
                {ACTIONS[a].label}
              </button>
            ))}
          </div>

          {action && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {ACTIONS[action].needsNote && (
                <>
                  <label htmlFor="note" style={{ fontSize: 13, fontWeight: 600 }}>
                    Note to the rider (required)
                  </label>
                  <textarea
                    id="note"
                    className="input"
                    style={{ height: 80, padding: 10, resize: "vertical" }}
                    maxLength={500}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={action === "request_document" ? "e.g. CNIC back photo is blurry, please upload again" : "Why?"}
                  />
                </>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" disabled={busy || (ACTIONS[action].needsNote && !note.trim())} onClick={decide}>
                  {busy ? "Saving…" : `Confirm: ${ACTIONS[action].label.toLowerCase()}`}
                </button>
                <button className="btn" style={{ background: "#fff", color: "var(--ink)", border: "1px solid var(--line-2)" }} onClick={() => setAction(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {error && (
        <div role="alert" style={{ color: "var(--urgent)", fontWeight: 600 }}>
          {error}
        </div>
      )}

      {zoom && (
        <div onClick={() => setZoom(null)} role="dialog" aria-label="Document photo" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.75)", display: "grid", placeItems: "center", padding: 24, zIndex: 50, cursor: "zoom-out" }}>
          <img src={zoom} alt="Document" style={{ maxWidth: "100%", maxHeight: "100%", borderRadius: 8 }} />
        </div>
      )}
    </aside>
  );
}

const th = { padding: "12px 18px", fontWeight: 700 } as const;
const td = { padding: "12px 18px", verticalAlign: "top" } as const;
const dt = { color: "var(--muted)", fontWeight: 600 } as const;
const linkBtn = { padding: 0, border: 0, background: "none", font: "inherit", fontWeight: 700, color: "var(--ink)", cursor: "pointer", textAlign: "left" } as const;
