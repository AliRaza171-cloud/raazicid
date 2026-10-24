import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (status === "signedIn") return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(id.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexWrap: "wrap" }}>
      <section style={{ flex: "1 1 480px", background: "var(--green-900)", color: "#fff", padding: "56px 64px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 16 }}>
        <span style={{ fontSize: 20, fontWeight: 800 }}>RAAZICID</span>
        <h1 style={{ margin: 0, fontSize: 40, lineHeight: 1.15 }}>From a donor's home to the families who need it most.</h1>
      </section>
      <section style={{ flex: "1 1 480px", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <form onSubmit={submit} style={{ width: "100%", maxWidth: 400, display: "flex", flexDirection: "column", gap: 16 }}>
          <h2 style={{ margin: 0, fontSize: 28 }}>Admin sign in</h2>
          <p style={{ margin: 0, color: "var(--muted)" }}>For RAAZICID staff only.</p>
          <div>
            <label htmlFor="login">Email or phone</label>
            <input id="login" className="input" value={id} onChange={(e) => setId(e.target.value)} placeholder="admin@raazicid.pk" autoComplete="username" required />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input id="password" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && (
            <div role="alert" className="card" style={{ background: "var(--urgent-bg)", borderColor: "#edb49e", color: "var(--urgent)", fontWeight: 600 }}>
              {error}
            </div>
          )}
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}
