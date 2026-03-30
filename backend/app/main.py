"""FastAPI application entry point.

Creates the app, configures CORS (allow all origins for Tailscale access),
and registers all routers under the /api prefix. Uvicorn runs this as
app.main:app.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, chat, health, people, profile, tasks, todos

app = FastAPI(title="Personal Assistant API", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(people.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(todos.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
