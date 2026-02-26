import os
os.environ.pop('OPENAI_API_KEY', None)
os.environ.pop('ANTHROPIC_API_KEY', None)

from src.main import app
print("App imported OK")
