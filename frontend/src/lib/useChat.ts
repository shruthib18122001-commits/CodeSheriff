import { useCallback, useState } from "react";
import { askQuestion, type Attachment, type Source, type ThinkingLevel } from "./api";

export interface ChatMessage {
  id: string;
  question: string;
  attachmentNames?: string[];
  answer?: string;
  sources?: Source[];
  loading: boolean;
  error?: string;
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Manages chat history for a single repo's Q&A interface. */
export function useChat(repoId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  // Bumped after each query that actually reaches the server (success or
  // fallback answer) -- the backend counts both toward the monthly quota.
  const [answeredCount, setAnsweredCount] = useState(0);

  const send = useCallback(
    async (question: string, thinkingLevel?: ThinkingLevel, attachments?: Attachment[]) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      const id = makeId();
      setMessages((prev) => [
        ...prev,
        { id, question: trimmed, attachmentNames: attachments?.map((a) => a.filename), loading: true },
      ]);
      setSending(true);

      try {
        const result = await askQuestion(repoId, trimmed, thinkingLevel, attachments);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === id ? { ...m, answer: result.answer, sources: result.sources, loading: false } : m
          )
        );
        setAnsweredCount((n) => n + 1);
      } catch (e: unknown) {
        const detail =
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "Something went wrong answering that question.";
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, error: detail, loading: false } : m)));
      } finally {
        setSending(false);
      }
    },
    [repoId]
  );

  return { messages, send, sending, answeredCount };
}
