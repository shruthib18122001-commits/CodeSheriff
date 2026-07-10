import { useCallback, useEffect, useRef, useState } from "react";
import { connectRepo, deleteRepo, fetchRepoStatus, fetchRepos, type Repo } from "./api";

const TERMINAL_STATUSES = new Set(["ready", "failed"]);

/**
 * Fetches the current user's repos and keeps any still-indexing repo's
 * status fresh by polling GET /api/repos/:id/status every 3s until it
 * reaches a terminal state (ready/failed).
 */
export function useRepos() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollTimers = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRepos();
      setRepos(data);
      setError(null);
    } catch {
      setError("Failed to load repos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timers = pollTimers.current;
    return () => {
      Object.values(timers).forEach((id) => window.clearInterval(id));
    };
  }, [load]);

  const pollStatus = useCallback((repoId: string) => {
    if (pollTimers.current[repoId]) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await fetchRepoStatus(repoId);
        setRepos((prev) =>
          prev.map((r) => (r.id === repoId ? { ...r, index_status: status.index_status } : r))
        );
        if (TERMINAL_STATUSES.has(status.index_status)) {
          window.clearInterval(pollTimers.current[repoId]);
          delete pollTimers.current[repoId];
        }
      } catch {
        window.clearInterval(pollTimers.current[repoId]);
        delete pollTimers.current[repoId];
      }
    }, 3000);
    pollTimers.current[repoId] = timer;
  }, []);

  useEffect(() => {
    repos.forEach((r) => {
      if (!TERMINAL_STATUSES.has(r.index_status)) {
        pollStatus(r.id);
      }
    });
  }, [repos, pollStatus]);

  const connect = useCallback(
    async (githubFullName: string) => {
      const repo = await connectRepo(githubFullName, `https://github.com/${githubFullName}`);
      setRepos((prev) => [...prev, repo]);
      pollStatus(repo.id);
      return repo;
    },
    [pollStatus]
  );

  const remove = useCallback(async (repoId: string) => {
    await deleteRepo(repoId);
    setRepos((prev) => prev.filter((r) => r.id !== repoId));
  }, []);

  return { repos, loading, error, connect, remove, reload: load };
}
