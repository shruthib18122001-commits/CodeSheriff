# Architecture decisions

Log every meaningful technical choice here as you make it — the *why*,
not just the *what*. This file is what you'll actually use in interviews
when someone asks "why did you choose X over Y?"

## Format
```
## [Date] Decision title
**Choice:** what you picked
**Alternatives considered:** what else you looked at
**Why:** the reasoning
**Tradeoff:** what you gave up
```

---

## [2026-06-25] FastAPI over Django/Flask for the backend
**Choice:** FastAPI
**Alternatives considered:** Django REST Framework, Flask
**Why:** Native async support matters here — ingestion (cloning repos,
calling LLM APIs) is I/O-bound, and FastAPI's async handlers avoid
blocking the event loop. Pydantic models also give free request
validation, which matters for a public-facing API with paid tiers.
**Tradeoff:** Smaller ecosystem than Django (no built-in admin panel,
less mature ORM tooling) — using SQLAlchemy directly instead.

## [2026-06-25] pgvector over a dedicated vector DB (Pinecone, Weaviate)
**Choice:** pgvector extension on Postgres
**Alternatives considered:** Pinecone, Weaviate, Chroma
**Why:** Keeping vectors in the same database as relational data (users,
repos, billing) avoids a second system to operate, and at this stage
the data volume doesn't need a dedicated vector DB's scale. Joins
between code_chunks and repos are trivial in SQL.
**Tradeoff:** Will need to revisit if a single repo's embeddings grow
into the millions — pgvector's ANN indexing doesn't scale as well as
purpose-built vector stores at that size.

## [2026-06-25] JWT over session cookies for auth
**Choice:** JWT issued after GitHub OAuth, stored client-side
**Alternatives considered:** server-side sessions with Redis
**Why:** Stateless auth simplifies horizontal scaling of the API later,
and the VS Code extension / CLI (planned for weeks 7+) can't easily
share browser cookies — a bearer token works uniformly across all
three client surfaces.
**Tradeoff:** No instant revocation — a stolen token is valid until
expiry. Mitigated with a short expiry window and refresh flow (not yet
implemented).

## [2026-07-05] tree-sitter for chunking, pinned below 0.22

**Choice:** `tree-sitter==0.21.3` + `tree-sitter-languages==1.10.2`,
walking the parse tree for `function_definition`/`class_definition`
(and per-language equivalents) to produce one chunk per semantic unit.
**Alternatives considered:** fixed-size character/token windows;
regex-based function detection.
**Why:** Character-window chunking routinely slices a function in half,
which wrecks both embedding quality (half a function embeds as noise)
and the citations shown to the user (a line range that stops mid-body
looks wrong). Walking the AST guarantees each chunk is a complete,
independently meaningful unit with an accurate symbol name and line range.
**Tradeoff:** The originally-listed `tree-sitter==0.23.0` breaks
`tree-sitter-languages` 1.10.2 — 0.22 changed `Language.__init__` from
`(path, name)` to a single PyCapsule argument, and `get_parser()` raises
`TypeError: __init__() takes exactly 1 argument (2 given)`. Pinning to
0.21.3 (the last version before that change) fixes it without a rewrite;
migrating to `tree-sitter>=0.22` later means switching to
per-language pip packages (`tree-sitter-python`, `tree-sitter-javascript`,
`tree-sitter-typescript`) since `tree-sitter-languages` is unmaintained
against the new API.

## [2026-07-05] RQ over Celery for the ingestion queue

**Choice:** `rq` with a single named queue (`"ingestion"`), run via a
standalone `python worker.py` process.
**Alternatives considered:** Celery + a broker, FastAPI `BackgroundTasks`.
**Why:** Ingestion jobs are I/O-bound, run one-at-a-time per repo, and
we already run Redis for caching — RQ needs nothing beyond that Redis
instance (no separate broker/result backend config). `BackgroundTasks`
was ruled out per the project constraint that background work must
never run inside a request handler: a `BackgroundTask` still executes
in the same process as uvicorn, so a slow clone+embed job would starve
the event loop for every other request.
**Tradeoff:** RQ's retry/monitoring tooling is thinner than Celery's
(no built-in Flower-equivalent), and it doesn't support complex
workflows (chains/chords) if ingestion ever needs multi-stage fan-out.

## [2026-07-05] HNSW index built after embeddings, not in the migration

