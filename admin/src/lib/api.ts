// Small fetch wrapper for the RAAZICID API. Base URL comes from .env.local (VITE_API_URL).

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "raazicid_access_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: stay logged out */
  }
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body?.detail?.code ?? code;
      message = body?.detail?.message ?? (typeof body?.detail === "string" ? body.detail : message);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

// Types shared with the backend (see docs/api-contract.md)
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
