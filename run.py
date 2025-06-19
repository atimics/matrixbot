import os
import json
import subprocess

CONFIG_PATH = '/app/data/config.json'

def main():
    if not os.path.exists(CONFIG_PATH):
        print("Configuration file not found. Starting setup server.")
        from setup_server import run_setup_server
        run_setup_server()
    else:
        print("Configuration file found. Starting MatrixBot.")
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        for key, value in config.items():
            os.environ[key] = value
            
        # Replace this with the actual command to run your bot
        subprocess.run(["python", "-m", "chatbot.main", CONFIG_PATH])

if __name__ == "__main__":
    main()
