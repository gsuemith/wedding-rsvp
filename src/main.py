from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import create_engine, Column, String, ForeignKey, Enum as SQLEnum, DateTime, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from dotenv import load_dotenv

load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")

# Lazy initialization of database engine
_engine = None
_SessionLocal = None

def get_database_engine():
    """Get or create the database engine, with validation"""
    global _engine, _SessionLocal
    
    if _engine is None:
        if not DATABASE_URL:
            raise ValueError(
                "DATABASE_URL environment variable is not set. "
                "Please set it in your Vercel project settings. "
                "Go to: Project Settings → Environment Variables → Add DATABASE_URL"
            )
        
        # Validate it's not the default localhost
        if "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL:
            raise ValueError(
                "DATABASE_URL appears to point to localhost, which won't work on Vercel. "
                "Please use a remote PostgreSQL database (Supabase, Neon, Railway, etc.) "
                "and set the DATABASE_URL environment variable in Vercel."
            )
        
        # Configure engine for serverless environments
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=1,  # Smaller pool for serverless
            max_overflow=0,  # No overflow for serverless
            connect_args={
                "connect_timeout": 10,  # 10 second timeout
            }
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    
    return _engine, _SessionLocal

# Initialize for backward compatibility
# Don't initialize at import time - let it fail lazily with a clear error
engine = None
SessionLocal = None

# Try to initialize, but don't fail if DATABASE_URL is not set yet
# This allows the app to start and show a clear error when database is accessed
try:
    if DATABASE_URL:
        engine, SessionLocal = get_database_engine()
except Exception as e:
    import logging
    logging.warning(f"Database not initialized: {str(e)}")
    engine = None
    SessionLocal = None
Base = declarative_base()


class RSVPResponse(str, Enum):
    YES = "yes"
    NO = "no"
    PENDING = "pending"


class MailingAddress(BaseModel):
    id: UUID
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    email: Optional[str] = None
    phone_number: Optional[str] = None


class WeddingInvitee(BaseModel):
    id: UUID
    full_name: str
    mailing_address: UUID
    rsvp_response: RSVPResponse


# SQLAlchemy Models
class MailingAddressDB(Base):
    __tablename__ = "mailing_addresses"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    address_line_1 = Column(String, nullable=False)
    address_line_2 = Column(String, nullable=True)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)  # Hashed password for RSVP updates

    invitees = relationship("WeddingInviteeDB", back_populates="mailing_address_ref")


class WeddingInviteeDB(Base):
    __tablename__ = "wedding_invitees"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    full_name = Column(String, nullable=False)
    mailing_address_id = Column(PGUUID(as_uuid=True), ForeignKey("mailing_addresses.id"), nullable=False)

    mailing_address_ref = relationship("MailingAddressDB", back_populates="invitees")
    event_associations = relationship("EventInviteeAssociation", back_populates="invitee")


# Association model for events and invitees (many-to-many with rsvp_response)
class EventInviteeAssociation(Base):
    __tablename__ = "event_invitee_association"

    event_id = Column(PGUUID(as_uuid=True), ForeignKey("events.id"), primary_key=True)
    invitee_id = Column(PGUUID(as_uuid=True), ForeignKey("wedding_invitees.id"), primary_key=True)
    rsvp_response = Column(SQLEnum(RSVPResponse), nullable=False, default=RSVPResponse.PENDING)

    event = relationship("EventDB", back_populates="invitee_associations")
    invitee = relationship("WeddingInviteeDB", back_populates="event_associations")


class EventDB(Base):
    __tablename__ = "events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    part_of = Column(PGUUID(as_uuid=True), ForeignKey("events.id"), nullable=True)

    invitee_associations = relationship("EventInviteeAssociation", back_populates="event")


