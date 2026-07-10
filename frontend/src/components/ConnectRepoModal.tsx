import { useState } from "react";

interface Props {
  onClose: () => void;
  onConnect: (githubFullName: string) => Promise<unknown>;
}

function ConnectRepoModal({ onClose, onConnect }: Props) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConnect(name.trim());
      onClose();
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Could not connect repo. Check the name and try again.";
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Connect a repo</h3>
        <input
          autoFocus
          placeholder="owner/repo"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          style={{ width: "100%" }}
        />
        {error && <p className="error-text">{error}</p>}
        <div className="modal-actions">
          <button className="btn btn-outline" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting || !name.trim()}>
            {submitting ? "Connecting…" : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConnectRepoModal;
