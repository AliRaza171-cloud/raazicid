import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import AppealForm from "../components/AppealForm";
import { PageHeader } from "../components/Layout";
import LocationSelect from "../components/LocationSelect";
import { api, type Category, type FinderAnswer, type FinderArea } from "../lib/api";
import { date } from "../lib/format";

const EXAMPLES = [
  "Where are blankets and winter clothes needed most this winter?",
  "Which districts have the worst food insecurity right now?",
  "Where are flood-affected families still waiting for help?",
  "Which areas need hygiene kits for women and children?",
];

const NEED: Record<string, { label: string; cls: string }> = {
  urgent: { label: "Urgent need", cls: "lv3" },
  high: { label: "High need", cls: "lv2" },
  some: { label: "Some need", cls: "lv1" },
};

/** Does our own data (needs by area) agree with what the reports say? Plain words for the admin. */
function ourData(level: number | null): { text: string; color: string } {
  if (level === null) return { text: "Not in our places list", color: "var(--muted)" };
  if (level >= 2) return { text: "Our data agrees", color: "#0b5e50" };
  if (level === 1) return { text: "Our data shows some need", color: "var(--warn)" };
  return { text: "Not in our data yet", color: "var(--muted)" };
}

export default function NeedFinder() {
  const [cats, setCats] = useState<Category[]>([]);
  const [question, setQuestion] = useState("");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [web, setWeb] = useState<"auto" | "always" | "off">("auto");
  const [saved, setSaved] = useState<Record<string, string>>({});   // url -> "saving" | "saved" | error text
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<FinderAnswer | null>(null);
  const [focus, setFocus] = useState<string | null>(null);     // a source id like S2 / D1, or "Web"
  const [showSources, setShowSources] = useState(false);
  const [appealFor, setAppealFor] = useState<FinderArea | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const ask = async (e?: FormEvent) => {
    e?.preventDefault();
    if (question.trim().length < 5) return setError("Write a question first");
    setBusy(true);
    setError(null);
    setFocus(null);
    setShowSources(false);
    setAppealFor(null);
    setSaved({});
    try {
      setRes(await api<FinderAnswer>("/admin/need-finder/ask", {
        method: "POST",
        body: JSON.stringify({ question: question.trim(), location_id: locationId, category_id: categoryId, web }),
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saveToLibrary = async (url: string, title: string) => {
    setSaved((x) => ({ ...x, [url]: "saving" }));
    try {
      await api("/admin/reports/link", { method: "POST", body: JSON.stringify({ url, title }) });
      setSaved((x) => ({ ...x, [url]: "saved" }));
    } catch (e) {
      const msg = (e as Error).message;
      setSaved((x) => ({ ...x, [url]: msg.startsWith("Already in the library") ? "saved" : msg }));
    }
  };

  const openSource = (id: string) => {
    setShowSources(true);
    setFocus(focus === id ? null : id);
  };

  /** "Lyari needs blankets [S1] [Web]" with small clickable source chips */
  const cite = (text: string): ReactNode[] =>
    text.split(/(\[(?:S\d+|D\d+|Web)\])/g).map((part, i) => {
      const m = part.match(/^\[(S\d+|D\d+|Web)\]$/);
      if (!m) return <span key={i}>{part}</span>;
      const on = focus === m[1];
      return (
        <button key={i} onClick={() => openSource(m[1])} title={m[1] === "Web" ? "Found on the web" : m[1].startsWith("D") ? "Our need data" : "A report in the library"}
          style={{ border: 0, borderRadius: 6, padding: "0 5px", margin: "0 1px", fontSize: 10, fontWeight: 800, cursor: "pointer", verticalAlign: 1,
                   background: on ? "var(--green-700)" : "#eef0ec", color: on ? "#fff" : "#46504b" }}>
          {m[1] === "Web" ? "web" : m[1]}
        </button>
      );
    });

  const catIds = (names: string[]) => cats.filter((c) => names.some((n) => n.toLowerCase().includes(c.name.toLowerCase().split(" ")[0]) || c.name.toLowerCase().includes(n.toLowerCase()))).map((c) => c.id);

  return (
    <>
      <PageHeader title="Need finder" sub="Ask where help is needed. Answers come from the report library, our need levels and (if you switch it on) the web, and cite every source." />
      <main className="page">
        <form className="card" onSubmit={ask} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <textarea className="input" style={{ height: 76, paddingTop: 10 }} value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question"
            placeholder="Where in Sindh are blankets needed most this winter?" maxLength={600} />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {EXAMPLES.map((x) => (
              <button key={x} type="button" className="chip wait" style={{ border: 0, cursor: "pointer" }} onClick={() => setQuestion(x)}>{x}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <LocationSelect compact allLabel="All Pakistan" onChange={(id) => setLocationId(id)} />
            <select className="select" aria-label="Category" value={categoryId ?? ""} onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Any category</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 600 }}>
              Web search
              <select className="select" value={web} onChange={(e) => setWeb(e.target.value as "auto" | "always" | "off")}
                title="Each web search costs about 1 cent and takes up to a minute">
                <option value="auto">Auto (when our reports have little)</option>
                <option value="always">Always</option>
                <option value="off">Off (our reports only)</option>
              </select>
            </label>
            <button className="btn" type="submit" disabled={busy} style={{ marginLeft: "auto" }}>
              {busy ? (web === "off" ? "Searching our reports…" : "Searching our reports and the web…") : "Find needs"}
            </button>
          </div>
        </form>

        {error && <div className="flash bad" role="alert">{error}</div>}
        {flash && <div className="flash ok" role="status">{flash}</div>}

        {res && (
          <>
            <section className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }} aria-label="Answer">
              <p style={{ margin: 0, fontSize: 19, fontWeight: 700, lineHeight: 1.4 }}>{cite(res.summary || res.answer)}</p>
              {res.points.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6, fontSize: 15, lineHeight: 1.5 }}>
                  {res.points.map((pt, i) => <li key={i}>{cite(pt)}</li>)}
                </ul>
              )}
              {res.note && <p className="muted" style={{ margin: 0, fontSize: 14 }}>ⓘ Good to know: {res.note}</p>}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", borderTop: "1px solid var(--line)", paddingTop: 10 }}>
                <span className="muted small">
                  Based on {res.sources.length} report passage{res.sources.length === 1 ? "" : "s"}
                  {res.facts.some((f) => f.kind !== "3w") ? ", our need data" : ""}
                  {res.facts.some((f) => f.kind === "3w") ? ", UN data on who works where" : ""}
                  {res.reliefweb_found ? `, ${res.reliefweb_found} ReliefWeb reports checked` : ""}
                  {res.used_web ? ` and a web search (${res.web_results.length} page${res.web_results.length === 1 ? "" : "s"})` : res.web_mode === "auto" ? " (our reports covered it, no web search needed)" : ""}
                  {res.ai ? ` · how sure: ${res.confidence}` : ""}
                </span>
                <button className="btn ghost small" style={{ marginLeft: "auto" }} onClick={() => setShowSources(!showSources)}>
                  {showSources ? "Hide sources" : "Show sources"}
                </button>
              </div>
            </section>

            {res.areas.length > 0 && (
              <section className="card" style={{ padding: 0 }} aria-label="Where to help">
                <h2 style={{ margin: 0, fontSize: 16, padding: "14px 18px 4px" }}>Where to help</h2>
                <table className="table">
                  <thead><tr><th>Place</th><th>Need</th><th>What is needed</th><th>Why</th><th /></tr></thead>
                  <tbody>
                    {res.areas.map((a, i) => {
                      const od = ourData(a.our_level);
                      return (
                        <Fragment key={i}>
                          <tr>
                            <td style={{ whiteSpace: "nowrap" }}>
                              <strong>{a.name}</strong>
                              {a.path.length > 1 && <div className="muted small">{a.path.slice(0, -1).join(" › ")}</div>}
                            </td>
                            <td style={{ whiteSpace: "nowrap" }}>
                              <span className={`chip ${NEED[a.need]?.cls ?? "lv1"}`}>{NEED[a.need]?.label ?? "Some need"}</span>
                              <div className="small" style={{ color: od.color, marginTop: 4 }}>{od.text}</div>
                            </td>
                            <td>{a.categories.join(", ") || "–"}</td>
                            <td style={{ maxWidth: 420 }}>{cite(a.reason)}</td>
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                              {a.location_id && <button className="btn small" onClick={() => setAppealFor(appealFor === a ? null : a)}>Send appeal</button>}
                            </td>
                          </tr>
                          {appealFor === a && a.location_id && (
                            <tr>
                              <td colSpan={5}>
                                <AppealForm cats={cats}
                                  defaults={{ title: `${a.categories[0] ?? "Help"} needed in ${a.name}`, message: a.reason.replace(/\s*\[(?:S\d+|D\d+|Web)\]/g, ""),
                                              locationId: a.location_id, locationPath: a.path, categoryIds: catIds(a.categories) }}
                                  onCancel={() => setAppealFor(null)}
                                  onSent={(ap) => { setAppealFor(null); setFlash(`Appeal sent to ${ap.reached} donors in ${ap.provinces.join(", ")}`); }} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
                <div style={{ display: "flex", gap: 8, padding: "0 18px 14px" }}>
                  <Link className="btn ghost small" to="/needs">Open needs by area</Link>
                  <Link className="btn ghost small" to="/points">Add a distribution point</Link>
                </div>
              </section>
            )}

            {showSources && (
              <section className="card" style={{ padding: 0 }} aria-label="Sources">
                <h2 style={{ margin: 0, fontSize: 16, padding: "14px 18px 4px" }}>Where this comes from</h2>
                {res.sources.length === 0 && res.facts.length === 0 && res.web_results.length === 0 && (
                  <p className="muted small" style={{ padding: "0 18px 14px", margin: 0 }}>No sources. Upload reports in the Report library.</p>
                )}
                {res.sources.map((s) => (
                  <div key={s.id} style={{ borderTop: "1px solid var(--line)", padding: "10px 18px", background: focus === s.id ? "var(--green-50)" : undefined }}>
                    <button onClick={() => setFocus(focus === s.id ? null : s.id)} style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer", textAlign: "left" }}>
                      <span className={`chip ${s.cited ? "solid" : "wait"}`}>{s.id}</span> <strong>{s.title}</strong>
                      <span className="muted small"> · {s.publisher}{s.date ? `, ${date(s.date)}` : ""}{s.page ? `, page ${s.page}` : ""}</span>
                    </button>
                    {focus === s.id && (
                      <>
                        <p style={{ fontSize: 13, whiteSpace: "pre-wrap", margin: "8px 0 4px" }}>{s.text}</p>
                        <span className="muted small">Found by {s.found_by.join(" + ") || "search"}{s.places.length ? ` · about ${s.places.join(", ")}` : ""}</span>
                        {s.url && <> · <a className="small" href={s.url} target="_blank" rel="noreferrer">Open the original</a></>}
                      </>
                    )}
                  </div>
                ))}
                {res.facts.map((f) => (
                  <div key={f.id} style={{ borderTop: "1px solid var(--line)", padding: "10px 18px", background: focus === f.id ? "var(--green-50)" : undefined }}>
                    <span className="chip wait">{f.id}</span>{" "}
                    {f.kind === "3w"
                      ? <><strong>Who works in {f.place.split(" › ").slice(-1)[0]}:</strong> {f.text}</>
                      : <><strong>Our data:</strong> {f.category} need is <strong>{f.level}</strong> in {f.place}</>}
                    {focus === f.id && <div className="muted small" style={{ marginTop: 4 }}>{f.why}</div>}
                  </div>
                ))}
                {res.web_results.length > 0 && (
                  <div style={{ borderTop: "1px solid var(--line)", padding: "10px 18px", background: focus === "Web" ? "var(--green-50)" : undefined }}>
                    <span className="chip wait">web</span> <strong>Found on the web</strong>
                    <span className="muted small"> · Save a good page to the library so future answers can use it without searching.</span>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                      {res.web_results.map((w) => {
                        const st = saved[w.url];
                        return (
                          <div key={w.url} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <a href={w.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>{w.title}</a>
                              <div className="muted small">
                                {new URL(w.url).hostname.replace("www.", "")}{w.age ? ` · ${w.age}` : ""}{w.cited ? " · used in the answer" : ""}
                              </div>
                              {w.snippet && <div className="small" style={{ marginTop: 2 }}>“{w.snippet}”</div>}
                              {st && st !== "saving" && st !== "saved" && <div className="small" style={{ color: "var(--urgent)" }}>{st}</div>}
                            </div>
                            <button className="btn ghost small" disabled={st === "saving" || st === "saved"} onClick={() => saveToLibrary(w.url, w.title)}>
                              {st === "saving" ? "Saving…" : st === "saved" ? "Saved ✓" : "Save to library"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </>
  );
}
