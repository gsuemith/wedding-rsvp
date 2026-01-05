"""
Vercel serverless function handler for FastAPI application
"""
import sys
import os

# Add project root to path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mangum import Mangum
from src.main import app

# Create the handler for Vercel
# Mangum automatically handles the ASGI to Lambda/Vercel conversion
handler = Mangum(app, lifespan="off")

