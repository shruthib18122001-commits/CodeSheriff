# CodeSheriff

AI-powered codebase intelligence platform. Connect a GitHub repo and ask
natural-language questions about it — where auth is handled, what would
break if you change a schema, how a service handles errors.

## Architecture

- **Frontend**: React + TypeScript (Vite)
- **Backend**: FastAPI
- **Database**: PostgreSQL + pgvector (semantic code search)
- **Cache / queue**: Redis
- **AI**: tree-sitter for parsing, Gemini for embeddings + reasoning
- **Billing**: Stripe (free / pro / team plans)

See `docs/DECISIONS.md` for architecture decision log (start this today —
write down *why* you chose each piece as you build it, not after).

## Local setup

### 1. Start Postgres + Redis
```bash
docker-compose up -d
```

### 2. Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in GitHub OAuth + API keys
uvicorn app.main:app --reload
```
API runs at http://localhost:8000 — interactive docs at http://localhost:8000/docs

### 3. Frontend
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

## Build plan (8 weeks)

| Week | Milestone |
|------|-----------|
| 1 | GitHub OAuth + repo connection (this scaffold) |
| 2 | Ingestion pipeline: clone, parse with tree-sitter, chunk code |
| 3 | Embeddings + pgvector storage |
| 4 | Q&A endpoint + chat UI |
| 5 | Architecture map + drift detection |
| 6 | Stripe billing + plan enforcement |
| 7 | VS Code extension MVP |
| 8 | Polish, deploy, write it up |

