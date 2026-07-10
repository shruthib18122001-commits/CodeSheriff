import { useEffect, useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPlan, PLAN_QUERY_LIMITS, type PlanInfo } from "../lib/api";
import { logout } from "../lib/auth";
import { useRepos } from "../lib/useRepo";
import ConnectRepoModal from "./ConnectRepoModal";

interface Props {
  activeRepoId?: string;
  /** Which page tapping a repo should navigate to. */
  linkTo?: "chat" | "architecture";
}

function Sidebar({ activeRepoId, linkTo = "chat" }: Props) {
  const { repos, loading, error, connect, remove } = useRepos();
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchPlan()
      .then(setPlan)
      .catch(() => setPlan(null));
  }, []);

  async function handleDelete(e: MouseEvent, repoId: string) {
    e.stopPropagation();
    if (!window.confirm("Delete this repo and all its indexed data?")) return;
    await remove(repoId);
    if (activeRepoId === repoId) navigate("/dashboard");
  }

  const limit = plan ? PLAN_QUERY_LIMITS[plan.plan] : null;
  const remaining = plan && limit ? Math.max(limit - plan.queries_this_month, 0) : null;

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand" style={{ fontSize: 15 }}>
          Code<span className="brand-mark">Sheriff</span>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          + Connect
        </button>
      </div>

      <div className="sidebar-repos">
        {loading && <p className="chat-loading">Loading repos…</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && repos.length === 0 && <p className="chat-loading">No repos connected yet.</p>}

        {repos.map((repo) => (
          <div
            key={repo.id}
            className={`repo-item${repo.id === activeRepoId ? " active" : ""}`}
            onClick={() => navigate(`/repo/${repo.id}/${linkTo}`)}
          >
            <span className="repo-item-name">{repo.github_full_name}</span>
            <div className="repo-item-row">
              <span className={`status-dot ${repo.index_status}`} />
              <span className="status-label">{repo.index_status}</span>
              <button
                className="btn-danger btn-sm"
                style={{ marginLeft: "auto", border: "none", padding: "2px 6px" }}
                onClick={(e) => handleDelete(e, repo.id)}
                title="Delete repo"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        {plan && (
          <>
            <span className={`plan-badge ${plan.plan}`}>{plan.plan}</span>
            {remaining !== null && (
              <p className="queries-remaining">
                {remaining} / {limit} queries left this month
              </p>
            )}
          </>
        )}
        <button className="btn btn-outline btn-sm" style={{ marginTop: 10, width: "100%" }} onClick={logout}>
          Sign out
        </button>
      </div>

      {showModal && (
        <ConnectRepoModal
          onClose={() => setShowModal(false)}
          onConnect={(name) => connect(name)}
        />
      )}
    </aside>
  );
}

export default Sidebar;
