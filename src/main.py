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
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/wedding_rsvp"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
    Base.metadata.create_all(bind=engine)


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
    init_db()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

