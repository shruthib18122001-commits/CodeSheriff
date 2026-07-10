import axios from "axios";
import * as vscode from "vscode";

export interface Repo {
  id: string;
  github_full_name: string;
  index_status: string;
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

function client() {
  const config = vscode.workspace.getConfiguration("codesheriff");
  const baseURL = config.get<string>("apiBaseUrl") || "http://localhost:8000/api";
  const token = config.get<string>("token") || "";
  return axios.create({
    baseURL,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function fetchRepos(): Promise<Repo[]> {
  const { data } = await client().get<Repo[]>("/repos");
  return data;
}

export async function askQuestion(repoId: string, question: string): Promise<AskResponse> {
  const { data } = await client().post<AskResponse>("/query/ask", { repo_id: repoId, question });
  return data;
}
