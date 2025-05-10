# Matrix + OpenRouter Chatbot

A modern, async Matrix chatbot that uses OpenRouter (GPT) for AI-powered responses. Built with [matrix-nio](https://github.com/poljar/matrix-nio) and Python 3.7+.

## Features
- Listens for messages in a Matrix room or direct messages
- Responds to messages prefixed with `!bot` or to DMs
- Uses OpenRouter API (GPT models) for generating responses
- Modern, environment-variable-based configuration

## Setup

1. **Clone this repo**

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env with your credentials
```

- `MATRIX_HOMESERVER`: Your Matrix homeserver URL (e.g. https://matrix.example.org)
- `MATRIX_USER_ID`: Your bot's full Matrix user ID (e.g. @your-bot:example.org)
- `MATRIX_PASSWORD`: The bot's password
- `MATRIX_ROOM_ID`: The room ID to join (e.g. !yourRoom:example.org)
- `DEVICE_NAME`: (Optional) Device name for the bot
- `OPENROUTER_API_KEY`: Your OpenRouter API key
- `OPENROUTER_MODEL`: (Optional) Model to use (default: openai/gpt-4o-mini)
- `YOUR_SITE_URL`: (Optional) For OpenRouter leaderboards
- `YOUR_SITE_NAME`: (Optional) For OpenRouter leaderboards

4. **Run the bot**

```bash
python main.py
```

## Usage
- In the configured room, type `!bot your question` to get a response.
- The bot will also respond to direct messages.

## Security
- Never commit your real `.env` file or credentials to version control.

## License
MIT
