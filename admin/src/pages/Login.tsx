import { useNavigate } from "react-router-dom";

/** Phase 2 wires this to POST /auth/login. For now it just opens the dashboard. */
export default function Login() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexWrap: "wrap" }}>
      <section style={{ flex: "1 1 480px", background: "var(--green-900)", color: "#fff", padding: "56px 64px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 16 }}>
        <span style={{ fontSize: 20, fontWeight: 800 }}>RAAZICID</span>
        <h1 style={{ margin: 0, fontSize: 40, lineHeight: 1.15 }}>From a donor's home to the families who need it most.</h1>
      </section>
      <section style={{ flex: "1 1 480px", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <form
          style={{ width: "100%", maxWidth: 400, display: "flex", flexDirection: "column", gap: 16 }}
          onSubmit={(e) => {
            e.preventDefault();
            navigate("/");
          }}
        >
          <h2 style={{ margin: 0, fontSize: 28 }}>Admin sign in</h2>
          <div>
            <label htmlFor="email">Email</label>
            <input id="email" className="input" type="email" placeholder="admin@raazicid.pk" />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input id="password" className="input" type="password" />
          </div>
          <button className="btn" type="submit">Sign in</button>
        </form>
      </section>
    </div>
  );
}
