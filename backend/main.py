"""FastAPI application entry point for NHL Analytics Dashboard backend.

This module initializes the FastAPI app and includes all routers.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from routers import games, teams, players, goalies, rankings, streaks, tools

app = FastAPI(
    title="NHL Analytics Dashboard API",
    description="Backend API for NHL game, team, and player analytics",
    version="1.0.0",
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to specific frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(games.router, prefix="/games", tags=["games"])
app.include_router(teams.router, prefix="/teams", tags=["teams"])
app.include_router(players.router, prefix="/players", tags=["players"])
app.include_router(goalies.router, prefix="/goalies", tags=["goalies"])
app.include_router(rankings.router, prefix="/rankings", tags=["rankings"])
app.include_router(streaks.router, prefix="/streaks", tags=["streaks"])
app.include_router(tools.router, prefix="/tools", tags=["tools"])


@app.get("/")
async def root() -> dict:
    """Health check endpoint.

    Returns:
        Dict with status and API version.
    """
    return {
        "status": "healthy",
        "service": "NHL Analytics Dashboard API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint for Cloud Run.

    Returns:
        Dict with status.
    """
    return {"status": "healthy"}
