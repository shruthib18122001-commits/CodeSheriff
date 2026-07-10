import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { setToken } from "../lib/auth";

function Callback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const token = params.get("token");
    if (token) {
      setToken(token);
      navigate("/dashboard", { replace: true });
    } else {
      navigate("/", { replace: true });
    }
  }, [params, navigate]);

  return (
    <div className="empty-state" style={{ height: "100vh" }}>
      <span className="spinner" />
      <p>Signing you in…</p>
    </div>
  );
}

export default Callback;
