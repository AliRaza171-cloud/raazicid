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
  lat?: number | null;
  lng?: number | null;
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



export type DonationStatus =
  | "in_review" | "accepted" | "rejected" | "rider_assigned" | "picked_up" | "delivered" | "cancelled";

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
  ngo_name: string | null;
  donor_name: string | null;
  created_at: string;
}

export interface Donation extends DonationItem {
  description: string | null;
  condition: "new" | "good" | "used" | null;
  food_type: "cooked" | "dry" | null;
  prepared_at: string | null;
  urgency_reasons: { label: string; points: number }[];
  pickup: { address: string; lat: number; lng: number; location_id: string | null; location_path: string[]; from: string | null; to: string | null };
  ngo: { id: string; name: string; address: string; location_path: string[]; lat: number; lng: number; phone: string | null; location_approx: boolean } | null;
  reject_reason: string | null;
  photos: string[];
  history: { from_status: DonationStatus | null; to_status: DonationStatus; note: string | null; by_name: string | null; at: string }[];
  donor: { id: string; full_name: string; phone: string; donations_count: number };
  can_cancel: boolean;
}

export interface NgoOption {
  id: string;
  name: string;
  address: string;
  location_path: string[];
  distance_km: number;
  match: "same_area" | "same_region" | "same_city" | "same_province" | "other";
  phone: string | null;
  takes_cooked_food: boolean;
  location_approx: boolean;
  found_by: string;
  source_url: string | null;
  items_30d: number;
  phone_confirmed?: boolean;
  ban_checked?: boolean;
  registration?: string | null;
}

export interface Ngo {
  id: string;
  name: string;
  location_id: string;
  location_path: string[];
  address: string;
  lat: number;
  lng: number;
  location_approx: boolean;     // only the city centre is known: call first; the first delivery fixes it
  phone: string | null;
  website: string | null;
  about: string | null;
  takes_cooked_food: boolean;
  source_url: string | null;
  found_by: "web_search" | "admin" | string;
  is_active: boolean;
  categories: { id: number; name: string }[];   // empty = takes everything
  items_30d: number;
  created_at: string;
  place_warning?: string | null;
  phone_confirmed_at?: string | null;               // called: they take our items
  ban_checked_at?: string | null;                   // not on a banned-organisation list
  registration?: string | null;                     // e.g. PCP certified
}


