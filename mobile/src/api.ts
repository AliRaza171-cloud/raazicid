// Fetch wrapper for the RAAZICID API. Set EXPO_PUBLIC_API_URL in mobile/.env (see .env.example).

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://192.168.1.20:8000/api/v1";

let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => {
  accessToken = t;
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.detail?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  is_perishable: boolean;
}
