from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sqlalchemy

from app.api import auth, repos, query, billing
from app.db.session import engine, Base
from app.models import user, repo, code_chunk, query_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="CodeSheriff API",
    description="AI-powered codebase intelligence platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the React dev server to talk to this API during local development.
# Tighten allow_origins before deploying to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
