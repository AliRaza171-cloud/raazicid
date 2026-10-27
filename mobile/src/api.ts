// RAAZICID API client: adds the login token, refreshes it once when it expires, and turns
// errors into readable messages. Set EXPO_PUBLIC_API_URL in mobile/.env (see .env.example).
import * as SecureStore from "expo-secure-store";

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://192.168.1.20:8000/api/v1";

const ACCESS_KEY = "raazicid_access";
const REFRESH_KEY = "raazicid_refresh";

let accessToken: string | null = null;
let onSignedOut: (() => void) | null = null;

/** The auth provider registers this so an expired session sends the user back to login. */
export function setSignedOutHandler(fn: () => void) {
  onSignedOut = fn;
}

export async function saveTokens(access: string, refresh: string) {
  accessToken = access;
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

export async function clearTokens() {
  accessToken = null;
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function readError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Something went wrong (${res.status})`;
  try {
    const body = await res.json();
    const d = body?.detail;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      code = d.code ?? code;
      message = d.message ?? message;
    } else if (Array.isArray(d) && d.length) {
      // FastAPI validation errors: show the first one in plain words
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
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  // Without a timeout a wrong IP leaves the app spinning for minutes
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    return await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...headers, ...(init.headers as Record<string, string>) },
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, "network", `Cannot reach the server at ${API_URL}. Is the phone on the same Wi-Fi as the laptop, and is the backend running with --host 0.0.0.0?`);
  } finally {
    clearTimeout(timer);
  }
}

let refreshing: Promise<boolean> | null = null;

/** Try to get a new access token with the saved refresh token. Only one refresh runs at a time. */
async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const refresh = await getRefreshToken();
      if (!refresh) return false;
      const res = await rawFetch("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }, null);
      if (!res.ok) return false;
      const data = await res.json();
      await saveTokens(data.access_token, data.refresh_token);
      return true;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!accessToken) accessToken = await SecureStore.getItemAsync(ACCESS_KEY);
  let res = await rawFetch(path, init, accessToken);
  if (res.status === 401 && accessToken && !path.startsWith("/auth/")) {
    if (await tryRefresh()) {
      res = await rawFetch(path, init, accessToken);
    } else {
      await clearTokens();
      onSignedOut?.();
    }
  }
  if (!res.ok) throw await readError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Shared types (see docs/api-contract.md) ----

export type Role = "donor" | "rider" | "admin";
export type RiderStatus = "pending" | "approved" | "rejected" | "suspended";
export type DocType = "cnic_front" | "cnic_back" | "driving_licence" | "vehicle_registration";

export interface User {
  id: string;
  role: Role;
  full_name: string;
  phone: string;
  email: string | null;
  location_id: string | null;
  location_path: string[];
  address: string | null;
  rider_status: RiderStatus | null;
  rider_note: string | null;
  created_at: string;
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

export interface RiderDoc {
  id: string;
  doc_type: DocType;
  file_url: string;
  created_at: string;
}

export type DonationStatus =
  | "in_review" | "accepted" | "rejected" | "rider_assigned" | "picked_up" | "delivered" | "cancelled";

export interface DonationListItem {
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
  ngo_name: string | null;
  created_at: string;
}

export interface Donation extends DonationListItem {
  description: string | null;
  condition: "new" | "good" | "used" | null;
  food_type: "cooked" | "dry" | null;
  prepared_at: string | null;
  pickup: { address: string; lat: number; lng: number; location_path: string[]; from: string | null; to: string | null };
  ngo: { id: string; name: string; address: string; location_path: string[]; phone: string | null } | null;   // the NGO our rider drops it at
  reject_reason: string | null;
  photos: string[];
  history: { from_status: DonationStatus | null; to_status: DonationStatus; note: string | null; by_name: string | null; at: string }[];
  can_cancel: boolean;
  job: { id: string; status: JobStatus; rider_id: string; rider_name: string; rider_phone: string; vehicle: string; assigned_at: string } | null;
  proofs: { kind: "pickup_proof" | "delivery_proof"; url: string; lat: number | null; lng: number | null; distance_km: number | null; at: string }[];
}

export type JobStatus = "assigned" | "accepted" | "declined" | "picked_up" | "delivered" | "cancelled";

export interface Place {
  name: string | null;
  address: string;
  lat: number;
  lng: number;
  area: string[];
  contact_name: string | null;
  contact_phone: string | null;
  approx?: boolean;   // NGO office not on the map yet: call them for directions
}

export interface Job {
  id: string;
  status: JobStatus;
  assigned_at: string;
  accepted_at: string | null;
  picked_up_at: string | null;
  delivered_at: string | null;
  decline_reason: string | null;
  donation_id: string;
  donation_ref: string;
  donation_status: DonationStatus;
  title: string;
  category: string;
  quantity: number;
  description: string | null;
  is_food: boolean;
  food_type: "cooked" | "dry" | null;
  prepared_at: string | null;
  urgency_score: number | null;
  photos: string[];
  pickup: Place;
  pickup_from: string | null;
  pickup_to: string | null;
  ngo: Place | null;          // where to drop it
  donor_name: string;
  donor_phone: string | null;
  trip_km: number | null;
}

export interface RiderSummary {
  is_available: boolean;
  active_jobs: number;
  done_today: number;
  done_total: number;
  rating_avg: number | null;
}

export interface LatLngAt {
  lat: number;
  lng: number;
  at: string;
}

export interface Tracking {
  donation_id: string;
  donation_status: DonationStatus;
  job_id: string | null;
  job_status: JobStatus | null;
  heading_to: "pickup" | "ngo" | null;
  rider: { full_name: string; phone: string; vehicle_type: string; vehicle_number: string } | null;
  last: LatLngAt | null;
  path: LatLngAt[];
  stalled: boolean;
  pickup: Place;
  ngo: Place | null;
}

// ---------- Phase 6: needs by area and disaster alerts ----------

export interface NeedReason {
  why: string;
  source: string;
  date: string | null;
  place?: string | null;
  points: number;
  fresh?: "new" | "recent" | "old";   // last 3 months / this year / over a year
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
  level: string;
  lat: number | null;
  lng: number | null;
  has_children: boolean;
  max_level: number;
  needs: AreaNeed[];
}

export interface AreaNeeds {
  place: { id: string; name: string; level: string; parent_id: string | null } | null;
  summary: AreaNeed[] | null;
  children: AreaRow[];
  computed_at: string | null;
}

export interface DisasterAlert {
  id: string;
  type: "flood" | "earthquake" | "cyclone" | "drought" | "heatwave" | "cold_wave" | "heavy_rain" | "other";
  severity: "watch" | "moderate" | "severe";
  title: string;
  summary: string | null;
  figures: Record<string, number>;
  started_at: string | null;
  created_at: string;
  places: { id: string; name: string; path: string[] }[];
  needs: { category_id: number; name: string; quantity_needed: number | null; quantity_pledged: number }[];
  sources: { title: string; url: string | null; publisher: string | null }[];
  ngos: { id: string; name: string; city: string }[];   // NGOs our riders deliver to near the disaster
}

// ---------- Phase 6B: appeals and notifications ----------

export interface Appeal {
  id: string;
  title: string;
  message: string;
  place: string[];
  categories: { id: number; name: string }[];
  provinces: string[];
  sent_at: string | null;
  ends_at: string | null;
}

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, any>;
  created_at: string;
  read: boolean;
}
