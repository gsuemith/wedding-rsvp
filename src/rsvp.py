from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    EventDB,
    EventInviteeAssociation,
    RSVPResponse,
    WeddingInvitee,
    MailingAddress,
)
from .utils import sanitize_phone_number, verify_password


# Request/Response Models
class InviteeRSVPUpdate(BaseModel):
    invitee_id: UUID
    rsvp_response: RSVPResponse
    name: Optional[str] = None  # Optional name update for the invitee


class MailingAddressUpdate(BaseModel):
    """Model for updating mailing address fields. All fields are optional."""
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None


class RSVPRequest(BaseModel):
    mailing_address_id: UUID
    mailing_address: Optional[MailingAddressUpdate] = None
    event_id: UUID
    invitees: List[InviteeRSVPUpdate]


class RSVPUpdateResponse(BaseModel):
    updated_invitees: List[WeddingInvitee]


class GuestRSVPUpdateRequest(BaseModel):
    email: str
    phone_number: str
    password: str
    invitees: List[InviteeRSVPUpdate]


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


@router.post("/rsvp", response_model=RSVPUpdateResponse)
async def update_rsvps(request: RSVPRequest, db: Session = Depends(get_db)):
    """
    Update RSVP responses for multiple invitees associated with a mailing address and event.
    """
    # Verify event exists
    event = db.query(EventDB).filter(EventDB.id == request.event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {request.event_id} not found"
        )
    
    # Verify mailing address exists
    mailing_address = db.query(MailingAddressDB).filter(
        MailingAddressDB.id == request.mailing_address_id
    ).first()
    
    if not mailing_address:
        raise HTTPException(
            status_code=404,
            detail=f"Mailing address with id {request.mailing_address_id} not found"
        )
    
    # Update mailing address if provided (only update fields that are not None)
    if request.mailing_address is not None:
        mailing_address.address_line_1 = request.mailing_address.address_line_1 or mailing_address.address_line_1
        mailing_address.address_line_2 = request.mailing_address.address_line_2 or mailing_address.address_line_2
        mailing_address.city = request.mailing_address.city or mailing_address.city
        mailing_address.state = request.mailing_address.state or mailing_address.state
        mailing_address.postal_code = request.mailing_address.postal_code or mailing_address.postal_code
        mailing_address.email = request.mailing_address.email or mailing_address.email
        # Sanitize phone number if provided, otherwise keep existing value
        if request.mailing_address.phone_number is not None:
            mailing_address.phone_number = sanitize_phone_number(request.mailing_address.phone_number)
        # Note: password_hash is NOT updated via this endpoint
    
    # Update each invitee's RSVP response for this event
    updated_associations = []
    for invitee_update in request.invitees:
        # Find the association
        association = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.event_id == request.event_id,
            EventInviteeAssociation.invitee_id == invitee_update.invitee_id
        ).first()
        
        if not association:
            raise HTTPException(
                status_code=404,
                detail=f"Invitee {invitee_update.invitee_id} is not associated with event {request.event_id}"
            )
        
        # Verify invitee belongs to the specified mailing address
        if association.invitee.mailing_address_id != request.mailing_address_id:
            raise HTTPException(
                status_code=400,
                detail=f"Invitee {invitee_update.invitee_id} does not belong to mailing address {request.mailing_address_id}"
            )
        
        # Update the RSVP response in the association
        association.rsvp_response = invitee_update.rsvp_response
        
        # Update the invitee's name if provided
        if invitee_update.name is not None:
            association.invitee.full_name = invitee_update.name
        
        updated_associations.append(association)
    
    # Commit all changes
    db.commit()
    
    # Refresh to ensure we have the latest data
    for association in updated_associations:
        db.refresh(association)
        db.refresh(association.invitee)
    
    # Build response
    invitees_response = [
        WeddingInvitee(
            id=assoc.invitee.id,
            full_name=assoc.invitee.full_name,
            mailing_address=assoc.invitee.mailing_address_id,
            rsvp_response=assoc.rsvp_response,
        )
        for assoc in updated_associations
    ]
    
    return RSVPUpdateResponse(updated_invitees=invitees_response)


@router.post("/rsvp/event/{event_id}", response_model=RSVPUpdateResponse)
async def update_rsvp_by_guest_info(
    event_id: UUID,
    request: GuestRSVPUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update RSVP responses for invitees using event ID, email, phone number, and password.
    Guests can update their RSVP by providing their email, phone number, and the password
    they set when creating their RSVP.
    """
    # Verify event exists
    event = db.query(EventDB).filter(EventDB.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
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
    
    # Get all invitees at this address
    address_invitee_ids = [inv.id for inv in mailing_address.invitees]
    
    # Update each invitee's RSVP response for this event
    updated_associations = []
    for invitee_update in request.invitees:
        # Verify invitee belongs to the mailing address
        if invitee_update.invitee_id not in address_invitee_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Invitee {invitee_update.invitee_id} does not belong to this mailing address"
            )
        
        # Find the association
        association = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.event_id == event_id,
            EventInviteeAssociation.invitee_id == invitee_update.invitee_id
        ).first()
        
        if not association:
            raise HTTPException(
                status_code=404,
                detail=f"Invitee {invitee_update.invitee_id} is not associated with event {event_id}"
            )
        
        # Update the RSVP response in the association
        association.rsvp_response = invitee_update.rsvp_response
        
        # Update the invitee's name if provided
        if invitee_update.name is not None:
            association.invitee.full_name = invitee_update.name
        
        updated_associations.append(association)
    
    # Commit all changes
    db.commit()
    
    # Refresh to ensure we have the latest data
    for association in updated_associations:
        db.refresh(association)
        db.refresh(association.invitee)
    
    # Build response
    invitees_response = [
        WeddingInvitee(
            id=assoc.invitee.id,
            full_name=assoc.invitee.full_name,
            mailing_address=assoc.invitee.mailing_address_id,
            rsvp_response=assoc.rsvp_response,
        )
        for assoc in updated_associations
    ]
    
    return RSVPUpdateResponse(updated_invitees=invitees_response)

