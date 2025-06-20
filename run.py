import os
import subprocess

def main():
    # Check if required environment variables are set
    required_vars = ['OPENROUTER_API_KEY', 'MATRIX_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Required environment variables not found: {', '.join(missing_vars)}")
        print("Starting setup server for configuration.")
        from setup_server import run_setup_server
        run_setup_server()
    else:
        print("Environment variables configured. Starting MatrixBot.")
        # Replace this with the actual command to run your bot
        subprocess.run(["python", "-m", "chatbot.main"])

if __name__ == "__main__":
    main()
