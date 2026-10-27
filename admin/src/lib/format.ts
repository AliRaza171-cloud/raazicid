import type { DonationStatus } from "./api";

export const STATUS: Record<DonationStatus, { label: string; chip: string }> = {
  in_review: { label: "In review", chip: "warn" },
  accepted: { label: "Accepted", chip: "ok" },
  rejected: { label: "Rejected", chip: "bad" },
  rider_assigned: { label: "Rider assigned", chip: "info" },
  picked_up: { label: "Picked up", chip: "info" },
  delivered: { label: "Delivered to NGO", chip: "solid" },
  cancelled: { label: "Cancelled", chip: "wait" },
};

export const date = (iso: string) => new Date(iso).toLocaleDateString("en-PK", { day: "numeric", month: "short", year: "numeric" });

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-PK", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** "Today, 4:00 pm – 7:00 pm" style pickup window. */
export function windowText(from: string | null, to: string | null): string {
  if (!from || !to) return "Not set";
  const a = new Date(from);
  const b = new Date(to);
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 86400000);
  const day = a.toDateString() === now.toDateString() ? "Today" : a.toDateString() === tomorrow.toDateString() ? "Tomorrow" : date(from);
  const t = (d: Date) => d.toLocaleTimeString("en-PK", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${t(a)} – ${t(b)}`;
}

export function urgencyChip(score: number | null): { cls: string; label: string } {
  if (score === null) return { cls: "wait", label: "–" };
  if (score >= 70) return { cls: "bad", label: `Urgent · ${score}` };
  if (score >= 40) return { cls: "warn", label: `High · ${score}` };
  return { cls: "ok", label: `Normal · ${score}` };
}

// ---------- Phase 6 ----------

export const LEVELS = [
  { label: "None", cls: "lv0" },
  { label: "Some", cls: "lv1" },
  { label: "High", cls: "lv2" },
  { label: "Urgent", cls: "lv3" },
];

/** Short column names for the area × category grid. */
export const SHORT_CAT: Record<number, string> = {
  1: "Food", 2: "Ration", 3: "Clothes", 4: "Blankets", 5: "Winter", 6: "Hygiene",
  7: "Baby", 8: "Household", 9: "School", 10: "Books", 11: "Mobility", 12: "Relief",
};

export const ALERT_TYPES: Record<string, string> = {
  flood: "Flood", earthquake: "Earthquake", cyclone: "Cyclone", drought: "Drought", heatwave: "Heatwave",
  cold_wave: "Cold wave", heavy_rain: "Heavy rain", other: "Other",
};

export const SEVERITY: Record<string, { label: string; chip: string }> = {
  severe: { label: "Severe", chip: "bad" },
  moderate: { label: "Moderate", chip: "warn" },
  watch: { label: "Watch", chip: "info" },
};

export const ALERT_STATUS: Record<string, { label: string; chip: string }> = {
  unconfirmed: { label: "Needs checking", chip: "warn" },
  confirmed: { label: "Confirmed", chip: "ok" },
  handled: { label: "Handled", chip: "wait" },
  dismissed: { label: "Dismissed", chip: "wait" },
};

export const FIGURES: Record<string, string> = {
  people_affected: "People affected", families_affected: "Families affected", deaths: "Deaths",
  injured: "Injured", houses_damaged: "Houses damaged",
};

export function ago(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
}