**Choice:** `CREATE INDEX ... USING hnsw` runs at the end of
`embedder.embed_repo_chunks()`, not in the Alembic migration that
creates the `code_chunks` table.
**Alternatives considered:** create the index in the initial migration,
before any rows exist.
**Why:** Per the project's explicit ordering constraint — building an
ANN index against an empty (or partially-embedded) column is wasted
work, since HNSW is built incrementally as vectors are inserted and
would need to reprocess every existing row anyway once real data
lands. Building it once after a batch of embeddings finishes is strictly
cheaper for the common case (one repo's chunks arriving all at once).
**Tradeoff:** The very first query against a freshly-ingested repo (before
`embed_repo_chunks` finishes) has no index to use — acceptable here
because `index_status` gates queries to `ready`, which only happens
after embedding (and therefore indexing) completes.

## [2026-07-05] Stripe webhook exempted from JWT auth, verified by signature instead

**Choice:** `POST /api/billing/webhook` has no `Depends(get_current_user)`;
authenticity comes from `stripe.Webhook.construct_event()` checking the
`Stripe-Signature` header against `STRIPE_WEBHOOK_SECRET`.
**Alternatives considered:** requiring an API key/JWT on the endpoint.
**Why:** Stripe's servers call this endpoint directly and cannot obtain
or present a CodeSheriff-issued JWT. Signature verification is the
standard (and only viable) way to authenticate a webhook — it proves
the payload was signed by Stripe with the shared webhook secret.
**Tradeoff:** The endpoint is reachable by anyone on the internet; an
invalid/missing signature is rejected with 400, but this does mean the
route needs to stay carefully separate from anything JWT-gated so a
misconfiguration can't accidentally expose user data here.

## [2026-07-05] GitHub OAuth callback redirects to the SPA instead of returning JSON

**Choice:** `GET /api/auth/github/callback` ends with
`RedirectResponse(f"{frontend_base_url}/callback?token=...")` instead of
returning `{"access_token": ..., "token_type": "bearer"}` as JSON.
**Why:** GitHub's OAuth redirect always lands on the backend's
`redirect_uri` (`.../api/auth/github/callback`), not on the frontend.
The frontend's `/callback` route (as specified) is what's supposed to
read the JWT and store it in `localStorage` — but the browser never
visits that route unless the backend sends it there. Returning raw JSON
from the backend callback would leave the user staring at an API
response instead of landing in the app.
**Tradeoff:** The JWT briefly appears in the URL query string (and
therefore browser history / server logs) during the redirect. Mitigated
by the frontend immediately reading and stripping it via
`navigate(..., { replace: true })` on `/callback`, but a production
deployment should consider a short-lived one-time code exchanged for
the JWT instead of passing the JWT itself in the URL.

## [2026-07-05] React Flow with a hand-rolled grid layout, no layout-engine dependency

**Choice:** `reactflow` for rendering the architecture graph, with nodes
positioned by a simple `sqrt(n)`-column grid computed client-side.
**Alternatives considered:** `dagre`/`elkjs` for automatic hierarchical
layout.
**Why:** A real layout engine produces a much better graph for large
codebases with deep dependency chains, but adds a dependency and
non-trivial integration work for what's, at this stage, usually a
handful of modules per repo. The grid is legible for that scale and
keeps the frontend bundle smaller.
**Tradeoff:** Will look poor once a graph has 20+ nodes or deep edge
chains that a grid can't represent well — revisit with `dagre` if repos
with large module counts become common.

## [2026-07-05] Hand-written initial Alembic migration instead of autogenerate

**Choice:** `alembic/versions/0001_initial_schema.py` is written by hand
against the four SQLAlchemy models, rather than produced by
`alembic revision --autogenerate`.
**Why:** Autogenerate diffs against a live database connection, which
isn't guaranteed to be available in every environment this repo gets
set up in (e.g. CI, a fresh clone before `docker-compose up` has run).
A hand-written migration is deterministic and reviewable without needing
Postgres running first.
**Tradeoff:** Future schema changes still need autogenerate (or careful
hand-writing) against a real DB to stay in sync with the models — this
decision only covers the bootstrap migration.

## [2026-07-05] Test doubles over a real test database

**Choice:** Backend tests call route/service functions directly with
`unittest.mock.MagicMock` standing in for the SQLAlchemy `Session`, and
`SimpleNamespace` standing in for `User`/`Repo` rows — no FastAPI
`TestClient`, no SQLite/Postgres test database.
**Alternatives considered:** spin up SQLite in-memory for tests; use a
real Postgres test container.
**Why:** `code_chunks.embedding` is a pgvector `Vector` column and
`query_history.sources` is a `JSONB` column — both are Postgres-specific
types that don't have a faithful SQLite equivalent, so an in-memory
SQLite DB would either fail at `create_all()` or silently test against
different semantics than production. Mocking the session lets tests
exercise the actual business logic (limit checks, status-gating, error
handling) without needing a real Postgres instance in every environment
that runs `pytest`.
**Tradeoff:** These tests don't catch bugs in the actual SQL Alembic
generates or in real query behavior (e.g. a wrong `filter()` condition
that happens to still return the mocked value). That class of bug needs
a real Postgres+pgvector integration test suite, which this repo doesn't
have yet.
