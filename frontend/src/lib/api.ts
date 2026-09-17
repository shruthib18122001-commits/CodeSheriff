import axios from "axios";
import { getToken } from "./auth";

export const api = axios.create({
  baseURL: "http://localhost:8000/api",
});

// Attach the JWT (stored after GitHub OAuth login) to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface Repo {
  id: string;
  github_full_name: string;
  index_status: "pending" | "cloning" | "parsing" | "embedding" | "ready" | "failed";
}

export interface RepoStatus {
  id: string;
  index_status: Repo["index_status"];
  last_indexed_commit_sha: string | null;
}

export interface Source {
  file_path: string;
  start_line: number;
  end_line: number;
  symbol_name: string | null;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
}

export interface ArchitectureNode {
  id: string;
  label: string;
  description: string;
  type: string;
}

export interface ArchitectureEdge {
  source: string;
  target: string;
  label: string;
}

export interface ArchitectureGraph {
  nodes: ArchitectureNode[];
  edges: ArchitectureEdge[];
}

export interface DriftItem {
  description: string;
  severity: "high" | "medium" | "low";
  file: string | null;
}

export interface PlanInfo {
  plan: "free" | "pro" | "team";
  queries_this_month: number;
}

export const PLAN_QUERY_LIMITS: Record<PlanInfo["plan"], number> = {
  free: 50,
  pro: 500,
  team: 2000,
};

export async function getGithubLoginUrl(): Promise<string> {
  const { data } = await api.get<{ auth_url: string }>("/auth/github/login");
  return data.auth_url;
}

export async function fetchRepos(): Promise<Repo[]> {
  const { data } = await api.get<Repo[]>("/repos");
  return data;
}

export async function connectRepo(githubFullName: string, githubUrl: string): Promise<Repo> {
  const { data } = await api.post<Repo>("/repos", {
    github_full_name: githubFullName,
    github_url: githubUrl,
  });
  return data;
}

export async function deleteRepo(repoId: string): Promise<void> {
  await api.delete(`/repos/${repoId}`);
}

export async function fetchRepoStatus(repoId: string): Promise<RepoStatus> {
  const { data } = await api.get<RepoStatus>(`/repos/${repoId}/status`);
  return data;
}

export async function fetchArchitecture(repoId: string): Promise<ArchitectureGraph> {
  const { data } = await api.get<ArchitectureGraph>(`/repos/${repoId}/architecture`);
  return data;
}

export async function fetchDrift(repoId: string): Promise<DriftItem[]> {
  const { data } = await api.get<{ drifts: DriftItem[] }>(`/repos/${repoId}/drift`);
  return data.drifts;
}

export type ThinkingLevel = "low" | "medium" | "high";

export interface Attachment {
  filename: string;
  mime_type: string;
  data: string; // base64-encoded file contents, no data: URL prefix
}

export async function askQuestion(
  repoId: string,
  question: string,
  thinkingLevel?: ThinkingLevel,
  attachments?: Attachment[]
): Promise<AskResponse> {
  const { data } = await api.post<AskResponse>("/query/ask", {
    repo_id: repoId,
    question,
    thinking_level: thinkingLevel,
    attachments,
  });
  return data;
}

export async function fetchPlan(): Promise<PlanInfo> {
  const { data } = await api.get<PlanInfo>("/billing/plan");
  return data;
}

export interface CommunityPost {
  id: string;
  content: string;
  created_at: string;
  author_username: string;
  author_avatar_url: string | null;
}

export async function fetchCommunityPosts(repoId: string): Promise<CommunityPost[]> {
  const { data } = await api.get<CommunityPost[]>(`/community/${repoId}/posts`);
  return data;
}

export async function createCommunityPost(repoId: string, content: string): Promise<CommunityPost> {
  const { data } = await api.post<CommunityPost>(`/community/${repoId}/posts`, { content });
  return data;
}

export async function startCheckout(plan: "pro" | "team"): Promise<string> {
  const { data } = await api.post<{ checkout_url: string }>("/billing/checkout", { plan });
  return data.checkout_url;
}
