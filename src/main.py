from fastapi import FastAPI
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
    rsvp_response = Column(SQLEnum(RSVPResponse), nullable=False)

    mailing_address_ref = relationship("MailingAddressDB", back_populates="invitees")


# Junction table for events and invitees (many-to-many)
event_invitee_association = Table(
    "event_invitee_association",
    Base.metadata,
    Column("event_id", PGUUID(as_uuid=True), ForeignKey("events.id"), primary_key=True),
    Column("invitee_id", PGUUID(as_uuid=True), ForeignKey("wedding_invitees.id"), primary_key=True),
)


class EventDB(Base):
    __tablename__ = "events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    part_of = Column(PGUUID(as_uuid=True), ForeignKey("events.id"), nullable=True)

    invitees = relationship(
        "WeddingInviteeDB",
        secondary=event_invitee_association,
        backref="events"
    )


# Create tables
def init_db():
    # Ensure engine is initialized before creating tables
    db_engine, _ = get_database_engine()
    Base.metadata.create_all(bind=db_engine)


app = FastAPI()

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


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

