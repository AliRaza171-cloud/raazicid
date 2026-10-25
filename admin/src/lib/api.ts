// Fetch wrapper for the RAAZICID API: adds the token, refreshes it once on 401, readable errors.

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "raazicid_admin_access";
const REFRESH_KEY = "raazicid_admin_refresh";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    /* storage blocked: session lasts until the tab closes */
  }
}

let memAccess: string | null = read(ACCESS_KEY);
let memRefresh: string | null = read(REFRESH_KEY);
let onSignedOut: (() => void) | null = null;

export function setSignedOutHandler(fn: () => void) {
  onSignedOut = fn;
}

export function saveTokens(access: string, refresh: string) {
  memAccess = access;
  memRefresh = refresh;
  write(ACCESS_KEY, access);
  write(REFRESH_KEY, refresh);
}

export function clearTokens() {
  memAccess = null;
  memRefresh = null;
  write(ACCESS_KEY, null);
  write(REFRESH_KEY, null);
}

export const getRefreshToken = () => memRefresh;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function readError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Something went wrong (${res.status})`;
  try {
    const d = (await res.json())?.detail;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      code = d.code ?? code;
      message = d.message ?? message;
    } else if (Array.isArray(d) && d.length) {
      code = "validation_error";
      message = String(d[0]?.msg ?? message).replace(/^Value error, /, "");
    } else if (typeof d === "string") {
      message = d;
    }
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, code, message);
}

async function rawFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  // FormData (file uploads) sets its own multipart Content-Type
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  try {
    return await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      if (!memRefresh) return false;
      const res = await rawFetch("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: memRefresh }) }, null);
      if (!res.ok) return false;
      const data = await res.json();
      saveTokens(data.access_token, data.refresh_token);
      return true;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res = await rawFetch(path, init, memAccess);
  if (res.status === 401 && memAccess && !path.startsWith("/auth/")) {
    if (await tryRefresh()) {
      res = await rawFetch(path, init, memAccess);
    } else {
      clearTokens();
      onSignedOut?.();
    }
  }
  if (!res.ok) throw await readError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Shared types (see docs/api-contract.md) ----

export type RiderStatus = "pending" | "approved" | "rejected" | "suspended";

export interface User {
  id: string;
  role: "donor" | "rider" | "admin";
  full_name: string;
  phone: string;
  email: string | null;
  location_path: string[];
}

export interface TokenOut {
  user: User;
  access_token: string;
  refresh_token: string;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  is_perishable: boolean;
}

export interface LocationItem {
  id: string;
  name: string;
  level: "province" | "city" | "region" | "area";
  parent_id: string | null;
}

export interface RiderItem {
  id: string;
  full_name: string;
  phone: string;
  vehicle_type: "motorbike" | "rickshaw" | "pickup";
  vehicle_number: string;
  status: RiderStatus;
  location_path: string[];
  documents_count: number;
  created_at: string;
}

export interface RiderDetail extends RiderItem {
  email: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  documents: { id: string; doc_type: string; file_url: string; created_at: string }[];
  ai_review: { summary: string; checks: { label: string; ok: boolean | null; detail: string }[]; model: string; created_at: string } | null;
}

export interface AiStatus {
  classifier: "ready" | "not_installed" | "no_model";
  version: string | null;
  accuracy: number | null;
  own_photo_accuracy: number | null;
  document_review: boolean;
}

export interface AiStats {
  donations_with_ai: number;
  top1_kept: number;
  top3_hit: number;
  top1_rate: number | null;
  top3_rate: number | null;
  by_category: { category_id: number; name: string; suggested: number; kept: number }[];
}

export type DonationStatus =
  | "in_review" | "accepted" | "rejected" | "rider_assigned" | "picked_up" | "at_point" | "handed_out" | "cancelled";

export interface DonationItem {
  id: string;
  ref: string;
  title: string;
  category: { id: number; name: string };
  quantity: number;
  status: DonationStatus;
  is_food: boolean;
  urgency_score: number | null;
  photo_url: string | null;
  pickup_area: string[];
  point_name: string | null;
  donor_name: string | null;
  created_at: string;
}

export interface Donation extends DonationItem {
  description: string | null;
  condition: "new" | "good" | "used" | null;
  food_type: "cooked" | "dry" | null;
  prepared_at: string | null;
  urgency_reasons: { label: string; points: number }[];
  pickup: { address: string; lat: number; lng: number; location_path: string[]; from: string | null; to: string | null };
  point: { id: string; name: string; address: string; location_path: string[]; lat: number; lng: number } | null;
  reject_reason: string | null;
  photos: string[];
  history: { from_status: DonationStatus | null; to_status: DonationStatus; note: string | null; by_name: string | null; at: string }[];
  donor: { id: string; full_name: string; phone: string; donations_count: number };
  ai: { category_id: number; confidence: number; top3: { category_id: number; p: number }[] } | null;
  can_cancel: boolean;
  job: { id: string; status: JobStatus; rider_id: string; rider_name: string; rider_phone: string; vehicle: string; assigned_at: string } | null;
  proofs: { kind: "pickup_proof" | "delivery_proof" | "distribution_proof"; url: string; lat: number | null; lng: number | null; distance_km: number | null; at: string }[];
  hand_out: { quantity: number; families_served: number | null; photo_url: string | null; note: string | null; by_name: string; at: string } | null;
}

export type JobStatus = "assigned" | "accepted" | "declined" | "picked_up" | "delivered" | "cancelled";

export interface RiderOption {
  id: string;
  full_name: string;
  phone: string;
  vehicle_type: string;
  vehicle_number: string;
  is_available: boolean;
  active_jobs: number;
  match: "same_area" | "same_region" | "same_city" | "same_province" | "other";
  distance_km: number | null;
  last_seen_at: string | null;
  rating_avg: number | null;
  score: number;
  reasons: { label: string; points: number }[];
}

export interface Place {
  name: string | null;
  address: string;
  lat: number;
  lng: number;
  area: string[];
  contact_name: string | null;
  contact_phone: string | null;
}

export interface LatLngAt {
  lat: number;
  lng: number;
  at: string;
}

export interface TrackingItem {
  job_id: string;
  job_status: JobStatus;
  donation_id: string;
  donation_ref: string;
  title: string;
  rider_name: string;
  rider_phone: string;
  heading_to: "pickup" | "point";
  last: LatLngAt | null;
  minutes_since_ping: number | null;
  stalled: boolean;
  pickup: Place;
  point: Place | null;
}

export interface Tracking {
  job_status: JobStatus | null;
  heading_to: "pickup" | "point" | null;
  last: LatLngAt | null;
  path: LatLngAt[];
  stalled: boolean;
  pickup: Place;
  point: Place | null;
}

export interface PointOption {
  id: string;
  name: string;
  type: string;
  location_path: string[];
  distance_km: number;
  match: "same_area" | "same_region" | "same_city" | "same_province" | "other";
  same_day_food: boolean;
  items_30d: number;
}

export type PointType = "mosque" | "school" | "community_centre" | "relief_camp" | "other";

export interface Point {
  id: string;
  name: string;
  type: PointType;
  location_id: string;
  location_path: string[];
  address: string;
  lat: number;
  lng: number;
  contact_name: string | null;
  contact_phone: string | null;
  same_day_food: boolean;
  is_active: boolean;
  closes_at: string | null;
  categories: { id: number; name: string }[];
  items_30d: number;
  open_requests: number;
  created_at: string;
}

export interface PointRequest {
  id: string;
  category: { id: number; name: string };
  quantity: number;
  note: string | null;
  status: "open" | "fulfilled" | "cancelled";
  requested_by_name: string;
  created_at: string;
}

export interface PointDetail extends Point {
  requests: PointRequest[];
}

// ---------- Phase 6: needs by area, disaster alerts, data sources ----------

export interface NeedReason {
  why: string;
  source: string;
  date: string | null;
  place?: string | null;
  points: number;
  alert_id?: string;
}

export interface AreaNeed {
  category_id: number;
  name: string;
  level: 0 | 1 | 2 | 3;
  level_name: "none" | "some" | "high" | "urgent";
  score: number;
  reasons: NeedReason[];
}

export interface AreaRow {
  id: string;
  name: string;
  level: LocationItem["level"];
  lat: number | null;
  lng: number | null;
  has_children: boolean;
  max_level: number;
  needs: AreaNeed[];
  orgs: number;                          // organisations working here (OCHA 3W)
  who_works: Record<string, string[]>;   // sector -> organisations
  neglected: string[];                   // categories in high need with nobody working on them
}

export interface AreaNeeds {
  place: { id: string; name: string; level: string; parent_id: string | null } | null;
  summary: AreaNeed[] | null;
  children: AreaRow[];
  computed_at: string | null;
  has_3w: boolean;
}

export type AlertType = "flood" | "earthquake" | "cyclone" | "drought" | "heatwave" | "cold_wave" | "heavy_rain" | "other";
export type AlertSeverity = "watch" | "moderate" | "severe";
export type AlertStatus = "unconfirmed" | "confirmed" | "handled" | "dismissed";

export interface Alert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  summary: string | null;
  figures: Record<string, number>;
  started_at: string | null;
  created_at: string;
  confirmed_at: string | null;
  from_gdacs: boolean;
  places: { id: string; name: string; path: string[]; lat: number | null; lng: number | null }[];
  needs: { category_id: number; name: string; quantity_needed: number | null; quantity_pledged: number }[];
  sources: { title: string; url: string | null; publisher: string | null; published_at: string | null }[];
  camps: { id: string; name: string; is_active: boolean }[];
}

export interface DataSource {
  kind: string;
  name: string;
  is_enabled: boolean;
  every_minutes: number | null;
  last_run_at: string | null;
  last_status: string | null;
  can_run: boolean;
}

// ---------- Phase 6B: report library, need finder, appeals ----------

export type ReportStatus = "new" | "tagged" | "needs_review" | "archived";

export interface ReportItem {
  id: string;
  title: string;
  publisher: string | null;
  url: string | null;
  source: string;
  source_kind: string;
  status: ReportStatus;
  published_at: string | null;
  created_at: string;
  chunks: number;
  places: string[];
  has_text: boolean;
}

export interface ChunkTag { id: string; name: string; path: string[]; confidence: number; confirmed: boolean }

export interface ReportChunk {
  id: string;
  index: number;
  page: number | null;
  text: string;
  has_embedding: boolean;
  places: ChunkTag[];
}

export interface ReportDetail extends ReportItem {
  chunk_list: ReportChunk[];
}

export interface RagStatus {
  embeddings: { available: boolean; model: string; note: string };
  claude: boolean;
  reliefweb: boolean;
  reports: number;
  chunks: number;
  chunks_with_vectors: number;
  search: string;
}

export interface FinderSource {
  id: string;
  report_id: string;
  title: string;
  publisher: string | null;
  url: string | null;
  page: number | null;
  date: string | null;
  text: string;
  places: string[];
  found_by: string[];
  cited?: boolean;
}

export interface FinderArea {
  name: string;
  need: "urgent" | "high" | "some";
  categories: string[];
  reason: string;
  sources: string[];
  location_id: string | null;
  path: string[];
  our_level: number | null;
}

export interface FinderAnswer {
  question: string;
  place: string | null;
  category: string | null;
  answer: string;
  summary: string;      // one plain sentence
  points: string[];     // up to 4 short points, each with [S1] / [D1] / [Web]
  note: string;         // what the sources do not cover
  areas: FinderArea[];
  confidence: "low" | "medium" | "high";
  sources: FinderSource[];
  facts: { id: string; location_id: string; place: string; category: string; level: string; score: number; why: string; kind?: "3w"; text?: string }[];
  reliefweb_checked?: boolean;
  reliefweb_found?: number;
  web_results: { url: string; title: string; snippet: string; cited: boolean; age?: string }[];
  used_web: boolean;
  web_mode: "auto" | "always" | "off";
  ai: boolean;
  model: string;
}

export interface Appeal {
  id: string;
  title: string;
  message: string;
  place: string[];
  location_id: string;
  categories: { id: number; name: string }[];
  provinces: string[];
  alert_id: string | null;
  sent_at: string | null;
  ends_at: string | null;
  live: boolean;
  reached: number;
}
