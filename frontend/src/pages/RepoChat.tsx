import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { fetchRepoStatus, fetchRepos, type Repo } from "../lib/api";
import { useChat } from "../lib/useChat";

const STATUS_STEPS = ["pending", "cloning", "parsing", "embedding", "ready"];

function progressPercent(status: string): number {
  const idx = STATUS_STEPS.indexOf(status);
  if (idx === -1) return 0;
  return Math.round(((idx + 1) / STATUS_STEPS.length) * 100);
}

function RepoChat() {
  const { repoId } = useParams<{ repoId: string }>();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [question, setQuestion] = useState("");
  const { messages, send, sending } = useChat(repoId ?? "");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Poll repo status every 3s while indexing so the progress bar and the
  // question box (disabled until ready) stay in sync with the backend.
  useEffect(() => {
    if (!repoId) return;
    let active = true;

    async function poll() {
      try {
        const [status, repos] = await Promise.all([fetchRepoStatus(repoId!), fetchRepos()]);
        if (!active) return;
        const match = repos.find((r) => r.id === repoId) ?? null;
        setRepo(match ? { ...match, index_status: status.index_status } : null);
      } catch {
        // transient network hiccup -- keep showing the last known state
      }
    }

    poll();
    const timer = window.setInterval(poll, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [repoId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    if (!question.trim() || sending) return;
    send(question);
    setQuestion("");
  }

  const isReady = repo?.index_status === "ready";
  const isFailed = repo?.index_status === "failed";

  return (
    <div className="app-shell">
      <Sidebar activeRepoId={repoId} linkTo="chat" />
      <div className="main-panel">
        <div className="main-panel-header">
          <h2>{repo?.github_full_name ?? "Loading…"}</h2>
        </div>
        <div className="main-panel-body">
          {!isReady && !isFailed && repo && (
            <>
              <p className="chat-loading">Indexing repo — status: {repo.index_status}…</p>
              <div className="progress-bar-track">
                <div className="progress-bar-fill" style={{ width: `${progressPercent(repo.index_status)}%` }} />
              </div>
            </>
          )}
          {isFailed && <p className="error-text">Indexing failed for this repo. Try reconnecting it.</p>}

          <div className="chat-container">
            <div className="chat-messages">
              {messages.length === 0 && isReady && (
                <div className="empty-state" style={{ height: "auto", padding: "40px 0" }}>
                  <p>Ask anything about this codebase to get started.</p>
                </div>
              )}
              {messages.map((m) => (
                <div className="chat-message" key={m.id}>
                  <div className="chat-question">{m.question}</div>
                  {m.loading && <p className="chat-loading">Thinking…</p>}
                  {m.error && <div className="chat-answer error">{m.error}</div>}
                  {m.answer && (
                    <div className="chat-answer">
                      {m.answer}
                      {m.sources && m.sources.length > 0 && (
                        <div className="chat-sources">
                          {m.sources.map((s, i) => (
                            <span className="source-chip" key={i}>
                              {s.file_path}:{s.start_line}-{s.end_line}
                              {s.symbol_name ? ` (${s.symbol_name})` : ""}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            <div className="chat-input-row">
              <input
                placeholder="Ask anything about this codebase..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                disabled={!isReady || sending}
              />
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={!isReady || sending || !question.trim()}
              >
                {sending ? "Asking…" : "Ask"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RepoChat;
