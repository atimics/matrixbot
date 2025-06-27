# Gemini Project Brief: Context-Aware AI Chatbot (RatiChat)

This document provides a summary of the RatiChat project for the Gemini agent.

## About the Project

RatiChat is a sophisticated, multi-platform, autonomous AI agent designed for advanced, context-aware interactions on Matrix and Farcaster. It features a modular, resilient architecture built for complex decision-making and proactive community engagement.

The core architecture is a Commander/Sub-Agent model where a strategic "Commander" AI handles complex analysis and delegates tasks to lightweight "Sub-Agent" AIs. The system uses a node-based "World State" for context management, a proactive engine for initiating conversations, and a unified tool system for interacting with the world.

The project is fully containerized using Docker and includes a management UI built with Next.js and a FastAPI backend.

## Tech Stack

### Backend
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Async:** Uvicorn, asyncio
- **Dependencies:** Poetry
- **Database:** PostgreSQL (with Psycopg), aiosqlite, Alembic for migrations
- **AI:** Google Gemini (`google-genai`)
- **Integrations:**
    - Matrix: `matrix-nio`
    - Farcaster: `web3`, `aiohttp`
    - Storage: Arweave (`arweave-python-client`)
- **Configuration:** Pydantic, `python-dotenv`

### Frontend
- **Framework:** Next.js
- **Styling:** Not specified, but likely Tailwind CSS given the `tailwind.config.ts` file.

### Tooling
- **Linting & Formatting:** Ruff
- **Testing:** Pytest with `pytest-asyncio`
- **Containerization:** Docker, Docker Compose

## Key Commands

### Running the Application
The entire stack (backend, UI, database) is managed by Docker Compose.

1.  **Copy environment variables:**
    ```bash
    cp .env.example .env
    ```
2.  **Build and run:**
    ```bash
    docker-compose up --build
    ```
- **Management UI:** `http://localhost:3000`
- **API Docs (Swagger):** `http://localhost:8000/docs`

### Testing
Tests are run using Pytest.

```bash
pytest
```
The test configuration is located in `pyproject.toml` under `[tool.pytest.ini_options]`.

### Linting & Formatting
The project uses Ruff for linting and formatting.

```bash
ruff check .
```
The configuration is located in `pyproject.toml` under `[tool.ruff]`.

## Project Structure Overview

- `chatbot/`: The main Python application package.
    - `api_server/`: FastAPI backend for the management UI.
    - `core/`: Core logic, including the Commander/Sub-Agent model, world state, and orchestration.
    - `integrations/`: Connectors for external services like Matrix and Farcaster.
    - `tools/`: The AI's toolkit for interacting with the world.
    - `config.py`: Centralized Pydantic-based configuration.
    - `main_with_ui.py`: Main entry point for running the backend and API server together.
- `ui-nextjs/`: The Next.js frontend for the management UI.
- `tests/`: The Pytest test suite.
- `Dockerfile`: Dockerfile for the Python backend.
- `docker-compose.yml`: Docker Compose file to orchestrate all services.
- `pyproject.toml`: Defines Python dependencies, project metadata, and tool configurations.
