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
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

