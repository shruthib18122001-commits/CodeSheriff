# CodeSheriff for VS Code

Ask natural language questions about your codebase without leaving the editor.

## Setup

1. `npm install && npm run compile` inside `vscode-extension/`.
2. Press F5 in VS Code (with this folder open) to launch an Extension Development Host.
3. Open Settings and set:
   - `codesheriff.apiBaseUrl` — defaults to `http://localhost:8000/api`.
   - `codesheriff.token` — the JWT issued after signing in to the CodeSheriff web app (copy the `cs_token` value from its localStorage).

## Usage

- **Sidebar**: click the CodeSheriff icon in the activity bar to see your connected repos and their index status. Click a repo to set it as the active repo.
- **Ask CodeSheriff**: select any code in the editor, right-click, and choose "Ask CodeSheriff". A panel opens beside the editor with the question pre-filled (including the selected code as context) and shows the grounded answer with cited sources once it responds.
