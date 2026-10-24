// How donation statuses look in the app.
import type { DonationStatus } from "./api";
import { colors } from "./theme";

export const STATUS: Record<DonationStatus, { label: string; fg: string; bg: string }> = {
  in_review: { label: "In review", fg: colors.warn, bg: colors.warnSoft },
  accepted: { label: "Accepted", fg: colors.primaryDark, bg: colors.primarySoft },
  rejected: { label: "Not accepted", fg: colors.urgent, bg: colors.urgentSoft },
  rider_assigned: { label: "Rider assigned", fg: colors.primaryDark, bg: colors.primarySoft },
  picked_up: { label: "Picked up", fg: colors.primaryDark, bg: colors.primarySoft },
  at_point: { label: "At the point", fg: colors.primaryDark, bg: colors.primarySoft },
  handed_out: { label: "Handed out", fg: "#fff", bg: colors.primary },
  cancelled: { label: "Cancelled", fg: colors.muted, bg: colors.line },
};

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-PK", { day: "numeric", month: "short" });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-PK", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

/** "Today, 4:00 – 7:00 pm" style pickup window. */
export function windowText(from: string | null, to: string | null): string {
  if (!from || !to) return "Not set";
  const a = new Date(from);
  const b = new Date(to);
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  const day =
    a.toDateString() === today.toDateString() ? "Today" : a.toDateString() === tomorrow.toDateString() ? "Tomorrow" : shortDate(from);
  const t = (d: Date) => d.toLocaleTimeString("en-PK", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${t(a)} – ${t(b)}`;
}
