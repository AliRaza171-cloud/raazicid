import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import { api, type Category, type Donation, type NgoOption, type NgoSearch, type RiderOption } from "../lib/api";
import { STATUS, dateTime, urgencyChip, windowText } from "../lib/format";

const PROOF = { pickup_proof: "Pickup", delivery_proof: "Handed to the NGO" } as const;

const MATCH: Record<NgoOption["match"], string> = {
  same_area: "Same area",
  same_region: "Same region",
  same_city: "Same city",
  same_province: "Same province",
  other: "Further away",
};

export default function DonationDetail() {
  const { id } = useParams();
  const [d, setD] = useState<Donation | null>(null);
  const [options, setOptions] = useState<NgoOption[] | null>(null);
  const [ngoId, setNgoId] = useState<string>("");
  const [searching, setSearching] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [zoom, setZoom] = useState<string | null>(null);
  const [riders, setRiders] = useState<RiderOption[] | null>(null);
  const [catNames, setCatNames] = useState<Record<number, string>>({});
  const [riderId, setRiderId] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(() => {
    api<Donation>(`/donations/${id}`)
      .then((data) => {
        setD(data);
        if (data.status === "accepted") {
          api<RiderOption[]>(`/admin/donations/${id}/rider-options`)
            .then((rs) => {
              setRiders(rs);
              setRiderId(rs[0]?.id ?? "");
            })
            .catch((e) => setError(e.message));
        }
        if (data.status === "in_review") {
          api<NgoOption[]>(`/admin/donations/${id}/ngo-options`)
            .then((opts) => {
              setOptions(opts);
              setNgoId(opts[0]?.id ?? "");
            })
            .catch((e) => setError(e.message));
        }
      })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);
  useEffect(() => {
    api<Category[]>("/categories").then((cs) => setCatNames(Object.fromEntries(cs.map((c) => [c.id, c.name])))).catch(() => undefined);
  }, []);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api<Donation>(`/admin/donations/${id}/accept`, { method: "POST", body: JSON.stringify({ ngo_id: ngoId }) });
      setD(out);
      setFlash(`Accepted. Our rider will take it to ${out.ngo?.name}. The donor has been told.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api<Donation>(`/admin/donations/${id}/reject`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) });
      setD(out);
      setRejecting(false);
      setFlash("Rejected. The donor can see your reason in the app.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const act = async (path: string, body: object, done: (out: Donation) => string) => {
    setBusy(true);
    setError(null);
    try {
      const out = await api<Donation>(`/admin/donations/${id}/${path}`, { method: "POST", body: JSON.stringify(body) });
      setD(out);
      setFlash(done(out));
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const assign = () => act("assign", { rider_id: riderId }, (out) => `Assigned to ${out.job?.rider_name}. The rider and donor have been told.`);

  const cancelJob = () =>
    act("cancel-job", { reason: cancelReason.trim() }, () => {
      setCancelling(false);
      setCancelReason("");
      return "Job cancelled. Choose another rider.";
    });

  const city = d ? d.pickup.location_path[Math.min(1, d.pickup.location_path.length - 1)] : "";
  const searchWeb = async () => {
    if (!d) return;
    setSearching(true);
    setError(null);
    try {
      // the pickup's city: the backend widens an area or district to its city
      const r = await api<NgoSearch>("/admin/ngos/search", { method: "POST", body: JSON.stringify({ location_id: d.pickup.location_id, category_id: d.category.id }) });
      setFlash(r.status);
      const opts = await api<NgoOption[]>(`/admin/donations/${id}/ngo-options`);
      setOptions(opts);
      setNgoId(opts[0]?.id ?? "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  };

  if (!d) {
    return (
      <>
        <PageHeader title="Donation" />
        <main className="page">{error ? <div className="flash bad">{error}</div> : <p className="muted">Loading…</p>}</main>
      </>
    );
  }

  const s = STATUS[d.status];
  const u = urgencyChip(d.urgency_score);
  return (
    <>
      <PageHeader title={d.title} sub={`${d.ref} · created ${dateTime(d.created_at)}`}>
        <Link to="/donations" className="btn ghost">← All donations</Link>
      </PageHeader>
      <main className="page">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className={`chip ${s.chip}`}>{s.label}</span>
          {d.urgency_score !== null && <span className={`chip ${u.cls}`}>{u.label}</span>}
          <span className="chip wait">{d.category.name}</span>
        </div>

        {flash && <div className="flash ok" role="status">{flash}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          {/* Left: what it is */}
          <div style={{ flex: "2 1 420px", display: "flex", flexDirection: "column", gap: 20 }}>
            <section className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10 }}>
                {d.photos.map((url, i) => (
                  <button key={url} onClick={() => setZoom(url)} aria-label={`Open photo ${i + 1}`} style={{ padding: 0, border: 0, background: "none", cursor: "zoom-in" }}>
                    <img src={url} alt={`Donation photo ${i + 1}`} style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 10, display: "block" }} />
                  </button>
                ))}
              </div>
              <dl style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "8px 16px", margin: 0, fontSize: 14 }}>
                {d.ai && (
                  <>
                    <dt className="muted">AI category</dt>
                    <dd style={{ margin: 0 }}>
                      {d.ai.top3.map((t) => `${catNames[t.category_id] ?? t.category_id} ${Math.round(t.p * 100)}%`).join(" · ")}
                      <div className={`small ${d.ai.category_id === d.category.id ? "muted" : ""}`} style={d.ai.category_id === d.category.id ? undefined : { color: "var(--warn)", fontWeight: 700 }}>
                        {d.ai.category_id === d.category.id ? `Donor confirmed ${d.category.name}.` : `Donor chose ${d.category.name} instead.`}
                      </div>
                    </dd>
                  </>
                )}
                <dt className="muted">Quantity</dt>
                <dd style={{ margin: 0 }}>{d.quantity}</dd>
                {d.is_food ? (
                  <>
                    <dt className="muted">Food type</dt>
                    <dd style={{ margin: 0 }}>
                      {d.food_type === "cooked" ? "Cooked" : "Dry / packed"}
                      {d.prepared_at ? ` · prepared ${dateTime(d.prepared_at)}` : ""}
                    </dd>
                  </>
                ) : (
                  <>
                    <dt className="muted">Condition</dt>
                    <dd style={{ margin: 0, textTransform: "capitalize" }}>{d.condition ?? "–"}</dd>
                  </>
                )}
                {d.description && (
                  <>
                    <dt className="muted">Description</dt>
                    <dd style={{ margin: 0 }}>{d.description}</dd>
                  </>
                )}
                <dt className="muted">Pickup window</dt>
                <dd style={{ margin: 0 }}>{windowText(d.pickup.from, d.pickup.to)}</dd>
                <dt className="muted">Pickup address</dt>
                <dd style={{ margin: 0 }}>
                  {d.pickup.address}
                  <div className="muted small">{d.pickup.location_path.join(" › ")}</div>
                  <a className="small" href={`https://www.google.com/maps?q=${d.pickup.lat},${d.pickup.lng}`} target="_blank" rel="noreferrer">Open in Google Maps</a>
                </dd>
                <dt className="muted">Donor</dt>
                <dd style={{ margin: 0 }}>
                  {d.donor.full_name} · {d.donor.phone} · {d.donor.donations_count} donation{d.donor.donations_count === 1 ? "" : "s"}
                </dd>
                {d.ngo && (
                  <>
                    <dt className="muted">{d.status === "delivered" ? "Delivered to" : "Going to"}</dt>
                    <dd style={{ margin: 0 }}>
                      <strong>{d.ngo.name}</strong>
                      <div className="muted small">{d.ngo.address} · {d.ngo.location_path.slice(-2).join(", ")}{d.ngo.phone ? ` · ${d.ngo.phone}` : ""}</div>
                      {d.ngo.location_approx
                        ? <span className="small" style={{ color: "var(--warn)" }}>Office not on the map yet: the rider should call the NGO.</span>
                        : <a className="small" href={`https://www.google.com/maps?q=${d.ngo.lat},${d.ngo.lng}`} target="_blank" rel="noreferrer">Open in Google Maps</a>}
                    </dd>
                  </>
                )}
                {d.reject_reason && (
                  <>
                    <dt className="muted">Reject reason</dt>
                    <dd style={{ margin: 0 }}>{d.reject_reason}</dd>
                  </>
                )}
              </dl>
            </section>

            {d.urgency_reasons.length > 0 && (
              <section className="card">
                <h2 style={{ margin: "0 0 4px", fontSize: 16 }}>Why it is urgent</h2>
                <p className="muted small" style={{ margin: "0 0 10px" }}>
                  Score {d.urgency_score} / 100 · rule-based{["in_review", "accepted", "rider_assigned"].includes(d.status) ? " · rises every hour the food waits" : ""}
                </p>
                {d.urgency_reasons.map((r) => (
                  <div key={r.label} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderTop: "1px solid var(--line)",
                    ...(r.label.startsWith("Warning") ? { color: "var(--urgent)", fontWeight: 700 } : {}) }}>
                    <span>{r.label}</span>
                    {r.points > 0 ? <strong>+{r.points}</strong> : null}
                  </div>
                ))}
              </section>
            )}

            {d.proofs.length > 0 && (
              <section className="card">
                <h2 style={{ margin: "0 0 10px", fontSize: 16 }}>Proof photos</h2>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 12 }}>
                  {d.proofs.map((p) => (
                    <figure key={p.url + p.kind} style={{ margin: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                      <button onClick={() => setZoom(p.url)} aria-label={`Open ${PROOF[p.kind]}`} style={{ padding: 0, border: 0, background: "none", cursor: "zoom-in" }}>
                        <img src={p.url} alt={PROOF[p.kind]} style={{ width: "100%", height: 120, objectFit: "cover", borderRadius: 10, display: "block" }} />
                      </button>
                      <figcaption className="small">
                        <strong>{PROOF[p.kind]}</strong> · {dateTime(p.at)}
                        {p.distance_km !== null && (
                          <span className={`chip ${p.distance_km > 1 ? "bad" : "ok"}`} style={{ marginLeft: 6 }}>
                            {p.distance_km > 1 ? `${p.distance_km} km away` : "At the right place"}
                          </span>
                        )}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              </section>
            )}

            <section className="card">
              <h2 style={{ margin: "0 0 10px", fontSize: 16 }}>History</h2>
              <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 10 }}>
                {d.history.map((h, i) => (
                  <li key={i}>
                    <strong>{STATUS[h.to_status].label}</strong>
                    {h.note ? ` · ${h.note}` : ""}
                    <div className="muted small">{dateTime(h.at)} · {h.by_name ?? "System"}</div>
                  </li>
                ))}
              </ol>
            </section>
          </div>

          {/* Right: decision */}
          <aside className="card" style={{ flex: "1 1 340px", display: "flex", flexDirection: "column", gap: 14 }}>
            {d.status === "in_review" ? (
              <>
                <div>
                  <h2 style={{ margin: 0, fontSize: 16 }}>Which NGO should get it?</h2>
                  <p className="muted small" style={{ margin: "4px 0 0" }}>Our rider picks it up and drops it at the NGO. NGOs that take {d.category.name.toLowerCase()}{d.food_type === "cooked" ? " and cooked food" : ""}: those working where a disaster needs this item first, then checked ones, then nearest.</p>
                </div>
                {options === null ? (
                  <p className="muted">Loading NGOs…</p>
                ) : options.length === 0 ? (
                  <div className="flash bad">
                    We know no NGO near {city} that takes this{d.food_type === "cooked" ? " cooked food" : ""}. Search the web, or <Link to="/ngos">add one you know</Link>.
                  </div>
                ) : (
                  <div role="radiogroup" aria-label="NGO" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {options.map((o) => (
                      <label
                        key={o.id}
                        style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: 12, margin: 0, borderRadius: 10, cursor: "pointer", fontWeight: 400,
                          border: ngoId === o.id ? "2px solid var(--green-700)" : "1px solid var(--line-2)", background: ngoId === o.id ? "var(--green-50)" : "#fff" }}
                      >
                        <input type="radio" name="ngo" value={o.id} checked={ngoId === o.id} onChange={() => setNgoId(o.id)} style={{ marginTop: 3 }} />
                        <span style={{ flex: 1 }}>
                          <strong style={{ color: "var(--ink)" }}>{o.name}</strong>
                          <span className="muted small" style={{ display: "block" }}>
                            {o.address} · {o.location_path.slice(-2).join(", ")}{o.phone ? ` · ${o.phone}` : ""}
                          </span>
                          <span className="small" style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                            <span className={`chip ${o.match === "same_area" || o.match === "same_city" ? "ok" : "wait"}`}>{MATCH[o.match]}</span>
                            <span className="chip wait">{o.location_approx ? "distance not known" : `${o.distance_km} km`}</span>
                            <span className="chip wait">{o.items_30d} donations / 30 days</span>
                            {o.found_by === "web_search" && <span className="chip wait" title="Found by web search: call them first">From the web</span>}
                            {o.found_by === "openstreetmap" && <span className="chip wait" title="Found on OpenStreetMap: call them first">From the map</span>}
                            {o.found_by === "ocha_3w" && <span className="chip wait" title="From OCHA 3W: office address not known, call them first">From OCHA 3W</span>}
                            {o.found_by === "import" && <span className="chip wait" title="From your imported list: call them first">From your list</span>}
                            {o.phone_confirmed && o.ban_checked
                              ? <span className="chip ok">✓ Checked</span>
                              : <span className="chip" style={{ background: "var(--warn-bg)", color: "var(--warn)" }}>{!o.ban_checked ? "Banned lists not checked" : "Not called yet"}</span>}
                          </span>
                          {o.disaster && <span className="small" style={{ display: "block", marginTop: 4, color: "var(--urgent)", fontWeight: 700 }}>{o.disaster}</span>}
                          {o.works_text && <span className="small" style={{ display: "block", marginTop: 2, color: "var(--info)" }}>{o.works_text}</span>}
                          {o.source_url && <a className="small" href={o.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Where we found it</a>}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                <button className="btn ghost" disabled={searching} onClick={searchWeb}>
                  {searching ? `Searching the web for NGOs in ${city}… (1–3 min)` : `Search the web for NGOs in ${city}`}
                </button>
                <button className="btn" disabled={busy || !ngoId} onClick={accept}>
                  {busy && !rejecting ? "Saving…" : "Accept and send to this NGO"}
                </button>

                {!rejecting ? (
                  <button className="btn danger" onClick={() => setRejecting(true)}>Reject</button>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <label htmlFor="reason" style={{ margin: 0 }}>Reason (the donor sees this)</label>
                    <textarea id="reason" className="input" style={{ height: 80, padding: 10, resize: "vertical" }} maxLength={500}
                      value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. We cannot collect cooked food this far today" />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btn danger" disabled={busy || reason.trim().length < 3} onClick={reject}>Confirm reject</button>
                      <button className="btn ghost" onClick={() => setRejecting(false)}>Cancel</button>
                    </div>
                  </div>
                )}
              </>
            ) : d.status === "accepted" ? (
              <>
                <div>
                  <h2 style={{ margin: 0, fontSize: 16 }}>Which rider?</h2>
                  <p className="muted small" style={{ margin: "4px 0 0" }}>Ranked by score: distance to pickup (40), current jobs (20), available now (15), rating (15) and vehicle size for this load (10).</p>
                </div>
                {riders === null ? (
                  <p className="muted">Loading riders…</p>
                ) : riders.length === 0 ? (
                  <div className="flash bad">No approved riders yet. <Link to="/riders">Approve a rider</Link> first.</div>
                ) : (
                  <div role="radiogroup" aria-label="Rider" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {riders.map((r) => (
                      <label key={r.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: 12, margin: 0, borderRadius: 10, cursor: "pointer", fontWeight: 400,
                        border: riderId === r.id ? "2px solid var(--green-700)" : "1px solid var(--line-2)", background: riderId === r.id ? "var(--green-50)" : "#fff" }}>
                        <input type="radio" name="rider" checked={riderId === r.id} onChange={() => setRiderId(r.id)} style={{ marginTop: 3 }} />
                        <span style={{ flex: 1 }}>
                          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <strong style={{ color: "var(--ink)", flex: 1 }}>{r.full_name}</strong>
                            <span className={`chip ${r.score >= 70 ? "ok" : r.score >= 45 ? "warn" : "wait"}`} title="Recommendation score">{r.score} / 100</span>
                          </span>
                          <span className="muted small" style={{ display: "block" }}>{r.vehicle_type} {r.vehicle_number} · {r.phone}</span>
                          <span className="small" style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                            <span className={`chip ${r.is_available ? "ok" : "wait"}`}>{r.is_available ? "Available" : "Off duty"}</span>
                            {r.distance_km !== null ? <span className="chip wait">{r.distance_km} km away</span> : <span className="chip wait">{MATCH[r.match]}</span>}
                            <span className="chip wait">{r.active_jobs} active job{r.active_jobs === 1 ? "" : "s"}</span>
                          </span>
                          {riderId === r.id && (
                            <span className="small" style={{ display: "block", marginTop: 8 }}>
                              {r.reasons.map((x) => (
                                <span key={x.label} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                                  <span className="muted">{x.label}</span>
                                  <strong>+{x.points}</strong>
                                </span>
                              ))}
                            </span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                <button className="btn" disabled={busy || !riderId} onClick={assign}>{busy ? "Saving…" : "Assign rider"}</button>
                <p className="muted small" style={{ margin: 0 }}>The donor can still cancel until a rider is assigned.</p>
              </>
            ) : (d.status === "rider_assigned" || d.status === "picked_up") && d.job ? (
              <>
                <h2 style={{ margin: 0, fontSize: 16 }}>{d.status === "picked_up" ? `On the way to ${d.ngo?.name ?? "the NGO"}` : d.job.status === "assigned" ? "Waiting for the rider to accept" : "Rider going to pickup"}</h2>
                <div>
                  <strong>{d.job.rider_name}</strong>
                  <div className="muted small">{d.job.vehicle} · {d.job.rider_phone} · assigned {dateTime(d.job.assigned_at)}</div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Link className="btn ghost small" to="/tracking">Live tracking</Link>
                  <a className="btn ghost small" href={`tel:${d.job.rider_phone}`}>Call rider</a>
                </div>
                {d.status === "rider_assigned" && (
                  !cancelling ? (
                    <button className="btn danger" onClick={() => setCancelling(true)}>Take the job off this rider</button>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <label htmlFor="creason" style={{ margin: 0 }}>Reason (the rider sees this)</label>
                      <textarea id="creason" className="input" style={{ height: 70, padding: 10 }} maxLength={500} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="e.g. Not moving for 30 minutes" />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button className="btn danger" disabled={busy || cancelReason.trim().length < 3} onClick={cancelJob}>Confirm</button>
                        <button className="btn ghost" onClick={() => setCancelling(false)}>Back</button>
                      </div>
                    </div>
                  )
                )}
              </>
            ) : d.status === "delivered" ? (
              <>
                <h2 style={{ margin: 0, fontSize: 16 }}>Delivered to {d.ngo?.name ?? "the NGO"}</h2>
                <p className="muted" style={{ margin: 0 }}>Done: the NGO gives the items to people in need. The rider's photo at the NGO is under Proof photos.</p>
              </>
            ) : (
              <>
                <h2 style={{ margin: 0, fontSize: 16 }}>{s.label}</h2>
                <p className="muted" style={{ margin: 0 }}>No action needed.</p>
              </>
            )}
          </aside>
        </div>

        {zoom && (
          <div onClick={() => setZoom(null)} role="dialog" aria-label="Photo" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.75)", display: "grid", placeItems: "center", padding: 24, zIndex: 50, cursor: "zoom-out" }}>
            <img src={zoom} alt="Donation" style={{ maxWidth: "100%", maxHeight: "100%", borderRadius: 8 }} />
          </div>
        )}
      </main>
    </>
  );
}
