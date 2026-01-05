"""
Vercel serverless function handler for FastAPI application
"""
import sys
import os
import json
from io import BytesIO

# Add project root to path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.main import app

async def call_app(scope, receive, send):
    """
    ASGI application callable
    """
    await app(scope, receive, send)

def handler(request):
    """
    Vercel Python function handler
    Converts Vercel request to ASGI and handles the response
    """
    from starlette.requests import Request
    from starlette.responses import Response
    import asyncio
    
    # Extract request details
    method = request.get('method', 'GET')
    path = request.get('path', '/')
    headers = dict(request.get('headers', {}))
    body = request.get('body', '')
    query_params = request.get('queryStringParameters') or {}
    
    # Build query string
    query_string = '&'.join([f"{k}={v}" for k, v in query_params.items()]).encode()
    
    # Create ASGI scope
    scope = {
        'type': 'http',
        'method': method,
        'path': path,
        'raw_path': path.encode(),
        'query_string': query_string,
        'headers': [[k.encode(), str(v).encode()] for k, v in headers.items()],
        'client': ['127.0.0.1', 0],
        'server': ['localhost', 80],
        'scheme': 'https',
        'http_version': '1.1',
        'asgi': {'version': '3.0', 'spec_version': '2.0'},
    }
    
    # Response data
    response_data = {'status': 200, 'headers': [], 'body': b''}
    
    async def receive():
        return {
            'type': 'http.request',
            'body': body.encode() if isinstance(body, str) else body,
            'more_body': False
        }
    
    async def send(message):
        if message['type'] == 'http.response.start':
            response_data['status'] = message['status']
            response_data['headers'] = message['headers']
        elif message['type'] == 'http.response.body':
            response_data['body'] += message.get('body', b'')
    
    # Run the ASGI app
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(call_app(scope, receive, send))
        loop.close()
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
    
    # Convert response
    response_headers = {}
    for header in response_data['headers']:
        if len(header) == 2:
            key = header[0].decode() if isinstance(header[0], bytes) else header[0]
            value = header[1].decode() if isinstance(header[1], bytes) else header[1]
            response_headers[key] = value
    
    body = response_data['body']
    if isinstance(body, bytes):
        try:
            body = body.decode()
        except:
            pass
    
    return {
        'statusCode': response_data['status'],
        'headers': response_headers,
        'body': body
    }

