import * as vscode from "vscode";
import { askQuestion, type AskResponse } from "./api";

export function createAskPanel(
  context: vscode.ExtensionContext,
  repoId: string,
  repoName: string,
  selectedCode: string,
  fileName: string
): void {
  const panel = vscode.window.createWebviewPanel(
    "codesheriffAsk",
    `Ask CodeSheriff — ${repoName}`,
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  const prefilledQuestion = `Explain this code from ${fileName}:\n\n${selectedCode}`;
  panel.webview.html = renderHtml(prefilledQuestion, null, false);

  panel.webview.onDidReceiveMessage(
    async (message: { command: string; question: string }) => {
      if (message.command !== "ask") return;

      panel.webview.html = renderHtml(message.question, null, true);
      try {
        const result = await askQuestion(repoId, message.question);
        panel.webview.html = renderHtml(message.question, result, false);
      } catch (err) {
        const failed: AskResponse = { answer: `Error: ${String(err)}`, sources: [] };
        panel.webview.html = renderHtml(message.question, failed, false);
      }
    },
    undefined,
    context.subscriptions
  );
}

function renderHtml(question: string, result: AskResponse | null, loading: boolean): string {
  const escapedQuestion = escapeHtml(question);
  const sourcesHtml = result?.sources.length
    ? `<div class="sources">${result.sources
        .map((s) => `<span class="source">${escapeHtml(s.file_path)}:${s.start_line}-${s.end_line}</span>`)
        .join(" ")}</div>`
    : "";
  const answerHtml = loading
    ? `<p class="loading">Thinking…</p>`
    : result
      ? `<div class="answer">${escapeHtml(result.answer)}</div>${sourcesHtml}`
      : "";

  return `<!DOCTYPE html>
<html>
<head>
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 16px; }
  textarea {
    width: 100%; height: 140px; box-sizing: border-box;
    background: var(--vscode-input-background); color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 8px;
    font-family: var(--vscode-editor-font-family);
  }
  button {
    margin-top: 8px; padding: 6px 14px;
    background: var(--vscode-button-background); color: var(--vscode-button-foreground);
    border: none; border-radius: 4px; cursor: pointer;
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  .answer { margin-top: 16px; white-space: pre-wrap; line-height: 1.5; }
  .sources { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
  .source {
    font-family: var(--vscode-editor-font-family); font-size: 12px;
    background: var(--vscode-badge-background); color: var(--vscode-badge-foreground);
    padding: 2px 8px; border-radius: 10px;
  }
  .loading { color: var(--vscode-descriptionForeground); font-style: italic; }
</style>
</head>
<body>
  <textarea id="question">${escapedQuestion}</textarea><br/>
  <button id="askBtn">Ask</button>
  <div id="result">${answerHtml}</div>
  <script>
    const vscode = acquireVsCodeApi();
    document.getElementById('askBtn').addEventListener('click', () => {
      const question = document.getElementById('question').value;
      vscode.postMessage({ command: 'ask', question });
    });
  </script>
</body>
</html>`;
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return text.replace(/[&<>"']/g, (c) => map[c]);
}
