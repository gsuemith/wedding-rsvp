"""
Vercel serverless function handler for FastAPI application
"""
import sys
import os
import traceback

# Add project root to path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from mangum import Mangum
    from src.main import app
    
    # Create the handler for Vercel
    # Note: In serverless environments, database connections should use connection pooling
    # The startup event will run on first invocation
    handler = Mangum(app)
except Exception as e:
    # If there's an import error, create a handler that returns the error details
    def handler(event, context):
        error_msg = f"Error initializing application: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Log to Vercel function logs
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': error_msg
        }

