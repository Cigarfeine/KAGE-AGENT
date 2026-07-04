# sample_project/app.py
# A mock application to demonstrate usage analysis.

# 1. ACTIVELY USED: flask
# We import Flask and actually use it to define an app.
from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World!"

# 2. ACTIVELY USED: pillow
# We import PIL.Image and actually call Image.open()
from PIL import Image

def process_image(path):
    img = Image.open(path)
    return img

# 3. IMPORTED, NOT CALLED: pyyaml
# We import yaml, but we never actually call yaml.load() or reference it again.
# The tool should flag this as "IMPORTED, NOT CALLED".
import yaml

# 4. NOT FOUND IN SOURCE: jinja2 (and others)
# jinja2, django, requests, urllib3 are in requirements.txt but NEVER imported anywhere in the code.
# The tool should flag them as "NOT FOUND IN SOURCE".

if __name__ == "__main__":
    app.run()
