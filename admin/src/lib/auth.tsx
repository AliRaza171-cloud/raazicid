import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearTokens, getRefreshToken, saveTokens, setSignedOutHandler, type TokenOut, type User } from "./api";

type AuthState = {
  status: "loading" | "signedOut" | "signedIn";
  user: User | null;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

// Runs once per page load. React dev mode mounts effects twice; spending the same
// refresh token twice would make the second call fail and sign the admin out.
let restoring: Promise<User | null> | null = null;

function restoreSession(): Promise<User | null> {
  if (!restoring) {
    const refresh = getRefreshToken();
    restoring = !refresh
      ? Promise.resolve(null)
      : api<TokenOut>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) })
          .then((data) => {
            if (data.user.role !== "admin") throw new Error("not admin");
            saveTokens(data.access_token, data.refresh_token);
            return data.user;
          })
          .catch((e) => {
            // Keep the saved session if the backend just could not be reached
            if (!(e instanceof ApiError && e.status === 0)) clearTokens();
            return null;
          });
  }
  return restoring;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);

  const signedOut = useCallback(() => {
    setUser(null);
    setStatus("signedOut");
  }, []);

  useEffect(() => {
    setSignedOutHandler(signedOut);
    let alive = true;
    restoreSession().then((u) => {
      if (!alive) return;
      if (u) {
        setUser(u);
        setStatus("signedIn");
      } else {
        signedOut();
      }
    });
    return () => {
      alive = false;
    };
  }, [signedOut]);

  const login = useCallback(async (loginId: string, password: string) => {
    const data = await api<TokenOut>("/auth/login", { method: "POST", body: JSON.stringify({ login: loginId, password }) });
    if (data.user.role !== "admin") {
      // Do not keep a donor/rider session in the admin app
      await api("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: data.refresh_token }) }).catch(() => undefined);
      throw new Error("This account is not an admin. Donors and riders use the mobile app.");
    }
    saveTokens(data.access_token, data.refresh_token);
    setUser(data.user);
    setStatus("signedIn");
  }, []);

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) await api("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }).catch(() => undefined);
    clearTokens();
    signedOut();
  }, [signedOut]);

  return <AuthContext.Provider value={{ status, user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
