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

    See `main_orchestrator.py` and `.env.example` for other optional polling and memory configuration variables.

4.  **Run the bot**
    ```bash
    python main_orchestrator.py
    ```
    The bot will attempt to fetch its display name from its Matrix profile. This name is used for mentions.

## Usage
-   **Activation**: In a Matrix room the bot has joined, mention the bot by its display name (e.g., "Hello @mybotname, can you help?"). This will activate the bot for that room.
-   **Interaction**: Once active, the bot will respond to messages sent in the room.
-   **Deactivation**: If there's a period of inactivity in the room, the bot will announce it's stopping active listening. Mention it again to re-activate.
-   The bot will also respond to direct messages if it's invited to a DM chat.

## Security
-   Never commit your actual `.env` file or credentials to version control. The `.gitignore` file should prevent this.

## License
MIT
