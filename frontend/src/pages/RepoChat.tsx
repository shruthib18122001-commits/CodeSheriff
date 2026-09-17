import { useEffect, useRef, useState, type ClipboardEvent } from "react";
import { useParams } from "react-router-dom";
import EffortPicker from "../components/EffortPicker";
import RepoTabs from "../components/RepoTabs";
import Sidebar from "../components/Sidebar";
import { fetchRepoStatus, fetchRepos, type Attachment, type Repo, type ThinkingLevel } from "../lib/api";
import { useChat } from "../lib/useChat";

const STATUS_STEPS = ["pending", "cloning", "parsing", "embedding", "ready"];
// Mirrors backend MAX_ATTACHMENTS_BYTES (app/api/query.py) so oversized
// files are rejected client-side instead of round-tripping to the server.
const MAX_ATTACHMENTS_BYTES = 15 * 1024 * 1024;

interface PendingAttachment extends Attachment {
  id: string;
  previewUrl: string | null; // object URL for image thumbnails; null otherwise
}

function progressPercent(status: string): number {
  const idx = STATUS_STEPS.indexOf(status);
  if (idx === -1) return 0;
  return Math.round(((idx + 1) / STATUS_STEPS.length) * 100);
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function filesToAttachments(files: File[]): Promise<PendingAttachment[]> {
  return Promise.all(
    files.map(async (file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      filename: file.name || "pasted-image.png",
      mime_type: file.type || "application/octet-stream",
      data: await fileToBase64(file),
      previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
    }))
  );
}

function RepoChat() {
  const { repoId } = useParams<{ repoId: string }>();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [question, setQuestion] = useState("");
  const [thinkingLevel, setThinkingLevel] = useState<ThinkingLevel>("low");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [attachError, setAttachError] = useState<string | null>(null);
  const { messages, send, sending, answeredCount } = useChat(repoId ?? "");
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function addAttachments(files: File[]) {
    if (files.length === 0) return;
    filesToAttachments(files).then((next) => {
      setPendingAttachments((prev) => {
        const combined = [...prev, ...next];
        const totalBytes = combined.reduce((sum, a) => sum + a.data.length * 0.75, 0);
        if (totalBytes > MAX_ATTACHMENTS_BYTES) {
          setAttachError("Attachments too large — 15MB total limit.");
          return prev;
        }
        setAttachError(null);
        return combined;
      });
    });
  }

  function removeAttachment(id: string) {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function handlePaste(e: ClipboardEvent<HTMLInputElement>) {
    const files = Array.from(e.clipboardData.items)
      .filter((item) => item.kind === "file")
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (files.length > 0) addAttachments(files);
  }

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
    const attachments: Attachment[] = pendingAttachments.map(({ filename, mime_type, data }) => ({
      filename,
      mime_type,
      data,
    }));
    send(question, thinkingLevel, attachments.length > 0 ? attachments : undefined);
    setQuestion("");
    pendingAttachments.forEach((a) => a.previewUrl && URL.revokeObjectURL(a.previewUrl));
    setPendingAttachments([]);
  }

  const isReady = repo?.index_status === "ready";
  const isFailed = repo?.index_status === "failed";

  return (
    <div className="app-shell">
      <Sidebar activeRepoId={repoId} linkTo="chat" planRefreshSignal={answeredCount} />
      <div className="main-panel">
        <div className="main-panel-header">
          <h2>{repo?.github_full_name ?? "Loading…"}</h2>
          <RepoTabs active="chat" />
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
                  {m.attachmentNames && m.attachmentNames.length > 0 && (
                    <div className="chat-attachments">
                      {m.attachmentNames.map((name, i) => (
                        <span className="attachment-chip" key={i}>
                          📎 {name}
                        </span>
                      ))}
                    </div>
                  )}
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

            {attachError && <p className="error-text">{attachError}</p>}

            <div className="chat-composer">
              {pendingAttachments.length > 0 && (
                <div className="attachment-preview-row">
                  {pendingAttachments.map((a) => (
                    <div className="attachment-preview-chip" key={a.id}>
                      {a.previewUrl ? (
                        <img src={a.previewUrl} alt={a.filename} />
                      ) : (
                        <span className="attachment-preview-icon">📄</span>
                      )}
                      <span className="attachment-preview-name">{a.filename}</span>
                      <button
                        type="button"
                        className="attachment-preview-remove"
                        onClick={() => removeAttachment(a.id)}
                        title="Remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="chat-input-row">
                <input
                  type="file"
                  multiple
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  onChange={(e) => {
                    addAttachments(Array.from(e.target.files ?? []));
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  className="attach-button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!isReady || sending}
                  title="Attach files or images"
                >
                  +
                </button>
                <input
                  className="chat-text-input"
                  placeholder="Ask anything about this codebase..."
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  onPaste={handlePaste}
                  disabled={!isReady || sending}
                />
                <EffortPicker value={thinkingLevel} onChange={setThinkingLevel} disabled={!isReady || sending} />
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
    </div>
  );
}

export default RepoChat;
