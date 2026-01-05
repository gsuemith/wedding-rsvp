from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from .main import (
    EventDB,
    MailingAddressDB,
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


class EventCreateRequest(BaseModel):
    name: str
    date: datetime
    part_of: Optional[UUID] = None  # UUID of parent event if this is part of a larger event


# Database dependency
def get_db():
    from .main import get_database_engine
    
    # Ensure database is initialized
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


@router.get("/event", response_model=List[Event])
async def get_all_events(
    part_of: Optional[UUID] = Query(None, description="Filter by parent event UUID to get sub-events"),
    db: Session = Depends(get_db)
):
    """
    Get events with their guest lists and invitees.
    - If part_of is not provided: returns all top-level events (events that are not part of another event)
    - If part_of is provided: returns all sub-events of the specified parent event
    """
    if part_of is not None:
        # Verify parent event exists
        parent_event = db.query(EventDB).filter(EventDB.id == part_of).first()
        if not parent_event:
            raise HTTPException(
                status_code=404,
                detail=f"Parent event with id {part_of} not found"
            )
        # Get all events that are part of the specified parent event
        events = db.query(EventDB).filter(EventDB.part_of == part_of).all()
    else:
        # Get only events that are not part of another event (part_of is None)
        events = db.query(EventDB).filter(EventDB.part_of.is_(None)).all()
    
    # Build response for each event
    events_response = []
    for event_db in events:
        # Get invitee IDs
        invitee_ids = [invitee.id for invitee in event_db.invitees]
        
        # Get unique mailing address IDs from invitees (guest_list)
        mailing_address_ids = list(set([
            invitee.mailing_address_id 
            for invitee in event_db.invitees
            if invitee.mailing_address_id is not None
        ]))
        
        events_response.append(
            Event(
                id=event_db.id,
                name=event_db.name,
                guest_list=mailing_address_ids,
                date=event_db.date,
                invitees=invitee_ids,
                part_of=event_db.part_of,
            )
        )
    
    return events_response


@router.post("/event", response_model=Event)
async def create_event(
    request: EventCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new event with name and date.
    Initializes empty lists for guest_list and invitees.
    """
    # Verify parent event exists if part_of is provided
    if request.part_of:
        parent_event = db.query(EventDB).filter(EventDB.id == request.part_of).first()
        if not parent_event:
            raise HTTPException(
                status_code=404,
                detail=f"Parent event with id {request.part_of} not found"
            )
    
    # Create the event
    event_db = EventDB(
        name=request.name,
        date=request.date,
        part_of=request.part_of,
    )
    db.add(event_db)
    db.commit()
    db.refresh(event_db)
    
    # Build response with empty lists for guest_list and invitees
    # guest_list would be computed from invitees' mailing addresses
    # For now, return empty list
    guest_list = []
    
    # Get invitee IDs (will be empty initially)
    invitee_ids = []
    
    return Event(
        id=event_db.id,
        name=event_db.name,
        guest_list=guest_list,
        date=event_db.date,
        invitees=invitee_ids,
        part_of=event_db.part_of,
    )


@router.delete("/event/{event_id}")
async def delete_event(
    event_id: UUID,
    delete_sub_events: bool = Query(False, description="If true, delete sub-events as well (only if no guests exist)"),
    db: Session = Depends(get_db)
):
    """
    Delete an event.
    - By default: Cannot delete if the event has sub-events or guests (invitees).
    - If delete_sub_events=true: Will delete the event and all sub-events, but only if none of them have guests.
    """
    # Find the event
    event = db.query(EventDB).filter(EventDB.id == event_id).first()
    
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
        )
    
    # Get all sub-events
    sub_events = db.query(EventDB).filter(EventDB.part_of == event_id).all()
    
    if delete_sub_events:
        # Check if main event has guests
        if event.invitees:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete event {event_id}: it has {len(event.invitees)} guest(s). Please remove guests first."
            )
        
        # Check if any sub-events have guests
        events_with_guests = []
        for sub_event in sub_events:
            if sub_event.invitees:
                events_with_guests.append(sub_event.name)
        
        if events_with_guests:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete event {event_id} and sub-events: the following sub-events have guests: {', '.join(events_with_guests)}. Please remove guests first."
            )
        
        # Delete all sub-events first
        for sub_event in sub_events:
            db.delete(sub_event)
        
        # Then delete the main event
        db.delete(event)
        db.commit()
        
        return {
            "message": f"Event {event_id} and {len(sub_events)} sub-event(s) deleted successfully"
        }
    else:
        # Original behavior: don't allow deletion if there are sub-events
        if sub_events:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete event {event_id}: it has {len(sub_events)} sub-event(s). Please delete sub-events first or use delete_sub_events=true."
            )
        
        # Check if there are any invitees associated with this event
        if event.invitees:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete event {event_id}: it has {len(event.invitees)} guest(s). Please remove guests first."
            )
        
        # Safe to delete
        db.delete(event)
        db.commit()
        
        return {"message": f"Event {event_id} deleted successfully"}


@router.post("/event/{event_id}/clear-guests")
async def clear_event_guests(
    event_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Remove all guests (invitees) linked to an event.
    This removes the association between the event and invitees, but does not delete the invitees themselves.
    """
    # Find the event
    event = db.query(EventDB).filter(EventDB.id == event_id).first()
    
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
        )
    
    # Get count of invitees before clearing
    invitee_count = len(event.invitees)
    
    # Clear the association (removes entries from junction table)
    event.invitees.clear()
    
    db.commit()
    
    return {
        "message": f"Removed {invitee_count} guest(s) from event {event_id}",
        "event_id": str(event_id),
        "guests_removed": invitee_count
    }


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
