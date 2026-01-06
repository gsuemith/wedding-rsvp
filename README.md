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

### Root Endpoints
- `GET /` - Returns a hello world message
- `GET /health` - Health check endpoint

### Guest Endpoints
- `POST /guest/event/{event_id}` - Create guests for an event
  - Creates a mailing address and wedding invitees for a list of names
  - All invitees share the same mailing address and are associated with the specified event
  - Optional password field for RSVP updates
- `GET /guest/{guest_id}` - Get guest details with events
  - Returns guest name, mailing address, and all events they're attending
  - For each event, includes all guests with the same address attending that event
- `POST /guest/rsvp-info` - Get RSVP information for guests
  - Requires: email, phone_number, password, and event_id
  - Returns mailing address and RSVP information for all guests at that address for the specified event

### RSVP Endpoints
- `POST /rsvp` - Update RSVP responses
  - Requires: mailing_address_id and list of invitee RSVP updates
  - Updates RSVP responses for multiple invitees associated with a mailing address
- `POST /rsvp/event/{event_id}` - Update RSVP using guest credentials
  - Requires: email, phone_number, password, and list of invitee RSVP updates
  - Allows guests to update their RSVP using their credentials

### Event Endpoints
- `GET /event` - Get all events
  - Returns all top-level events (events that are not part of another event)
  - Optional query parameter: `part_of` (UUID) - returns all sub-events of the specified parent event
- `POST /event` - Create or update an event
  - Creates a new event with name and date
  - Optional query parameter: `id` (UUID) - if provided, updates existing event's name and date (ignores part_of)
  - Optional field: `part_of` (UUID) - indicates this event is part of a larger event
- `DELETE /event/{event_id}` - Delete an event
  - Cannot delete if the event has sub-events or guests
  - Optional query parameter: `delete_sub_events` (bool) - if true, deletes event and sub-events (only if no guests exist)
- `POST /event/{event_id}/clear-guests` - Remove all guests from an event
  - Removes the association between the event and invitees (does not delete the invitees themselves)
- `GET /event/{event_id}/guests` - Get guests for an event
  - Returns list of wedding invitees for the event
  - Optional query parameter: `response` (yes/no/pending) - filter by RSVP response

### Documentation
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Deployment to Vercel

This application can be deployed to Vercel serverless functions using Mangum as an ASGI adapter.

### Prerequisites

1. A Vercel account
2. PostgreSQL database (can use services like Supabase, Neon, or Railway)
3. Vercel CLI installed (optional, for local testing)

### Deployment Steps

1. **Set up environment variables in Vercel (REQUIRED):**
   - Go to your Vercel project settings
   - Navigate to "Environment Variables"
   - Add `DATABASE_URL` with your PostgreSQL connection string
   - **Important:** Without this, the application will fail to connect to the database
   - Example: `postgresql://user:password@host:5432/database`
   - You can use services like Supabase, Neon, Railway, or any PostgreSQL provider

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

