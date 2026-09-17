# CodeSheriff

AI-powered codebase intelligence platform. Connect a GitHub repo and ask
natural-language questions about it — where auth is handled, what would
break if you change a schema, how a service handles errors.

## Features

- **Codebase Q&A** — grounded, cited answers to natural-language questions about a
  connected repo. Adjustable reasoning effort (Low / Medium / High) per question,
  and you can paste an image or attach files (screenshots, logs, etc.) alongside
  your question for extra context.
- **Architecture map** — an interactive dependency graph of a repo's modules,
  generated from the indexed source.
- **Drift detection** — flags places where a repo's README/docs claim something
  the actual code no longer reflects.
- **Community** — a lightweight discussion thread per repo. Anyone who connects
  the same GitHub repo lands in the same shared thread, so people working on or
  exploring the same open-source project can ask each other questions.
- **Billing** — Free / Pro / Team plans (Stripe), gating connected-repo count and
  monthly query volume.

## Architecture

- **Frontend**: React + TypeScript (Vite)
- **Backend**: FastAPI
- **Database**: PostgreSQL + pgvector (semantic code search)
- **Cache / queue**: Redis + RQ (background ingestion worker)
- **AI**: tree-sitter (Python/JS/TS/TSX) for parsing; Gemini for embeddings
  (`gemini-embedding-001`) and reasoning (`gemini-flash-latest`)
- **Billing**: Stripe (free / pro / team plans)

See `docs/DECISIONS.md` for architecture decision log (start this today —
write down *why* you chose each piece as you build it, not after).

## Local setup

### 1. Start Postgres + Redis
```bash
docker-compose up -d
```
Postgres is exposed on host port `5433` (not `5432`) to avoid clashing with a
locally installed Postgres.

### 2. Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in GitHub OAuth + GEMINI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload
```
API runs at http://localhost:8000 — interactive docs at http://localhost:8000/docs

### 3. Ingestion worker
Repos stay stuck on `pending` without this running — it's what actually
clones, parses, and embeds a connected repo.
```bash
cd backend                        # same venv as above
python worker.py
```
**macOS note**: RQ forks a subprocess per job, which can crash immediately
with an Objective-C fork-safety `SIGABRT` on macOS. If the worker dies right
after picking up a job, run it with:
```bash
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES python worker.py
```

### 4. Frontend
```bash
cd frontend
npm install
npm run dev
```
App runs at http://localhost:5173

## GitHub OAuth setup (needed before login works)

1. Go to https://github.com/settings/developers → "New OAuth App"
2. Homepage URL: `http://localhost:5173`
3. Authorization callback URL: `http://localhost:8000/api/auth/github/callback`
4. Copy the Client ID and Client Secret into `backend/.env`

## Notes on the Gemini integration

- `GEMINI_THINKING_LEVEL` in `.env` (`off` / `low` / `medium` / `high`) sets the
  server-wide default reasoning effort; the chat UI's effort picker overrides it
  per question.
- Free-tier Gemini API keys can be capped at a very low daily request quota
  (as low as 20/day for the chat model on some projects) — expect intermittent
  502s under heavy local testing. Enabling billing on the Google Cloud project
  removes this cap.


