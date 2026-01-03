from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    EventDB,
    WeddingInviteeDB,
    RSVPResponse,
    WeddingInvitee,
)


class Event(BaseModel):
    id: UUID
    name: str
    guest_list: List[UUID]  # List of mailing address UUIDs
    date: datetime
    invitees: List[UUID]  # List of wedding invitee UUIDs
    part_of: Optional[UUID] = None  # UUID of parent event if this is part of a larger event


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter()


@router.get("/event/{event_id}/guests", response_model=List[WeddingInvitee])
async def get_event_guests(
    event_id: UUID,
    response: Optional[RSVPResponse] = Query(None, description="Filter by RSVP response (yes, no, or pending)"),
    db: Session = Depends(get_db)
):
    """
    Get a list of wedding invitees for an event.
    Optionally filter by RSVP response.
    """
    # Find the event
    event = db.query(EventDB).filter(EventDB.id == event_id).first()
    
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
        )
    
    # Get invitees for this event through the relationship
    invitees = event.invitees
    
    # Apply RSVP response filter if provided
    if response is not None:
        invitees = [invitee for invitee in invitees if invitee.rsvp_response == response]
    
    # Build response
    invitees_response = [
        WeddingInvitee(
            full_name=invitee.full_name,
            mailing_address=invitee.mailing_address_id,
            rsvp_response=invitee.rsvp_response,
        )
        for invitee in invitees
    ]
    
    return invitees_response
