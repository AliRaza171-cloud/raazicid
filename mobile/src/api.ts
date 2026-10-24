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
  try {
    return await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  } catch {
    throw new ApiError(0, "network", `Cannot reach the server at ${API_URL}. Same Wi-Fi? Is the backend running?`);
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
