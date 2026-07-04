# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Set the encoding to UTF-8 to prevent banner errors
$env:PYTHONUTF8=1

# Run the agent against the sample project
python main.py sample_project/requirements.txt
