from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    EventDB,
    RSVPResponse,
    MailingAddress,
    WeddingInvitee,
)


# Request/Response Models
class MailingAddressInput(BaseModel):
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str


class GuestRequest(BaseModel):
    names: List[str]
    mailing_address: MailingAddressInput


class GuestResponse(BaseModel):
    mailing_address: MailingAddress
    invitees: List[WeddingInvitee]


class EventWithGuests(BaseModel):
    id: UUID
    name: str
    date: datetime
    guests: List[WeddingInvitee]  # All guests with same address attending this event


class GuestDetailResponse(BaseModel):
    full_name: str
    mailing_address: MailingAddress
    events: List[EventWithGuests]


# Database dependency
def get_db():
    from .main import SessionLocal, get_database_engine
    
    # Ensure database is initialized
    if SessionLocal is None:
        try:
            _, SessionLocal = get_database_engine()
        except ValueError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Database configuration error: {str(e)}"
            )
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter()


@router.post("/guest/{event_id}", response_model=GuestResponse)
async def create_guests(event_id: UUID, request: GuestRequest, db: Session = Depends(get_db)):
    """
    Create a mailing address and wedding invitees for a list of names.
    All invitees share the same mailing address, have RSVP status set to pending,
    and are associated with the specified event.
    """
    # Verify event exists
    event = db.query(EventDB).filter(EventDB.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
        )
    
    # Create mailing address
    mailing_address_db = MailingAddressDB(
        address_line_1=request.mailing_address.address_line_1,
        address_line_2=request.mailing_address.address_line_2,
        city=request.mailing_address.city,
        state=request.mailing_address.state,
        postal_code=request.mailing_address.postal_code,
    )
    db.add(mailing_address_db)
    db.flush()  # Flush to get the ID without committing

    # Create invitees for each name
    invitees_db = []
    for name in request.names:
        invitee_db = WeddingInviteeDB(
            full_name=name,
            mailing_address_id=mailing_address_db.id,
            rsvp_response=RSVPResponse.PENDING,
        )
        db.add(invitee_db)
        invitees_db.append(invitee_db)
    
    # Flush to get invitee IDs before associating with event
    db.flush()
    
    # Associate invitees with the event (populates junction table)
    event.invitees.extend(invitees_db)

    # Commit all changes
    db.commit()

    # Refresh to ensure we have the latest data
    db.refresh(mailing_address_db)
    for invitee_db in invitees_db:
        db.refresh(invitee_db)

    # Build response
    mailing_address_response = MailingAddress(
        id=mailing_address_db.id,
        address_line_1=mailing_address_db.address_line_1,
        address_line_2=mailing_address_db.address_line_2,
        city=mailing_address_db.city,
        state=mailing_address_db.state,
        postal_code=mailing_address_db.postal_code,
    )

    invitees_response = [
        WeddingInvitee(
            full_name=invitee_db.full_name,
            mailing_address=invitee_db.mailing_address_id,
            rsvp_response=invitee_db.rsvp_response,
        )
        for invitee_db in invitees_db
    ]

    return GuestResponse(
        mailing_address=mailing_address_response,
        invitees=invitees_response,
    )


@router.get("/guest/{guest_id}", response_model=GuestDetailResponse)
async def get_guest(guest_id: UUID, db: Session = Depends(get_db)):
    """
    Get guest details including their name, mailing address, and all events they're attending.
    For each event, includes a list of all guests with the same address attending that event.
    """
    # Find the invitee
    invitee = db.query(WeddingInviteeDB).filter(WeddingInviteeDB.id == guest_id).first()
    
    if not invitee:
        raise HTTPException(
            status_code=404,
            detail=f"Guest with id {guest_id} not found"
        )
    
    # Get mailing address
    mailing_address = invitee.mailing_address_ref
    mailing_address_response = MailingAddress(
        id=mailing_address.id,
        address_line_1=mailing_address.address_line_1,
        address_line_2=mailing_address.address_line_2,
        city=mailing_address.city,
        state=mailing_address.state,
        postal_code=mailing_address.postal_code,
    )
    
    # Get all events this invitee is attending (through the backref relationship)
    events = invitee.events
    
    # Build events with guests list
    events_with_guests = []
    for event in events:
        # Find all invitees with the same mailing address who are also in this event
        same_address_invitees = [
            e for e in event.invitees 
            if e.mailing_address_id == invitee.mailing_address_id
        ]
        
        # Convert to response models
        guests_response = [
            WeddingInvitee(
                full_name=inv.full_name,
                mailing_address=inv.mailing_address_id,
                rsvp_response=inv.rsvp_response,
            )
            for inv in same_address_invitees
        ]
        
        events_with_guests.append(
            EventWithGuests(
                id=event.id,
                name=event.name,
                date=event.date,
                guests=guests_response,
            )
        )
    
    return GuestDetailResponse(
        full_name=invitee.full_name,
        mailing_address=mailing_address_response,
        events=events_with_guests,
    )

