"""
Netlify Functions handler for FastAPI application
"""
import sys
import os

# Add project root to path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

from mangum import Mangum
from src.main import app

# Create the handler
# Note: In serverless environments, database connections should use connection pooling
# The startup event will run on first invocation
handler = Mangum(app)

