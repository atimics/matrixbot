# Matrix + OpenRouter Chatbot (Version 0.0.1)

A modern, async Matrix chatbot that uses OpenRouter for AI-powered responses. Built with [matrix-nio](https://github.com/poljar/matrix-nio) and Python 3.10+.

## Features
- Listens for messages in configured Matrix rooms.
- Activates in a room when mentioned by its display name.
- Once active, responds to all messages in that room.
- Features an active listening decay mechanism: the bot will announce when it stops listening due to inactivity and can be re-activated by a mention.
- Uses OpenRouter API (configurable GPT models) for generating responses.
- Maintains a short-term memory of the conversation in each room for contextual responses.
- Configuration via environment variables.

## Setup

1.  **Clone this repo**

2.  **Install dependencies**
    Ensure you have Python 3.10+ installed.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables**
    Copy `.env.example` to `.env` and fill in your values:
    ```bash
    cp .env.example .env
    # Edit .env with your credentials
    ```
    Key variables:
    -   `MATRIX_HOMESERVER`: Your Matrix homeserver URL (e.g., `https://matrix.example.org`)
    -   `MATRIX_USER_ID`: Your bot's full Matrix user ID (e.g., `@your-bot:example.org`)
    -   `MATRIX_PASSWORD`: The bot's password
    -   `MATRIX_ROOM_ID`: The primary room ID for the bot to join on startup (e.g., `!yourRoom:example.org`)
    -   `OPENROUTER_API_KEY`: Your OpenRouter API key.
    -   `OPENROUTER_MODEL`: (Optional) AI model to use (default: `openai/gpt-4o-mini`).
    -   `DEVICE_NAME`: (Optional) Device name for the bot's Matrix session.
    -   `YOUR_SITE_URL`: (Optional) For OpenRouter API headers.
    -   `YOUR_SITE_NAME`: (Optional) For OpenRouter API headers.

    See `main.py` and `.env.example` for other optional polling and memory configuration variables.

    ### `.env` File Configuration

    # --- Ollama Configuration ---
    # Determines the primary LLM provider. Can be "openrouter" or "ollama".
    PRIMARY_LLM_PROVIDER=openrouter 
    # The API URL for your local Ollama instance.
    OLLAMA_API_URL=http://localhost:11434 
    # Default Ollama model for chat if Ollama is the primary provider.
    OLLAMA_DEFAULT_CHAT_MODEL=llama3 
    # Default Ollama model for summaries if Ollama is the primary provider.
    OLLAMA_DEFAULT_SUMMARY_MODEL=llama3 
    # Optional: How long Ollama should keep models loaded in memory (e.g., "5m", "1h").
    # OLLAMA_KEEP_ALIVE="5m"

4.  **Run the bot**
    ```bash
    python main.py
    ```
    The bot will attempt to fetch its display name from its Matrix profile. This name is used for mentions.

## Usage
-   **Activation**: In a Matrix room the bot has joined, mention the bot by its display name (e.g., "Hello @mybotname, can you help?"). This will activate the bot for that room.
-   **Interaction**: Once active, the bot will respond to messages sent in the room.
-   **Deactivation**: If there's a period of inactivity in the room, the bot will announce it's stopping active listening. Mention it again to re-activate.
-   The bot will also respond to direct messages if it's invited to a DM chat.

## Ollama Integration

This bot supports using local LLMs through Ollama as the primary inference engine. This allows for greater privacy, potential cost savings, and offline capabilities.

### How it Works

When `PRIMARY_LLM_PROVIDER` is set to `ollama`:

1.  The bot will use the specified `OLLAMA_DEFAULT_CHAT_MODEL` for handling chat interactions.
2.  It will use `OLLAMA_DEFAULT_SUMMARY_MODEL` for generating conversation summaries.
3.  The Ollama-powered LLM is provided with a special tool called `call_openrouter_llm`. This tool allows the local LLM to delegate complex queries or tasks requiring specific capabilities (e.g., larger context windows, proprietary models) to a more powerful cloud-based LLM via OpenRouter.

### Setting up Ollama

1.  **Install Ollama**: Follow the instructions on [ollama.com](https://ollama.com) to download and install Ollama for your operating system.
2.  **Pull Models**: Once Ollama is running, pull the models you intend to use. For example:
    ```bash
    ollama pull llama3 # For chat
    ollama pull mxbai-embed-large # Or another model suitable for summarization if different
    ```
    Ensure the model names in your `.env` file (`OLLAMA_DEFAULT_CHAT_MODEL`, `OLLAMA_DEFAULT_SUMMARY_MODEL`) match the models you have pulled.
3.  **Ensure Accessibility**: The Ollama API endpoint (default `http://localhost:11434`) must be accessible from where the bot is running. If running the bot in a Docker container, you might need to configure network settings accordingly (e.g., using `host.docker.internal` for the `OLLAMA_API_URL` or ensuring the container can reach the host's network).

### The `call_openrouter_llm` Tool

When Ollama is the primary LLM, it can decide to use the `call_openrouter_llm` tool. This tool allows the local model to effectively "ask for help" from a more capable model configured via OpenRouter for specific parts of a conversation or for tasks it deems too complex for itself.

The flow is as follows:

1.  User sends a message.
2.  Ollama (local LLM) processes the message.
3.  If Ollama decides the query is complex, it can choose to use the `call_openrouter_llm` tool, formulating a prompt for OpenRouter.
4.  The bot then makes a request to OpenRouter using the specified model (or a default OpenRouter model).
5.  The response from OpenRouter is returned to the Ollama LLM as the result of the tool call.
6.  Ollama then uses this result to formulate its final response to the user.

This hybrid approach provides flexibility, allowing you to leverage local LLMs for most tasks while still having access to powerful cloud models for more demanding requests.

## Security
-   Never commit your actual `.env` file or credentials to version control. The `.gitignore` file should prevent this.

## License
MIT
