# Matrix AI Chatbot: Your Smart, Flexible, and Private Conversation Partner

**Supercharge your Matrix chats with a powerful, async AI chatbot!** This bot seamlessly integrates with [OpenRouter](https://openrouter.ai/) for access to cutting-edge AI models and now features robust **Ollama support**, allowing you to run LLMs locally for enhanced privacy and control. Built with [matrix-nio](https://github.com/poljar/matrix-nio) and Python 3.10+.

## Key Features

*   **Dual AI Power:**
    *   **OpenRouter Integration:** Access a vast array of state-of-the-art LLMs from providers like OpenAI, Anthropic, Google, and more.
    *   **Ollama Local LLM Support:** Run powerful open-source models (e.g., Llama3, Mistral, Qwen) directly on your hardware for maximum privacy, offline capability, and cost-effectiveness.
    *   **Hybrid AI Strategy:** When using Ollama as the primary provider, the bot can intelligently delegate complex queries to OpenRouter, giving you the best of both worlds.
*   **Intelligent Interaction:**
    *   Listens for messages in configured Matrix rooms.
    *   Activates in a room when mentioned by its display name.
    *   Responds to all messages in a room once active.
    *   Handles direct messages seamlessly.
*   **Context-Aware Conversations:**
    *   Maintains short-term memory of conversations in each room for relevant and coherent responses.
    *   Supports persistent conversation summaries, allowing the bot to recall context from earlier parts of a discussion.
*   **Dynamic & User-Friendly:**
    *   **Active Listening Decay:** Gracefully deactivates after periods of inactivity and can be re-activated by a simple mention.
    *   **Tool Usage:** LLMs can use tools to perform actions like sending replies and reacting to messages, making interactions more dynamic.
*   **Easy Configuration:**
    *   Simple setup using environment variables (`.env` file).
    *   Clear instructions for both OpenRouter and Ollama setups.
*   **Developer Friendly:**
    *   Asynchronous architecture using `asyncio`.
    *   Modular design with a message bus for inter-service communication.

## Why Choose This Bot?

*   **Flexibility:** Choose between cloud-based AI for cutting-edge performance or local AI for privacy and control. The hybrid mode offers a unique balance.
*   **Privacy:** With Ollama, your conversations can stay entirely on your infrastructure.
*   **Cost-Effective:** Leveraging local models via Ollama can significantly reduce API costs.
*   **Always Learning:** Conversation summaries ensure the bot remembers important context over longer periods.
*   **Extensible:** The modular architecture allows for easier addition of new features and services.

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
    -   `OPENROUTER_API_KEY`: Your OpenRouter API key (required even if Ollama is primary, for the `call_openrouter_llm` tool).
    -   `OPENROUTER_MODEL`: (Optional) Default OpenRouter AI model to use (default: `openai/gpt-4o-mini`).
    -   `DEVICE_NAME`: (Optional) Device name for the bot's Matrix session.
    -   `YOUR_SITE_URL`: (Optional) For OpenRouter API headers.
    -   `YOUR_SITE_NAME`: (Optional) For OpenRouter API headers.

    See `room_logic_service.py` and `.env.example` for other optional polling, memory, and summarization configuration variables.

    ### `.env` File Configuration for LLM Providers

    You can choose between `openrouter` or `ollama` as your primary LLM provider.

    ```env
    # --- Primary LLM Provider ---
    # Determines the primary LLM provider. Can be "openrouter" or "ollama".
    PRIMARY_LLM_PROVIDER=openrouter # or "ollama"

    # --- OpenRouter Configuration (Always provide API key if Ollama might delegate) ---
    OPENROUTER_API_KEY=your-openrouter-api-key
    OPENROUTER_MODEL=openai/gpt-4o-mini # Default model for OpenRouter

    # --- Ollama Configuration (If using Ollama as primary or for delegation) ---
    OLLAMA_API_URL=http://localhost:11434 # The API URL for your local Ollama instance.
    OLLAMA_DEFAULT_CHAT_MODEL=llama3 # Default Ollama model for chat if Ollama is primary.
    OLLAMA_DEFAULT_SUMMARY_MODEL=llama3 # Default Ollama model for summaries.
    # Optional: How long Ollama should keep models loaded in memory (e.g., "5m", "1h").
    # This is passed to the Ollama API on each call.
    # OLLAMA_KEEP_ALIVE="5m"
    ```

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
-   **Tool Usage**: The AI can decide to use tools like `send_reply` or `react_to_message` to interact more dynamically.

## Ollama Integration: Power Up with Local LLMs

This bot features robust support for [Ollama](https://ollama.com), allowing you to run powerful large language models directly on your own hardware. This brings several advantages:

*   **Enhanced Privacy:** Keep your conversation data entirely within your control.
*   **Reduced Costs:** Avoid API fees associated with cloud-based LLM providers.
*   **Offline Capabilities:** (Depending on your setup) Potentially use the bot even without internet access to external services.
*   **Customization:** Easily experiment with a wide range of open-source models.

### How it Works with Ollama

When `PRIMARY_LLM_PROVIDER` in your `.env` file is set to `ollama`:

1.  The bot directs chat and summarization tasks to your configured Ollama instance and models (`OLLAMA_DEFAULT_CHAT_MODEL`, `OLLAMA_DEFAULT_SUMMARY_MODEL`).
2.  **Intelligent Delegation (Hybrid AI):** The Ollama-powered LLM is equipped with a special tool: `call_openrouter_llm`. This unique feature allows your local LLM to intelligently delegate specific queries or tasks that it deems too complex, require capabilities it doesn't possess (like a much larger context window), or would benefit from a specific proprietary model, to a more powerful or specialized LLM via OpenRouter.

### Setting up Ollama

1.  **Install Ollama**: Follow the instructions on [ollama.com](https://ollama.com) to download and install Ollama for your operating system.
2.  **Pull Models**: Once Ollama is running, pull the models you intend to use. For example:
    ```bash
    ollama pull llama3 # For chat
    ollama pull mxbai-embed-large # Or another model suitable for summarization if different
    ```
    Ensure the model names in your `.env` file (`OLLAMA_DEFAULT_CHAT_MODEL`, `OLLAMA_DEFAULT_SUMMARY_MODEL`) match the models you have pulled and are available in your Ollama instance.
3.  **Ensure Accessibility**: The Ollama API endpoint (default `http://localhost:11434`) must be accessible from where the bot is running.
    *   If running the bot in a Docker container, you might need to adjust your network settings. For example, on Linux, you might use `http://172.17.0.1:11434` (default Docker host IP) or configure Docker to use `host-gateway` via `extra_hosts` in your Docker Compose file if `OLLAMA_API_URL` is set to `http://host.docker.internal:11434`.
    *   Ensure your Ollama server is configured to listen on an accessible network interface if it's not on the same machine (e.g., by setting `OLLAMA_HOST=0.0.0.0` when starting the Ollama server).

### The `call_openrouter_llm` Tool: Bridging Local and Cloud AI

When Ollama is the primary LLM, it can decide to use the `call_openrouter_llm` tool. This tool allows the local model to effectively "ask for help" from a more capable model configured via OpenRouter for specific parts of a conversation or for tasks it deems too complex for itself.

The flow is as follows:

1.  User sends a message.
2.  Ollama (local LLM) processes the message.
3.  If Ollama decides the query is complex, it can choose to use the `call_openrouter_llm` tool, formulating a prompt for OpenRouter.
4.  The bot then makes a request to OpenRouter using the specified model (or a default OpenRouter model if not specified by Ollama).
5.  The response from OpenRouter (including any text or tool calls it might make) is returned to the Ollama LLM as the result of its `call_openrouter_llm` tool call.
6.  Ollama then processes this information and formulates its final response to the user, potentially incorporating the insights or actions from the more powerful cloud model.

This hybrid approach offers unparalleled flexibility, allowing you to primarily rely on local LLMs for privacy and speed while seamlessly escalating to more capable cloud models when necessary.

## Security
-   Never commit your actual `.env` file or credentials to version control. The `.gitignore` file should prevent this.

## License
MIT
