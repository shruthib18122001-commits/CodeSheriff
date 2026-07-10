import { Link } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { useRepos } from "../lib/useRepo";

function Dashboard() {
  const { repos, loading } = useRepos();

  return (
    <div className="app-shell">
      <Sidebar linkTo="chat" />

      <div className="main-panel">
        <div className="main-panel-header">
          <h2>Dashboard</h2>
        </div>
        <div className="main-panel-body">
          {loading ? (
            <p className="chat-loading">Loading…</p>
          ) : repos.length === 0 ? (
            <div className="empty-state">
              <h3>No repos connected yet</h3>
              <p>Use "+ Connect" in the sidebar to add your first GitHub repo.</p>
            </div>
          ) : (
            <div className="feature-grid" style={{ margin: 0, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
              {repos.map((repo) => (
                <div className="feature-card" key={repo.id}>
                  <h3 style={{ fontFamily: "var(--font-mono)", fontSize: 15 }}>{repo.github_full_name}</h3>
                  <p>
                    Status: <span className={`status-label`}>{repo.index_status}</span>
                  </p>
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <Link className="btn btn-primary btn-sm" to={`/repo/${repo.id}/chat`}>
                      Ask questions
                    </Link>
                    <Link className="btn btn-outline btn-sm" to={`/repo/${repo.id}/architecture`}>
                      Architecture
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
