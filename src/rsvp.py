from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    EventDB,
    RSVPResponse,
    WeddingInvitee,
)
from .utils import sanitize_phone_number, verify_password


# Request/Response Models
class InviteeRSVPUpdate(BaseModel):
    invitee_id: UUID
    rsvp_response: RSVPResponse


class RSVPRequest(BaseModel):
    mailing_address_id: UUID
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


@router.post("/rsvp", response_model=RSVPUpdateResponse)
async def update_rsvps(request: RSVPRequest, db: Session = Depends(get_db)):
    """
    Update RSVP responses for multiple invitees associated with a mailing address.
    """
    # Verify mailing address exists
    mailing_address = db.query(MailingAddressDB).filter(
        MailingAddressDB.id == request.mailing_address_id
    ).first()
    
    if not mailing_address:
        raise HTTPException(
            status_code=404,
            detail=f"Mailing address with id {request.mailing_address_id} not found"
        )
    
    # Update each invitee's RSVP response
    updated_invitees = []
    for invitee_update in request.invitees:
        # Find the invitee
        invitee = db.query(WeddingInviteeDB).filter(
            WeddingInviteeDB.id == invitee_update.invitee_id
        ).first()
        
        if not invitee:
            raise HTTPException(
                status_code=404,
                detail=f"Invitee with id {invitee_update.invitee_id} not found"
            )
        
        # Verify invitee belongs to the specified mailing address
        if invitee.mailing_address_id != request.mailing_address_id:
            raise HTTPException(
                status_code=400,
                detail=f"Invitee {invitee_update.invitee_id} does not belong to mailing address {request.mailing_address_id}"
            )
        
        # Update the RSVP response
        invitee.rsvp_response = invitee_update.rsvp_response
        updated_invitees.append(invitee)
    
    # Commit all changes
    db.commit()
    
    # Refresh to ensure we have the latest data
    for invitee in updated_invitees:
        db.refresh(invitee)
    
    # Build response
    invitees_response = [
        WeddingInvitee(
            id=invitee.id,
            full_name=invitee.full_name,
            mailing_address=invitee.mailing_address_id,
            rsvp_response=invitee.rsvp_response,
        )
        for invitee in updated_invitees
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
    
    # Get all invitees at this address who are associated with the event
    event_invitee_ids = {invitee.id for invitee in event.invitees}
    address_invitee_ids = {invitee.id for invitee in mailing_address.invitees}
    valid_invitee_ids = event_invitee_ids & address_invitee_ids
    
    # Update each invitee's RSVP response
    updated_invitees = []
    for invitee_update in request.invitees:
        # Verify invitee ID is valid for this event and address
        if invitee_update.invitee_id not in valid_invitee_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Invitee {invitee_update.invitee_id} is not associated with event {event_id} and this mailing address"
            )
        
        # Find the invitee
        invitee = db.query(WeddingInviteeDB).filter(
            WeddingInviteeDB.id == invitee_update.invitee_id
        ).first()
        
        if not invitee:
            raise HTTPException(
                status_code=404,
                detail=f"Invitee with id {invitee_update.invitee_id} not found"
            )
        
        # Verify invitee belongs to the mailing address
        if invitee.mailing_address_id != mailing_address.id:
            raise HTTPException(
                status_code=400,
                detail=f"Invitee {invitee_update.invitee_id} does not belong to this mailing address"
            )
        
        # Update the RSVP response
        invitee.rsvp_response = invitee_update.rsvp_response
        updated_invitees.append(invitee)
    
    # Commit all changes
    db.commit()
    
    # Refresh to ensure we have the latest data
    for invitee in updated_invitees:
        db.refresh(invitee)
    
    # Build response
    invitees_response = [
        WeddingInvitee(
            id=invitee.id,
            full_name=invitee.full_name,
            mailing_address=invitee.mailing_address_id,
            rsvp_response=invitee.rsvp_response,
        )
        for invitee in updated_invitees
    ]
    
    return RSVPUpdateResponse(updated_invitees=invitees_response)

