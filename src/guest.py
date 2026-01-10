from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
import logging

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    EventDB,
    EventInviteeAssociation,
    RSVPResponse,
    MailingAddress,
    WeddingInvitee,
    CommentDB,
)
from .utils import sanitize_phone_number, hash_password, verify_password, send_confirmation_email

logger = logging.getLogger(__name__)


# Request/Response Models
class MailingAddressInput(BaseModel):
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    password: str  # Password for RSVP updates (required)


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
    password_hash = hash_password(request.mailing_address.password)
    
    # Sanitize phone number and store it for use in response
    sanitized_phone = sanitize_phone_number(request.mailing_address.phone_number)
    
    # Store email in lowercase
    email_lower = request.mailing_address.email.lower() if request.mailing_address.email else None
    
    mailing_address_db = MailingAddressDB(
        address_line_1=request.mailing_address.address_line_1,
        address_line_2=request.mailing_address.address_line_2,
        city=request.mailing_address.city,
        state=request.mailing_address.state,
        postal_code=request.mailing_address.postal_code,
        email=email_lower,
        phone_number=sanitized_phone,
        password_hash=password_hash,
    )
    db.add(mailing_address_db)
    try:
        db.flush()  # Flush to get the ID without committing
    except IntegrityError as e:
        db.rollback()
        if 'mailing_addresses_email_key' in str(e.orig) or 'unique constraint' in str(e.orig).lower():
            raise HTTPException(
                status_code=400,
                detail=f"A mailing address with email '{request.mailing_address.email}' already exists."
            )
        raise

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
    
    # Get all sub-events of the main event
    sub_events = db.query(EventDB).filter(EventDB.part_of == event_id).all()
    
    # Associate invitees with the main event (rsvp_response = "yes")
    for invitee_db in invitees_db:
        main_association = EventInviteeAssociation(
            event_id=event_id,
            invitee_id=invitee_db.id,
            rsvp_response=RSVPResponse.YES,
        )
        db.add(main_association)
    
    # Associate invitees with all sub-events (rsvp_response = "pending")
    for sub_event in sub_events:
        for invitee_db in invitees_db:
            sub_association = EventInviteeAssociation(
                event_id=sub_event.id,
                invitee_id=invitee_db.id,
                rsvp_response=RSVPResponse.PENDING,
            )
            db.add(sub_association)

    # Commit all changes
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if 'mailing_addresses_email_key' in str(e.orig) or 'unique constraint' in str(e.orig).lower():
            raise HTTPException(
                status_code=400,
                detail=f"A mailing address with email '{request.mailing_address.email}' already exists"
            )
        raise

    # Only send confirmation email if database save was successful (after commit)
    if request.mailing_address.email:
        invitee_names = [invitee_db.full_name for invitee_db in invitees_db]
        send_confirmation_email(
            email=request.mailing_address.email,
            invitee_names=invitee_names,
            phone_number=sanitized_phone
        )

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
    Accepts either an invitee ID or a mailing address ID.
    """
    # First check if guest_id is a mailing address ID
    mailing_address = db.query(MailingAddressDB).filter(MailingAddressDB.id == guest_id).first()
    
    if mailing_address:
        # Use the mailing address and get the first invitee at this address
        invitee = db.query(WeddingInviteeDB).filter(
            WeddingInviteeDB.mailing_address_id == guest_id
        ).first()
        
        if not invitee:
            raise HTTPException(
                status_code=404,
                detail=f"No invitees found for mailing address {guest_id}"
            )
    else:
        # Try to find by invitee ID
        invitee = db.query(WeddingInviteeDB).filter(WeddingInviteeDB.id == guest_id).first()
        
        if not invitee:
            raise HTTPException(
                status_code=404,
                detail=f"Guest with id {guest_id} not found (checked as both invitee ID and mailing address ID)"
            )
        
        # Get mailing address from invitee
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
    
    # Get all events this invitee (or all invitees at this mailing address) is attending (through associations)
    # If guest_id was a mailing address ID, get associations for all invitees at that address
    if mailing_address.id == guest_id:
        # Get all invitee IDs at this mailing address
        invitee_ids = [inv.id for inv in mailing_address.invitees]
        event_associations = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.invitee_id.in_(invitee_ids)
        ).all()
    else:
        # guest_id was an invitee ID, get associations for just that invitee
        event_associations = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.invitee_id == guest_id
        ).all()
    
    # Build events with guests list (deduplicate by event ID)
    events_with_guests = []
    seen_event_ids = set()
    for assoc in event_associations:
        event = assoc.event
        
        # Skip if we've already processed this event
        if event.id in seen_event_ids:
            continue
        seen_event_ids.add(event.id)
        
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

class GuestRSVPInfoRequest(BaseModel):
    email: str
    phone_number: str
    password: str
    event_id: UUID

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
    
    # Find mailing address by email and phone number (case-insensitive email comparison)
    mailing_address = db.query(MailingAddressDB).filter(
        func.lower(MailingAddressDB.email) == request.email.lower(),
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
    
    # Log for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Looking for guests - event_id: {request.event_id}, address_invitee_ids: {address_invitee_ids}")
    logger.info(f"Mailing address ID: {mailing_address.id}, Email: {mailing_address.email}, Phone: {mailing_address.phone_number}")
    
    # Get all associations for these invitees to see what events they're associated with
    all_associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.invitee_id.in_(address_invitee_ids)
    ).all()
    logger.info(f"All associations for these invitees: {[(str(a.event_id), str(a.invitee_id), a.rsvp_response) for a in all_associations]}")
    
    # Also check what invitees are associated with the requested event
    event_associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.event_id == request.event_id
    ).all()
    logger.info(f"All invitees associated with event {request.event_id}: {[str(a.invitee_id) for a in event_associations]}")
    
    # Get associations for this event and address
    associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.event_id == request.event_id,
        EventInviteeAssociation.invitee_id.in_(address_invitee_ids)
    ).all()
    
    logger.info(f"Associations found for event {request.event_id} and address invitees: {len(associations)}")
    
    if not associations:
        # If no associations exist but invitees are at this address, create them
        # This handles the case where associations were missing or cleared
        if address_invitee_ids:
            logger.warning(f"No associations found for event {request.event_id} and address invitees. Creating missing associations.")
            # Get all sub-events of the main event
            sub_events = db.query(EventDB).filter(EventDB.part_of == request.event_id).all()
            
            # Create associations for the main event (rsvp_response = "yes")
            for invitee_id in address_invitee_ids:
                main_association = EventInviteeAssociation(
                    event_id=request.event_id,
                    invitee_id=invitee_id,
                    rsvp_response=RSVPResponse.YES,
                )
                db.add(main_association)
            
            # Create associations for all sub-events (rsvp_response = "pending")
            for sub_event in sub_events:
                for invitee_id in address_invitee_ids:
                    sub_association = EventInviteeAssociation(
                        event_id=sub_event.id,
                        invitee_id=invitee_id,
                        rsvp_response=RSVPResponse.PENDING,
                    )
                    db.add(sub_association)
            
            db.commit()
            
            # Re-query associations after creating them
            associations = db.query(EventInviteeAssociation).filter(
                EventInviteeAssociation.event_id == request.event_id,
                EventInviteeAssociation.invitee_id.in_(address_invitee_ids)
            ).all()
            
            logger.info(f"Created missing associations. Now found {len(associations)} associations.")
        
        if not associations:
            # Still no associations - provide helpful error message
            event_ids_with_guests = list(set([str(a.event_id) for a in all_associations]))
            raise HTTPException(
                status_code=404,
                detail=f"No guests found at this address for event {request.event_id}. Address invitee IDs: {[str(id) for id in address_invitee_ids]}, Event invitee IDs: {[str(a.invitee_id) for a in event_associations]}, Guests are associated with events: {event_ids_with_guests}"
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


@router.delete("/guest/{guest_id}")
async def delete_guest(guest_id: UUID, db: Session = Depends(get_db)):
    """
    Delete a guest. If guest_id is a mailing address ID, delete all invitees at that address
    and all their event associations. If guest_id is an invitee ID, delete just that invitee
    and all its event associations. If no guests remain for the mailing address, delete the mailing address.
    """
    # First check if guest_id is a mailing address ID
    mailing_address = db.query(MailingAddressDB).filter(MailingAddressDB.id == guest_id).first()
    
    if mailing_address:
        # Delete all invitees at this mailing address
        invitees = db.query(WeddingInviteeDB).filter(
            WeddingInviteeDB.mailing_address_id == guest_id
        ).all()
        
        if not invitees:
            raise HTTPException(
                status_code=404,
                detail=f"No invitees found for mailing address {guest_id}"
            )
        
        invitee_ids = [inv.id for inv in invitees]
        
        # Get all comments for these invitees
        comments = db.query(CommentDB).filter(
            CommentDB.invitee_id.in_(invitee_ids)
        ).all()
        
        # Get all associations for these invitees
        associations = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.invitee_id.in_(invitee_ids)
        ).all()
        
        # Get counts before deletion
        comment_count = len(comments)
        association_count = len(associations)
        invitee_count = len(invitees)
        
        # Delete comments first (due to foreign key constraints)
        for comment in comments:
            db.delete(comment)
        
        # Delete associations (due to foreign key constraints)
        for assoc in associations:
            db.delete(assoc)
        
        # Delete invitees
        for invitee in invitees:
            db.delete(invitee)
        
        # Delete mailing address
        db.delete(mailing_address)
        
        db.commit()
        
        return {
            "message": f"Deleted mailing address {guest_id} with {invitee_count} invitee(s), {comment_count} comment(s), and {association_count} association(s)",
            "mailing_address_deleted": True,
            "invitees_deleted": invitee_count,
            "comments_deleted": comment_count,
            "associations_deleted": association_count
        }
    else:
        # Try to find by invitee ID
        invitee = db.query(WeddingInviteeDB).filter(WeddingInviteeDB.id == guest_id).first()
        
        if not invitee:
            raise HTTPException(
                status_code=404,
                detail=f"Guest with id {guest_id} not found (checked as both invitee ID and mailing address ID)"
            )
        
        mailing_address_id = invitee.mailing_address_id
        
        # Get all comments for this invitee
        comments = db.query(CommentDB).filter(
            CommentDB.invitee_id == guest_id
        ).all()
        
        # Get all associations for this invitee
        associations = db.query(EventInviteeAssociation).filter(
            EventInviteeAssociation.invitee_id == guest_id
        ).all()
        
        # Get counts before deletion
        comment_count = len(comments)
        association_count = len(associations)
        
        # Delete comments first (due to foreign key constraints)
        for comment in comments:
            db.delete(comment)
        
        # Delete associations (due to foreign key constraints)
        for assoc in associations:
            db.delete(assoc)
        
        # Delete the invitee
        db.delete(invitee)
        
        # Check if any other invitees remain at this mailing address
        remaining_invitees = db.query(WeddingInviteeDB).filter(
            WeddingInviteeDB.mailing_address_id == mailing_address_id
        ).count()
        
        mailing_address_deleted = False
        if remaining_invitees == 0:
            # No other invitees remain, delete the mailing address
            mailing_address = db.query(MailingAddressDB).filter(
                MailingAddressDB.id == mailing_address_id
            ).first()
            if mailing_address:
                db.delete(mailing_address)
                mailing_address_deleted = True
        
        db.commit()
        
        return {
            "message": f"Deleted invitee {guest_id} with {comment_count} comment(s) and {association_count} association(s)" + 
                      (f" and mailing address {mailing_address_id}" if mailing_address_deleted else ""),
            "invitee_deleted": True,
            "comments_deleted": comment_count,
            "associations_deleted": association_count,
            "mailing_address_deleted": mailing_address_deleted
        }


@router.delete("/guest")
async def delete_guest_by_email(
    email: Optional[str] = Query(None, description="Email address of the mailing address to delete"),
    db: Session = Depends(get_db)
):
    """
    Delete a guest by email address.
    Deletes the mailing address, all invitees at that address, and all their RSVP associations.
    """
    # Check if email is provided
    if not email:
        raise HTTPException(
            status_code=403,
            detail="Email parameter is required"
        )
    
    # Find mailing address by email (case-insensitive comparison)
    mailing_address = db.query(MailingAddressDB).filter(
        func.lower(MailingAddressDB.email) == email.lower()
    ).first()
    
    if not mailing_address:
        raise HTTPException(
            status_code=404,
            detail=f"No mailing address found with email {email}"
        )
    
    # Get all invitees at this mailing address
    invitees = db.query(WeddingInviteeDB).filter(
        WeddingInviteeDB.mailing_address_id == mailing_address.id
    ).all()
    
    if not invitees:
        # No invitees, just delete the mailing address
        db.delete(mailing_address)
        db.commit()
        
        return {
            "message": f"Deleted mailing address with email {email} (no invitees found)",
            "mailing_address_deleted": True,
            "invitees_deleted": 0,
            "associations_deleted": 0
        }
    
    invitee_ids = [inv.id for inv in invitees]
    
    # Get all comments for these invitees
    comments = db.query(CommentDB).filter(
        CommentDB.invitee_id.in_(invitee_ids)
    ).all()
    
    # Get all associations for these invitees
    associations = db.query(EventInviteeAssociation).filter(
        EventInviteeAssociation.invitee_id.in_(invitee_ids)
    ).all()
    
    # Get counts before deletion
    comment_count = len(comments)
    association_count = len(associations)
    invitee_count = len(invitees)
    
    # Delete comments first (due to foreign key constraints)
    for comment in comments:
        db.delete(comment)
    
    # Delete associations (due to foreign key constraints)
    for assoc in associations:
        db.delete(assoc)
    
    # Delete invitees
    for invitee in invitees:
        db.delete(invitee)
    
    # Delete mailing address
    db.delete(mailing_address)
    
    db.commit()
    
    return {
        "message": f"Deleted mailing address with email {email}: {invitee_count} invitee(s), {comment_count} comment(s), and {association_count} association(s)",
        "email": email,
        "mailing_address_deleted": True,
        "invitees_deleted": invitee_count,
        "comments_deleted": comment_count,
        "associations_deleted": association_count
    }


@router.delete("/guest/all")
async def delete_all_guests(db: Session = Depends(get_db)):
    """
    Delete all mailing addresses, invitees, their event associations, and comments.
    This is a destructive operation that removes all guest data.
    """
    # Get counts before deletion
    mailing_address_count = db.query(MailingAddressDB).count()
    invitee_count = db.query(WeddingInviteeDB).count()
    association_count = db.query(EventInviteeAssociation).count()
    comment_count = db.query(CommentDB).count()
    
    # Delete all comments first (due to foreign key constraints)
    db.query(CommentDB).delete()
    
    # Delete all associations (due to foreign key constraints)
    db.query(EventInviteeAssociation).delete()
    
    # Delete all invitees
    db.query(WeddingInviteeDB).delete()
    
    # Delete all mailing addresses
    db.query(MailingAddressDB).delete()
    
    db.commit()
    
    return {
        "message": f"Deleted all guest data: {mailing_address_count} mailing address(es), {invitee_count} invitee(s), {comment_count} comment(s), and {association_count} association(s)",
        "mailing_addresses_deleted": mailing_address_count,
        "invitees_deleted": invitee_count,
        "comments_deleted": comment_count,
        "associations_deleted": association_count
    }

