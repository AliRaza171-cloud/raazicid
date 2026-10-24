import { createContext, useContext, useState, type ReactNode } from "react";

export type Role = "donor" | "rider";

type AuthState = {
  role: Role | null;
  riderApproved: boolean;
  /** Phase 1 demo login. Phase 2 replaces this with POST /auth/login + SecureStore tokens. */
  signInDemo: (role: Role, riderApproved?: boolean) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role | null>(null);
  const [riderApproved, setRiderApproved] = useState(true);
  return (
    <AuthContext.Provider
      value={{
        role,
        riderApproved,
        signInDemo: (r: Role, approved = true) => {
          setRiderApproved(approved);
          setRole(r);
        },
        signOut: () => setRole(null),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
