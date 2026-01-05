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

## Deployment to Vercel

This application can be deployed to Vercel serverless functions using Mangum as an ASGI adapter.

### Prerequisites

1. A Vercel account
2. PostgreSQL database (can use services like Supabase, Neon, or Railway)
3. Vercel CLI installed (optional, for local testing)

### Deployment Steps

1. **Set up environment variables in Vercel:**
   - Go to your Vercel project settings
   - Navigate to "Environment Variables"
   - Add `DATABASE_URL` with your PostgreSQL connection string

2. **Deploy via Git:**
   - Connect your repository to Vercel
   - Vercel will automatically detect the `vercel.json` configuration
   - The build will install dependencies and set up the function

3. **Or deploy via CLI:**
   ```bash
   npm install -g vercel
   vercel login
   vercel --prod
   ```

### Important Notes for Serverless Deployment

- **Database Connections**: In serverless environments, consider using connection pooling (e.g., PgBouncer) or a serverless-friendly database service
- **Cold Starts**: First request may be slower due to function initialization
- **Function Timeout**: Vercel Functions have a 10-second timeout on the free tier (Hobby), 60 seconds on Pro plan
- **API Routes**: All routes will be available at the root of your Vercel deployment URL

### Local Testing with Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Run locally
vercel dev
```

The API will be available at `http://localhost:3000/`

