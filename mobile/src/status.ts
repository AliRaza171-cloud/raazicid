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

export function minutesAgo(iso: string): string {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? "just now" : m === 1 ? "1 min ago" : m < 60 ? `${m} min ago` : `${Math.floor(m / 60)} h ago`;
}

/** Opens Google Maps turn-by-turn directions to a place. */
export function directionsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=driving`;
}

/** Straight-line distance in km. */
export function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b.lat - a.lat) / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(r(b.lng - a.lng) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}
