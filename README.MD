# Context-Aware AI Chatbot (RatiChat)

A sophisticated, multi-platform, autonomous AI agent designed for advanced, context-aware interactions on Matrix and Farcaster. This system features a modular, resilient architecture built for complex decision-making and proactive community engagement.


![RatiChat](ratichat.jpg)



## ✨ Key Features

-   **🧠 Advanced Agentic Architecture:** Implements a **Commander/Sub-Agent** model. A strategic "Commander" AI handles complex analysis and delegates conversational tasks to lightweight "Sub-Agent" AIs for efficiency and cost-effectiveness.
-   **🌳 Node-Based World State:** Manages vast amounts of information using a tree-like "node" structure with AI-powered summarization, enabling efficient and scalable context management for the Commander AI.
-   **⚡ Proactive Engagement Engine:** Goes beyond reacting to messages. The AI analyzes the world state to identify opportunities and initiate meaningful conversations on its own.
-   **🔧 Unified Tool System:** The AI interacts with the world through a dynamic and extensible set of tools, allowing for easy addition of new capabilities like sending messages, generating media, or analyzing data.
-   **🔌 Multi-Platform Integration:** Natively supports **Matrix** and **Farcaster**, with a robust `IntegrationManager` designed for adding future platforms.
-   **🖼️ AI Media Generation:** Includes tools for generating images (SDXL, Gemini) and videos (Google Veo) on the fly, with uploads to permanent storage on S3 or Arweave.
-   **🌐 Comprehensive Management UI:** A FastAPI backend and Next.js frontend provide a rich, real-time administrative dashboard for monitoring, configuration, and control.
-   **🐳 Fully Containerized:** Deploys easily and reliably using a multi-stage Docker build and a full-stack Docker Compose configuration for the backend, UI, and database.

## 🏛️ Architectural Overview

The system's architecture is designed for robustness and advanced AI behavior. It follows a clear data flow from event reception to action execution, centered around a few core components:

1.  **Dependency Container (`/chatbot/core/container.py`):** The application's entry point. It initializes and injects all necessary components, ensuring a clean, decoupled architecture.

2.  **Main Orchestrator (`/chatbot/core/orchestration/main_orchestrator.py`):** The central coordinator that manages the system's lifecycle, platform observers, and the main processing loop.

3.  **Attention Engine (`/chatbot/core/attention/engine.py`):** The first stage of the processing pipeline. Instead of processing raw events, the Attention Engine acts as an intelligent filter, analyzing incoming messages to determine if they warrant the AI's attention. It bundles messages with their full context (user profile, conversation history) into a `ContextualThread`.

4.  **Processing Hub (`/chatbot/core/orchestration/processing_hub.py`):** The heart of the Commander/Sub-Agent logic. It receives `ContextualThread` objects from the Attention Engine and routes them to the appropriate processor:
    *   **Commander AI (`AdaptiveProcessor`):** Handles complex, strategic threads that require system-wide awareness. It uses the node-based world state to reason about the big picture and can delegate tasks.
    *   **Sub-Agents (`MissionProcessor`):** Lightweight, focused AIs that are assigned a specific "mission" (e.g., "answer questions in this channel"). They operate with a smaller context and use a faster, cheaper LLM to handle immediate conversational needs.

5.  **Tool Registry & Execution (`/chatbot/tools/`):** The AI's interface to the outside world. The selected AI processor (Commander or Sub-Agent) chooses a tool, and the system executes it. This includes sending messages, generating media, or analyzing data.

## 🚀 Getting Started

### Prerequisites

-   Docker and Docker Compose
-   Git

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/ratichat.git
cd ratichat
```

### 2. Environment Configuration

Create a `.env` file in the root directory by copying the example:

```bash
cp .env.example .env
```

Now, edit the `.env` file with your API keys and credentials. The following are **required** for the system to function:

-   `OPENROUTER_API_KEY`: Your API key for OpenRouter.ai.
-   `POSTGRES_PASSWORD`: A secure password for the PostgreSQL database used by services.
-   **Matrix Credentials:**
    -   `MATRIX_HOMESERVER`
    -   `MATRIX_USER_ID`
    -   `MATRIX_PASSWORD`
-   **Farcaster Credentials (if used):**
    -   `NEYNAR_API_KEY`
    -   `FARCASTER_BOT_FID`
    -   `FARCASTER_BOT_SIGNER_UUID`

Refer to `.env.example` and `/chatbot/config.py` for a full list of configurable variables.

### 3. Build and Run with Docker

The entire application stack (backend, UI, database) is managed by Docker Compose.

```bash
docker-compose up --build
```

-   The **Chatbot Backend** will start and begin observing platforms.
-   The **Management UI** will be available at `http://localhost:3000`.
-   The **FastAPI Backend API** will be available at `http://localhost:8000`.
-   API documentation (Swagger UI) is at `http://localhost:8000/docs`.

### 4. First-Time Setup (UI)

If you are running the bot for the first time without a complete `.env` file, you can navigate to `http://localhost:3000` to use the **Setup Wizard**. This wizard will guide you through a conversational setup process to configure the essential credentials.

## 📂 Project Structure

```
├── chatbot/                # Main Python application package
│   ├── api_server/         # FastAPI backend for the management UI
│   ├── core/               # Core logic: orchestration, AI engines, world state
│   │   ├── attention/      # Attention Engine for intelligent event filtering
│   │   ├── node_system/    # Node-based context management
│   │   ├── processors/     # Commander (Adaptive) and Sub-Agent (Mission) processors
│   │   ├── proactive/      # Proactive engagement engine
│   │   └── world_state/    # World state data structures and manager
│   ├── integrations/       # Connectors for external services (Matrix, Farcaster, S3)
│   ├── tools/              # The AI's toolkit for interacting with the world
│   ├── prompts/            # Modular .txt files for AI identity and guidelines
│   ├── config.py           # Centralized Pydantic-based configuration
│   └── main_with_ui.py     # Main entry point for running backend + API server
├── ui-nextjs/              # Next.js frontend for the management UI
├── tests/                  # Pytest test suite
├── Dockerfile              # Dockerfile for the Python backend
└── docker-compose.yml      # Docker Compose file to orchestrate all services
```

## ⚙️ Configuration

Configuration is managed via environment variables and the `.env` file, loaded by `/chatbot/config.py`. The system uses nested Pydantic models for robust validation and organization. This allows for clear, hierarchical configuration of all components, including AI models, rate limits, and integration credentials.

## 🌐 API & UI

The system includes a comprehensive management interface:

-   **Backend:** A FastAPI server located in `/chatbot/api_server/` provides a REST API for monitoring and controlling the bot. It features a modular router architecture and WebSocket support for real-time log streaming.
-   **Frontend:** A Next.js web application in `/ui-nextjs/` serves as the user-facing dashboard. It communicates with the FastAPI backend to provide real-time status updates, log viewing, and system controls.

Key API endpoints:
-   `GET /api/system/status`: Get a comprehensive real-time status of the entire system.
-   `GET /api/tools`: List all available AI tools and their status.
-   `GET /docs`: View interactive API documentation (Swagger UI).

## 📄 License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International License**.

-   **You are free to:** Share and adapt the material.
-   **Under the following terms:** You must give appropriate credit and may not use the material for commercial purposes.

For commercial use, licensing, or any use that generates revenue, you must obtain explicit written permission from the copyright holder. See the [LICENSE](./LICENSE) file for full details.


[![Tip in Crypto](https://tip.md/badge.svg)](https://tip.md/immanence)