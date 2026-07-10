import * as vscode from "vscode";
import { fetchRepos, type Repo } from "./api";
import { createAskPanel } from "./askPanel";
import { RepoTreeProvider } from "./repoTreeProvider";

export function activate(context: vscode.ExtensionContext): void {
  const treeProvider = new RepoTreeProvider(context);
  vscode.window.registerTreeDataProvider("codesheriffRepos", treeProvider);

  context.subscriptions.push(
    vscode.commands.registerCommand("codesheriff.refreshRepos", () => treeProvider.refresh()),

    vscode.commands.registerCommand("codesheriff.selectRepo", async (repo?: Repo) => {
      let target = repo;
      if (!target) {
        const repos = await fetchRepos().catch(() => [] as Repo[]);
        const pick = await vscode.window.showQuickPick(
          repos.map((r) => ({ label: r.github_full_name, repo: r })),
          { placeHolder: "Select the active CodeSheriff repo" }
        );
        target = pick?.repo;
      }
      if (target) {
        await context.globalState.update("activeRepoId", target.id);
        await context.globalState.update("activeRepoName", target.github_full_name);
        vscode.window.showInformationMessage(`CodeSheriff: active repo set to ${target.github_full_name}`);
        treeProvider.refresh();
      }
    }),

    vscode.commands.registerCommand("codesheriff.askSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("CodeSheriff: open a file and select some code first.");
        return;
      }

      const selectedCode = editor.document.getText(editor.selection);
      if (!selectedCode.trim()) {
        vscode.window.showWarningMessage("CodeSheriff: select some code first.");
        return;
      }

      let repoId = context.globalState.get<string>("activeRepoId");
      let repoName = context.globalState.get<string>("activeRepoName") ?? "repo";

      if (!repoId) {
        const repos = await fetchRepos().catch(() => [] as Repo[]);
        if (repos.length === 0) {
          vscode.window.showErrorMessage(
            "CodeSheriff: no repos found. Connect one in the web app first, and check codesheriff.token in Settings."
          );
          return;
        }
        const pick = await vscode.window.showQuickPick(
          repos.map((r) => ({ label: r.github_full_name, repo: r })),
          { placeHolder: "Which repo is this code from?" }
        );
        if (!pick) return;
        repoId = pick.repo.id;
        repoName = pick.repo.github_full_name;
        await context.globalState.update("activeRepoId", repoId);
        await context.globalState.update("activeRepoName", repoName);
      }

      const fileName = vscode.workspace.asRelativePath(editor.document.uri);
      createAskPanel(context, repoId, repoName, selectedCode, fileName);
    })
  );
}

export function deactivate(): void {}
