import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearTokens, getRefreshToken, saveTokens, setSignedOutHandler, type TokenOut, type User } from "./api";

export type RegisterBody = {
  role: "donor" | "rider";
  full_name: string;
  phone: string;
  email?: string;
  password: string;
  location_id?: string;
  address?: string;
  rider?: { vehicle_type: "motorbike" | "rickshaw" | "pickup"; vehicle_number: string };
};

type AuthState = {
  status: "loading" | "signedOut" | "signedIn";
  user: User | null;
  login: (login: string, password: string) => Promise<void>;
  register: (body: RegisterBody) => Promise<void>;
  logout: () => Promise<void>;
  /** Reload the user from the server, e.g. to see if a rider was approved. */
  reloadUser: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);

  const signedOut = useCallback(() => {
    setUser(null);
    setStatus("signedOut");
  }, []);

  // On app start: if a refresh token is saved, use it to log back in silently.
  useEffect(() => {
    setSignedOutHandler(signedOut);
    (async () => {
      try {
        const refresh = await getRefreshToken();
        if (!refresh) return signedOut();
        const data = await api<TokenOut>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) });
        await saveTokens(data.access_token, data.refresh_token);
        setUser(data.user);
        setStatus("signedIn");
      } catch (e) {
        // Keep the saved session if the backend just could not be reached
        if (!(e instanceof ApiError && e.status === 0)) await clearTokens().catch(() => undefined);
        signedOut();
      }
    })();
  }, [signedOut]);

  // Stable function identity, so screens can safely use it in useEffect dependencies
  const reloadUser = useCallback(async () => {
    setUser(await api<User>("/me"));
  }, []);

  const finish = async (data: TokenOut) => {
    await saveTokens(data.access_token, data.refresh_token);
    setUser(data.user);
    setStatus("signedIn");
  };

  const value: AuthState = {
    status,
    user,
    login: async (login: string, password: string) => {
      const data = await api<TokenOut>("/auth/login", { method: "POST", body: JSON.stringify({ login, password }) });
      if (data.user.role === "admin") {
        throw new Error("Admins use the RAAZICID web app, not the mobile app.");
      }
      await finish(data);
    },
    register: async (body: RegisterBody) => {
      const data = await api<TokenOut>("/auth/register", { method: "POST", body: JSON.stringify(body) });
      await finish(data);
    },
    logout: async () => {
      const refresh = await getRefreshToken();
      if (refresh) {
        await api("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }).catch(() => undefined);
      }
      await clearTokens();
      signedOut();
    },
    reloadUser,
    setUser: (u: User) => setUser(u),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
