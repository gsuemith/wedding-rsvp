from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    RSVPResponse,
    WeddingInvitee,
)


# Request/Response Models
class InviteeRSVPUpdate(BaseModel):
    invitee_id: UUID
    rsvp_response: RSVPResponse


class RSVPRequest(BaseModel):
    mailing_address_id: UUID
    invitees: List[InviteeRSVPUpdate]


class RSVPUpdateResponse(BaseModel):
    updated_invitees: List[WeddingInvitee]


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
            full_name=invitee.full_name,
            mailing_address=invitee.mailing_address_id,
            rsvp_response=invitee.rsvp_response,
        )
        for invitee in updated_invitees
    ]
    
    return RSVPUpdateResponse(updated_invitees=invitees_response)

