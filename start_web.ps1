# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Start the ADK web server in the background
Start-Process "http://127.0.0.1:8000"

# Run the web server
adk web
