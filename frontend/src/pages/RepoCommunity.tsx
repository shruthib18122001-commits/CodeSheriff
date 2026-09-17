import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import RepoTabs from "../components/RepoTabs";
import Sidebar from "../components/Sidebar";
import { createCommunityPost, fetchCommunityPosts, type CommunityPost } from "../lib/api";

function RepoCommunity() {
  const { repoId } = useParams<{ repoId: string }>();
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      setPosts(await fetchCommunityPosts(repoId));
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Could not load community posts.");
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handlePost() {
    if (!repoId || !content.trim() || posting) return;
    setPosting(true);
    setError(null);
    try {
      const post = await createCommunityPost(repoId, content.trim());
      setPosts((prev) => [post, ...prev]);
      setContent("");
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Could not post. Please try again.");
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activeRepoId={repoId} linkTo="community" />
      <div className="main-panel">
        <div className="main-panel-header">
          <h2>Community</h2>
          <RepoTabs active="community" />
        </div>
        <div className="main-panel-body">
          <p style={{ color: "var(--color-text-dim)", fontSize: 13, margin: "0 0 16px" }}>
            Ask questions and share notes with everyone else exploring this repo in CodeSheriff.
          </p>

          <div className="community-composer">
            <textarea
              placeholder="Ask a question or share something about this repo..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={posting}
              rows={3}
            />
            <button className="btn btn-primary" onClick={handlePost} disabled={posting || !content.trim()}>
              {posting ? "Posting…" : "Post"}
            </button>
          </div>

          {error && <p className="error-text">{error}</p>}

          {loading ? (
            <p className="chat-loading">Loading…</p>
          ) : posts.length === 0 ? (
            <div className="empty-state">
              <h3>No posts yet</h3>
              <p>Be the first to ask something about this repo.</p>
            </div>
          ) : (
            <div className="community-posts">
              {posts.map((p) => (
                <div className="community-post" key={p.id}>
                  <div className="community-post-header">
                    {p.author_avatar_url && (
                      <img src={p.author_avatar_url} alt={p.author_username} className="community-avatar" />
                    )}
                    <span className="community-author">{p.author_username}</span>
                    <span className="community-time">{new Date(p.created_at).toLocaleString()}</span>
                  </div>
                  <p className="community-content">{p.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default RepoCommunity;
