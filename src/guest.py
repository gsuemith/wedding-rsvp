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
    EventInviteeAssociation,
    RSVPResponse,
    MailingAddress,
    WeddingInvitee,
)
from .utils import sanitize_phone_number, hash_password, verify_password


# Request/Response Models
class MailingAddressInput(BaseModel):
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None  # Password for RSVP updates


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


class GuestRSVPInfoRequest(BaseModel):
    email: str
    phone_number: str
    password: str
    event_id: UUID


class EventRSVPInfo(BaseModel):
    id: UUID
    name: str
    date: datetime
    guests: List[WeddingInvitee]  # All guests with same address attending this event


class GuestRSVPInfoResponse(BaseModel):
    mailing_address: MailingAddress
    event: EventRSVPInfo


# Database dependency
def get_db():
    from .main import get_database_engine, ensure_migrations
    
    # Ensure migrations have run
    ensure_migrations()
    
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


@router.post("/guest/event/{event_id}", response_model=GuestResponse)
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
    password_hash = None
    if request.mailing_address.password:
        password_hash = hash_password(request.mailing_address.password)
    
    # Sanitize phone number and store it for use in response
    sanitized_phone = sanitize_phone_number(request.mailing_address.phone_number)
    
    mailing_address_db = MailingAddressDB(
        address_line_1=request.mailing_address.address_line_1,
        address_line_2=request.mailing_address.address_line_2,
        city=request.mailing_address.city,
        state=request.mailing_address.state,
        postal_code=request.mailing_address.postal_code,
        email=request.mailing_address.email,
        phone_number=sanitized_phone,
        password_hash=password_hash,
    )
    db.add(mailing_address_db)
    db.flush()  # Flush to get the ID without committing

    # Create invitees for each name
    invitees_db = []
    for name in request.names:
        invitee_db = WeddingInviteeDB(
            full_name=name,
            mailing_address_id=mailing_address_db.id,
        )
        db.add(invitee_db)
        invitees_db.append(invitee_db)
    
    # Flush to get invitee IDs before associating with event
    db.flush()
    
    # Associate invitees with the event (create associations with PENDING status)
    for invitee_db in invitees_db:
        association = EventInviteeAssociation(
            event_id=event_id,
            invitee_id=invitee_db.id,
            rsvp_response=RSVPResponse.PENDING,
        )
        db.add(association)

    # Commit all changes
    db.commit()

    # Refresh to ensure we have the latest data
    db.refresh(mailing_address_db)
    for invitee_db in invitees_db:
        db.refresh(invitee_db)

    # Build response - use the sanitized phone number we stored
    # (refresh might not always work correctly, so use the value we know we set)
    mailing_address_response = MailingAddress(
        id=mailing_address_db.id,
        address_line_1=mailing_address_db.address_line_1,
        address_line_2=mailing_address_db.address_line_2,
        city=mailing_address_db.city,
        state=mailing_address_db.state,
        postal_code=mailing_address_db.postal_code,
        email=mailing_address_db.email,
        phone_number=sanitized_phone,  # Use the sanitized value we stored
    )

    # Get associations for this event to get rsvp_response
    associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.event_id == event_id,
        EventInviteeAssociation.invitee_id.in_([inv.id for inv in invitees_db])
    ).all()
    association_map = {assoc.invitee_id: assoc.rsvp_response for assoc in associations}
    
    invitees_response = [
        WeddingInvitee(
            id=invitee_db.id,
            full_name=invitee_db.full_name,
            mailing_address=invitee_db.mailing_address_id,
            rsvp_response=association_map.get(invitee_db.id, RSVPResponse.PENDING),
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
        email=mailing_address.email,
        phone_number=mailing_address.phone_number,
    )
    
    # Get all events this invitee is attending (through associations)
    event_associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.invitee_id == guest_id
    ).all()
    
    # Build events with guests list
    events_with_guests = []
    for assoc in event_associations:
        event = assoc.event
        
        # Find all invitees with the same mailing address who are also in this event
        same_address_associations = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.event_id == event.id
        ).join(WeddingInviteeDB, EventInviteeAssociation.invitee_id == WeddingInviteeDB.id).filter(
            WeddingInviteeDB.mailing_address_id == invitee.mailing_address_id
        ).all()
        
        # Convert to response models
        guests_response = [
            WeddingInvitee(
                id=inv_assoc.invitee.id,
                full_name=inv_assoc.invitee.full_name,
                mailing_address=inv_assoc.invitee.mailing_address_id,
                rsvp_response=inv_assoc.rsvp_response,
            )
            for inv_assoc in same_address_associations
        ]
        
        events_with_guests.append(
            EventWithGuests(
                id=assoc.event.id,
                name=assoc.event.name,
                date=assoc.event.date,
                guests=guests_response,
            )
        )
    
    return GuestDetailResponse(
        full_name=invitee.full_name,
        mailing_address=mailing_address_response,
        events=events_with_guests,
    )


@router.post("/guest/rsvp-info", response_model=GuestRSVPInfoResponse)
async def get_guest_rsvp_info(request: GuestRSVPInfoRequest, db: Session = Depends(get_db)):
    """
    Get RSVP information for guests using email, phone number, password, and event ID.
    Returns mailing address and RSVP information for all guests at that address for the specified event.
    """
    # Verify event exists
    event = db.query(EventDB).filter(EventDB.id == request.event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {request.event_id} not found"
        )
    
    # Sanitize phone number
    sanitized_phone = sanitize_phone_number(request.phone_number)
    
    # Find mailing address by email and phone number
    mailing_address = db.query(MailingAddressDB).filter(
        MailingAddressDB.email == request.email,
        MailingAddressDB.phone_number == sanitized_phone
    ).first()
    
    if not mailing_address:
        raise HTTPException(
            status_code=404,
            detail="No mailing address found with the provided email and phone number"
        )
    
    # Verify password
    if not mailing_address.password_hash:
        raise HTTPException(
            status_code=400,
            detail="No password set for this mailing address. Please contact support."
        )
    
    if not verify_password(request.password, mailing_address.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid password"
        )
    
    # Get all invitees at this address who are associated with the event
    address_invitee_ids = [inv.id for inv in mailing_address.invitees]
    
    # Get associations for this event and address
    associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.event_id == request.event_id,
        EventInviteeAssociation.invitee_id.in_(address_invitee_ids)
    ).all()
    
    if not associations:
        raise HTTPException(
            status_code=404,
            detail=f"No guests found at this address for event {request.event_id}"
        )
    
    # Build mailing address response
    mailing_address_response = MailingAddress(
        id=mailing_address.id,
        address_line_1=mailing_address.address_line_1,
        address_line_2=mailing_address.address_line_2,
        city=mailing_address.city,
        state=mailing_address.state,
        postal_code=mailing_address.postal_code,
        email=mailing_address.email,
        phone_number=mailing_address.phone_number,
    )
    
    # Convert associations to response models
    guests_response = [
        WeddingInvitee(
            id=assoc.invitee.id,
            full_name=assoc.invitee.full_name,
            mailing_address=assoc.invitee.mailing_address_id,
            rsvp_response=assoc.rsvp_response,
        )
        for assoc in associations
    ]
    
    # Build event RSVP info
    event_rsvp_info = EventRSVPInfo(
        id=event.id,
        name=event.name,
        date=event.date,
        guests=guests_response,
    )
    
    return GuestRSVPInfoResponse(
        mailing_address=mailing_address_response,
        event=event_rsvp_info,
    )

