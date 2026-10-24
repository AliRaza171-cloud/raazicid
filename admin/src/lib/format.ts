import type { DonationStatus, PointType } from "./api";

export const STATUS: Record<DonationStatus, { label: string; chip: string }> = {
  in_review: { label: "In review", chip: "warn" },
  accepted: { label: "Accepted", chip: "ok" },
  rejected: { label: "Rejected", chip: "bad" },
  rider_assigned: { label: "Rider assigned", chip: "info" },
  picked_up: { label: "Picked up", chip: "info" },
  at_point: { label: "At point", chip: "info" },
  handed_out: { label: "Handed out", chip: "solid" },
  cancelled: { label: "Cancelled", chip: "wait" },
};

export const POINT_TYPES: { value: PointType; label: string }[] = [
  { value: "mosque", label: "Mosque" },
  { value: "school", label: "School" },
  { value: "community_centre", label: "Community centre" },
  { value: "relief_camp", label: "Relief camp" },
  { value: "other", label: "Other" },
];

export const pointTypeLabel = (t: string) => POINT_TYPES.find((p) => p.value === t)?.label ?? t;

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
