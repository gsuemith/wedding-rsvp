"""
Vercel FastAPI application entrypoint
According to Vercel docs: https://vercel.com/docs/frameworks/backend/fastapi
"""
import sys
import os

# Add project root to path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and export the FastAPI app instance
# Vercel will automatically detect and use this 'app' variable
from src.main import app

