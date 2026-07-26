
import os
import json
import hmac
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from flask import Flask, abort, render_template_string, request

app = Flask(__name__)

CONFIG_PATH = '/app/data/config.json'
SETUP_TOKEN = secrets.token_urlsafe(32)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MatrixBot Setup</title>
    <style>
        body { font-family: sans-serif; background-color: #f4f4f9; color: #333; }
        .container { max-width: 500px; margin: 50px auto; padding: 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #444; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        input[type="text"], input[type="password"] { width: 100%; padding: 8px; margin-top: 5px; border-radius: 4px; border: 1px solid #ddd; }
        input[type="submit"] { margin-top: 20px; padding: 10px 15px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        input[type="submit"]:hover { background-color: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>MatrixBot Setup</h1>
        <p>Please enter your secrets to configure the bot.</p>
        <form method="POST" action="/setup">
            <input type="hidden" name="setup_token" value="{{ setup_token }}">
            <label for="matrix_homeserver">Matrix Homeserver URL</label>
            <input type="text" id="matrix_homeserver" name="matrix_homeserver" placeholder="e.g., https://matrix-client.matrix.org" required>

            <label for="matrix_user_id">Matrix User ID</label>
            <input type="text" id="matrix_user_id" name="matrix_user_id" placeholder="e.g., @my-bot:matrix.org" required>

            <label for="matrix_password">Matrix Password</label>
            <input type="password" id="matrix_password" name="matrix_password" required>

            <label for="openrouter_api_key">OpenRouter API Key</label>
            <input type="password" id="openrouter_api_key" name="openrouter_api_key" required>
            
            <input type="submit" value="Save Configuration">
        </form>
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Setup Complete</title>
    <style>
        body { font-family: sans-serif; background-color: #f4f4f9; text-align: center; padding-top: 50px; }
        .container { max-width: 500px; margin: auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #28a745; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Configuration Saved!</h1>
        <p>Your configuration has been saved successfully.</p>
        <p>Copy this one-time management token now:</p>
        <p><code>{{ admin_token }}</code></p>
        <p>Please restart the Docker container to start the bot.</p>
        <p>You can do this by running: <code>docker-compose restart</code></p>
    </div>
</body>
</html>
"""

@app.route('/')
def form():
    return render_template_string(HTML_TEMPLATE, setup_token=SETUP_TOKEN)

@app.route('/setup', methods=['POST'])
def setup():
    supplied_token = request.form.get("setup_token", "")
    if not hmac.compare_digest(supplied_token, SETUP_TOKEN):
        abort(403)

    homeserver = request.form.get("matrix_homeserver", "").strip()
    user_id = request.form.get("matrix_user_id", "").strip()
    matrix_password = request.form.get("matrix_password", "")
    openrouter_key = request.form.get("openrouter_api_key", "")
    if not homeserver.startswith("https://") or len(homeserver) > 2048:
        abort(400, "Matrix homeserver must be a valid HTTPS URL")
    if not user_id.startswith("@") or ":" not in user_id or len(user_id) > 255:
        abort(400, "Invalid Matrix user ID")
    if not matrix_password or len(matrix_password) > 4096:
        abort(400, "Invalid Matrix password")
    if not openrouter_key or len(openrouter_key) > 4096:
        abort(400, "Invalid OpenRouter API key")

    admin_token = secrets.token_urlsafe(32)
    config = {
        'MATRIX_HOMESERVER': homeserver,
        'MATRIX_USER_ID': user_id,
        'MATRIX_PASSWORD': matrix_password,
        'OPENROUTER_API_KEY': openrouter_key,
        'ADMIN_API_TOKEN': admin_token,
        'INTEGRATION_CREDENTIAL_KEY': Fernet.generate_key().decode("ascii"),
    }

    config_path = Path(CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_path = config_path.with_suffix(".json.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as config_file:
            descriptor = -1
            json.dump(config, config_file, indent=4)
            config_file.flush()
            os.fsync(config_file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    return render_template_string(SUCCESS_TEMPLATE, admin_token=admin_token)

def run_setup_server():
    app.run(host=os.getenv("SETUP_SERVER_HOST", "127.0.0.1"), port=8000)

if __name__ == '__main__':
    run_setup_server()
