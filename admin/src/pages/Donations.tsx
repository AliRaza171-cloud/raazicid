import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import LocationSelect from "../components/LocationSelect";
import { PageHeader } from "../components/Layout";
import { api, type Category, type DonationItem, type DonationStatus } from "../lib/api";
import { STATUS, date, urgencyChip } from "../lib/format";

type Counts = Record<DonationStatus, number>;
type Sort = "urgency" | "newest" | "oldest";

const TABS: { key: DonationStatus | "all"; label: string }[] = [
  { key: "in_review", label: "In review" },
  { key: "accepted", label: "Accepted" },
  { key: "rider_assigned", label: "Rider assigned" },
  { key: "picked_up", label: "Picked up" },
  { key: "at_point", label: "At point" },
  { key: "handed_out", label: "Handed out" },
  { key: "rejected", label: "Rejected" },
  { key: "cancelled", label: "Cancelled" },
  { key: "all", label: "All" },
];

const PAGE = 20;

export default function Donations() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<DonationStatus | "all">("in_review");
  const [counts, setCounts] = useState<Counts | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("urgency");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<DonationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Counts>("/admin/donations/counts").then(setCounts).catch(() => undefined);
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const p = new URLSearchParams({ sort, limit: String(PAGE), offset: String(offset) });
    if (tab !== "all") p.set("status", tab);
    if (categoryId) p.set("category_id", categoryId);
    if (locationId) p.set("location_id", locationId);
    if (search) p.set("q", search);
    api<{ items: DonationItem[]; total: number }>(`/admin/donations?${p}`)
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tab, categoryId, locationId, sort, search, offset]);

  useEffect(load, [load]);

  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    setOffset(0);
    set(v);
  };

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setSearch(q.trim());
  };

  const tabCount = (key: DonationStatus | "all") => {
    if (!counts) return "–";
    if (key === "all") return Object.values(counts).reduce((a, b) => a + b, 0);
    return counts[key];
  };

  return (
    <>
      <PageHeader title="Donations" sub="Review new donations and send each one to a distribution point.">
        <form onSubmit={submitSearch} style={{ display: "flex", gap: 8 }}>
          <input className="input" style={{ width: 260 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, donor name or phone" aria-label="Search donations" />
          <button className="btn" type="submit">Search</button>
        </form>
      </PageHeader>
      <main className="page">
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "btn" : "btn ghost"} onClick={() => reset(setTab)(t.key)}>
              {t.label}
              <span style={{ marginLeft: 8, opacity: 0.8 }}>{tabCount(t.key)}</span>
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select className="select" aria-label="Category" value={categoryId} onChange={(e) => reset(setCategoryId)(e.target.value)}>
            <option value="">All categories</option>
            {cats.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <LocationSelect compact onChange={(id) => reset(setLocationId)(id)} />
          <select className="select" aria-label="Sort" value={sort} onChange={(e) => reset(setSort)(e.target.value as Sort)} style={{ marginLeft: "auto" }}>
            <option value="urgency">Most urgent first</option>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </div>

        <section className="card" style={{ padding: 0, overflowX: "auto" }}>
          {error ? (
            <p style={{ padding: 18, color: "var(--urgent)", fontWeight: 600 }}>{error}</p>
          ) : loading ? (
            <p style={{ padding: 18 }} className="muted">Loading donations…</p>
          ) : items.length === 0 ? (
            <p style={{ padding: 18 }} className="muted">No donations match these filters.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Donation</th>
                  <th>Donor</th>
                  <th>Pickup area</th>
                  <th>Created</th>
                  <th>Urgency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((d) => {
                  const u = urgencyChip(d.urgency_score);
                  const s = STATUS[d.status];
                  return (
                    <tr key={d.id} className="click" onClick={() => navigate(`/donations/${d.id}`)}>
                      <td className="muted">{d.ref}</td>
                      <td>
                        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          {d.photo_url ? <img src={d.photo_url} alt="" style={{ width: 40, height: 40, borderRadius: 8, objectFit: "cover" }} /> : null}
                          <div>
                            <a href={`/donations/${d.id}`} onClick={(e) => { e.preventDefault(); navigate(`/donations/${d.id}`); }} style={{ fontWeight: 700, color: "var(--ink)", textDecoration: "none" }}>
                              {d.title}
                            </a>
                            <div className="muted small">{d.category.name} · {d.quantity}</div>
                          </div>
                        </div>
                      </td>
                      <td>{d.donor_name}</td>
                      <td>{d.pickup_area.join(", ") || "–"}</td>
                      <td>{date(d.created_at)}</td>
                      <td><span className={`chip ${u.cls}`}>{u.label}</span></td>
                      <td><span className={`chip ${s.chip}`}>{s.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {total > PAGE && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", borderTop: "1px solid var(--line)" }}>
              <span className="muted small">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button className="btn ghost small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </span>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
