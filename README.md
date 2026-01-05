# Wedding RSVP FastAPI Application

A basic FastAPI application with PostgreSQL database.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up PostgreSQL database:
   - Make sure PostgreSQL is installed and running
   - Create a database (or use the default):
   ```bash
   createdb wedding_rsvp
   ```

3. Configure database connection (optional):
   - Create a `.env` file with your database URL:
   ```
   DATABASE_URL=postgresql://username:password@localhost:5432/wedding_rsvp
   ```
   - If no `.env` file is provided, it defaults to `postgresql://postgres:postgres@localhost:5432/wedding_rsvp`

4. Run the application:
```bash
uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`

The database tables will be automatically created on application startup.

## Endpoints

- `GET /` - Returns a hello world message
- `GET /health` - Health check endpoint
- `POST /guest/{event_id}` - Create guests for an event
- `GET /guest/{guest_id}` - Get guest details with events
- `POST /rsvp` - Update RSVP responses
- `GET /event/{event_id}/guests` - Get guests for an event
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Deployment to Netlify Functions

This application can be deployed to Netlify Functions using Mangum as an ASGI adapter.

### Prerequisites

1. A Netlify account
2. PostgreSQL database (can use services like Supabase, Neon, or Railway)
3. Netlify CLI installed (optional, for local testing)

### Deployment Steps

1. **Set up environment variables in Netlify:**
   - Go to your Netlify site settings
   - Navigate to "Environment variables"
   - Add `DATABASE_URL` with your PostgreSQL connection string

2. **Deploy via Git:**
   - Connect your repository to Netlify
   - Netlify will automatically detect the `netlify.toml` configuration
   - The build will install dependencies and set up the function

3. **Or deploy via CLI:**
   ```bash
   npm install -g netlify-cli
   netlify login
   netlify deploy --prod
   ```

### Important Notes for Serverless Deployment

- **Database Connections**: In serverless environments, consider using connection pooling (e.g., PgBouncer) or a serverless-friendly database service
- **Cold Starts**: First request may be slower due to function initialization
- **Function Timeout**: Netlify Functions have a 10-second timeout on the free tier, 26 seconds on paid plans
- **API Routes**: All routes will be available under `/.netlify/functions/api/` or via the redirect at `/api/*`

### Local Testing with Netlify Functions

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Run locally
netlify dev
```

The API will be available at `http://localhost:8888/.netlify/functions/api/`