# Create tables
def init_db():
    # Ensure engine is initialized before creating tables
    db_engine, _ = get_database_engine()
    Base.metadata.create_all(bind=db_engine)
    
    # Add missing columns to existing tables (migration)
    # This handles the case where tables exist but columns were added later
    from sqlalchemy import text, inspect
    
    inspector = inspect(db_engine)
    
    # Check mailing_addresses table
    if 'mailing_addresses' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('mailing_addresses')]
        
        with db_engine.connect() as conn:
            if 'email' not in existing_columns:
                conn.execute(text("ALTER TABLE mailing_addresses ADD COLUMN email VARCHAR"))
                conn.commit()
            
            if 'phone_number' not in existing_columns:
                conn.execute(text("ALTER TABLE mailing_addresses ADD COLUMN phone_number VARCHAR"))
                conn.commit()
            
            if 'password_hash' not in existing_columns:
                conn.execute(text("ALTER TABLE mailing_addresses ADD COLUMN password_hash VARCHAR"))
                conn.commit()
    
    # Migrate rsvp_response from wedding_invitees to event_invitee_association
    # First, handle wedding_invitees table - make rsvp_response nullable (we no longer use it)
    if 'wedding_invitees' in inspector.get_table_names():
        existing_invitee_columns = [col['name'] for col in inspector.get_columns('wedding_invitees')]
        
        with db_engine.connect() as conn:
            # Make rsvp_response nullable in wedding_invitees (we moved it to association table)
            if 'rsvp_response' in existing_invitee_columns:
                # First, set a default value for any NULL values (safety measure)
                try:
                    conn.execute(text("UPDATE wedding_invitees SET rsvp_response = 'pending' WHERE rsvp_response IS NULL"))
                    conn.commit()
                except Exception:
                    conn.rollback()
                
                # Always try to drop NOT NULL constraint (will fail silently if already nullable)
                try:
                    conn.execute(text("ALTER TABLE wedding_invitees ALTER COLUMN rsvp_response DROP NOT NULL"))
                    conn.commit()
                except Exception as e:
                    # Column might already be nullable, or constraint might not exist
                    # This is fine - just continue
                    conn.rollback()
                    pass
    
    # Now handle event_invitee_association table
    if 'event_invitee_association' in inspector.get_table_names():
        existing_assoc_columns = [col['name'] for col in inspector.get_columns('event_invitee_association')]
        
        with db_engine.connect() as conn:
            # Add rsvp_response column to association table if it doesn't exist
            if 'rsvp_response' not in existing_assoc_columns:
                conn.execute(text("ALTER TABLE event_invitee_association ADD COLUMN rsvp_response VARCHAR"))
                conn.commit()
                
                # Migrate existing data: copy rsvp_response from wedding_invitees to associations if possible
                # Otherwise set to PENDING as default
                try:
                    # Try to migrate from wedding_invitees if the column still exists
                    conn.execute(text("""
                        UPDATE event_invitee_association eia
                        SET rsvp_response = COALESCE(
                            (SELECT wi.rsvp_response::text 
                             FROM wedding_invitees wi 
                             WHERE wi.id = eia.invitee_id 
                             AND wi.rsvp_response IS NOT NULL),
                            'pending'
                        )
                        WHERE eia.rsvp_response IS NULL
                    """))
                except Exception:
                    # If migration fails, just set to pending
                    conn.execute(text("""
                        UPDATE event_invitee_association 
                        SET rsvp_response = 'pending' 
                        WHERE rsvp_response IS NULL
                    """))
                conn.commit()
                
                # Make rsvp_response NOT NULL after setting defaults
                conn.execute(text("ALTER TABLE event_invitee_association ALTER COLUMN rsvp_response SET NOT NULL"))
                conn.commit()


app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://deploy-preview-3--elizabethandcarlos2026.netlify.app",
        "https://carlosandelizabeth2026.com",
        "https://www.carlosandelizabeth2026.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from .guest import router as guest_router
from .rsvp import router as rsvp_router
from .event import router as event_router

app.include_router(guest_router)
app.include_router(rsvp_router)
app.include_router(event_router)


@app.on_event("startup")
async def startup_event():
    # Initialize database tables
    # Note: In serverless environments, this runs on first invocation
    # Consider using connection pooling for production
    try:
        init_db()
    except Exception as e:
        # Log error but don't crash the app - tables might already exist
        # or database connection might fail in serverless environment
        import logging
        logging.warning(f"Database initialization warning: {str(e)}")

# Also ensure migrations run on first database access (for serverless environments)
_migrations_run = False

def ensure_migrations():
    """Ensure database migrations have run."""
    global _migrations_run
    if not _migrations_run:
        try:
            init_db()
            _migrations_run = True
        except Exception as e:
            import logging
            logging.warning(f"Migration check warning: {str(e)}")


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

