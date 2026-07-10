import * as vscode from "vscode";
import { fetchRepos, type Repo } from "./api";

export class RepoTreeItem extends vscode.TreeItem {
  constructor(public readonly repo: Repo, isActive: boolean) {
    super(repo.github_full_name, vscode.TreeItemCollapsibleState.None);
    this.description = isActive ? `${repo.index_status} • active` : repo.index_status;
    this.contextValue = "codesheriffRepo";
    this.iconPath = new vscode.ThemeIcon(
      repo.index_status === "ready" ? "check" : repo.index_status === "failed" ? "error" : "sync"
    );
    this.command = {
      command: "codesheriff.selectRepo",
      title: "Set as active repo",
      arguments: [repo],
    };
  }
}

export class RepoTreeProvider implements vscode.TreeDataProvider<RepoTreeItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private readonly context: vscode.ExtensionContext) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: RepoTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<RepoTreeItem[]> {
    try {
      const repos = await fetchRepos();
      const activeId = this.context.globalState.get<string>("activeRepoId");
      return repos.map((r) => new RepoTreeItem(r, r.id === activeId));
    } catch (err) {
      vscode.window.showErrorMessage(
        `CodeSheriff: could not load repos. Check codesheriff.apiBaseUrl and codesheriff.token in Settings. (${err})`
      );
      return [];
    }
  }
}
