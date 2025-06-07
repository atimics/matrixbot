
import os
import json
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

CONFIG_PATH = '/app/data/config.json'

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
        <p>Please restart the Docker container to start the bot.</p>
        <p>You can do this by running: <code>docker-compose restart</code></p>
    </div>
</body>
</html>
"""

@app.route('/')
def form():
    return render_template_string(HTML_TEMPLATE)

@app.route('/setup', methods=['POST'])
def setup():
    config = {
        'MATRIX_HOMESERVER': request.form['matrix_homeserver'],
        'MATRIX_USER_ID': request.form['matrix_user_id'],
        'MATRIX_PASSWORD': request.form['matrix_password'],
        'OPENROUTER_API_KEY': request.form['openrouter_api_key']
    }

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
    
    # Set restrictive file permissions
    os.chmod(CONFIG_PATH, 0o600)

    return render_template_string(SUCCESS_TEMPLATE)

def run_setup_server():
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    run_setup_server()
