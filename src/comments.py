from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import desc
import os

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    CommentDB,
    EventDB,
    EventInviteeAssociation,
    RSVPResponse,
)
from .utils import verify_password, sanitize_phone_number, sanitize_message_text, hash_password
from sqlalchemy.exc import IntegrityError


# Request/Response Models
class CommentAuthRequest(BaseModel):
    email: str
    password: str


class InviteeInfo(BaseModel):
    id: UUID
    name: str


class CommentAuthResponse(BaseModel):
    mailing_address_id: UUID
    invitees: List[InviteeInfo]


class CommentPostRequest(BaseModel):
    invitee_id: UUID
    message_text: str


class CommentResponse(BaseModel):
    id: UUID
    message_text: str
    invitee_id: UUID
    invitee_name: str
    created_at: datetime


class CommentsListResponse(BaseModel):
    comments: List[CommentResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class NonAttendeeMailingAddressInput(BaseModel):
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    password: str  # Password for RSVP updates (required)


class NonAttendeeRequest(BaseModel):
    event_id: UUID
    name: str
    mailing_address: NonAttendeeMailingAddressInput


def get_db():
    """
    Database dependency that provides a database session.
    Ensures migrations run on first access.
    """
    from .main import ensure_migrations
    ensure_migrations()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter()


@router.post("/comments/auth", response_model=CommentAuthResponse)
async def authenticate_for_comments(request: CommentAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticate a user with email and password.
    Returns mailing_address_id and list of invitees associated with that address.
    """
    # Find mailing address by email (case-insensitive comparison)
    mailing_address = db.query(MailingAddressDB).filter(
        func.lower(MailingAddressDB.email) == request.email.lower()
    ).first()
    
    if not mailing_address:
        raise HTTPException(
            status_code=404,
            detail="No mailing address found with the provided email"
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
    invitees = db.query(WeddingInviteeDB).filter(
        WeddingInviteeDB.mailing_address_id == mailing_address.id
    ).all()
    
    if not invitees:
        raise HTTPException(
            status_code=404,
            detail="No invitees found for this mailing address"
        )
    
    invitees_info = [
        InviteeInfo(id=invitee.id, name=invitee.full_name)
        for invitee in invitees
    ]
    
    return CommentAuthResponse(
        mailing_address_id=mailing_address.id,
        invitees=invitees_info
    )


@router.post("/comments/non_attendee", response_model=CommentAuthResponse)
async def create_non_attendee(request: NonAttendeeRequest, db: Session = Depends(get_db)):
    """
    Create a mailing address and invitee for a non-attendee with a "no" RSVP response.
    The event must be a main event (not a sub-event).
    Returns the same response as /comments/auth: mailing_address_id and list of invitees.
    """
    # Verify event exists and is a main event (part_of must be None)
    event = db.query(EventDB).filter(EventDB.id == request.event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {request.event_id} not found"
        )
    
    if event.part_of is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Event {request.event_id} is a sub-event. This endpoint only accepts main events."
        )
    
    # Create mailing address
    password_hash = hash_password(request.mailing_address.password)
    
    # Sanitize phone number
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
    
    # Create invitee
    invitee_db = WeddingInviteeDB(
        full_name=request.name,
        mailing_address_id=mailing_address_db.id,
    )
    db.add(invitee_db)
    db.flush()  # Flush to get the invitee ID
    
    # Create association with "no" RSVP response for the main event
    association = EventInviteeAssociation(
        event_id=request.event_id,
        invitee_id=invitee_db.id,
        rsvp_response=RSVPResponse.NO,
    )
    db.add(association)
    
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
    
    # Refresh to ensure we have the latest data
    db.refresh(mailing_address_db)
    db.refresh(invitee_db)
    
    # Return the same format as /comments/auth
    invitees_info = [
        InviteeInfo(id=invitee_db.id, name=invitee_db.full_name)
    ]
    
    return CommentAuthResponse(
        mailing_address_id=mailing_address_db.id,
        invitees=invitees_info
    )


@router.post("/comments", response_model=CommentResponse)
async def post_comment(request: CommentPostRequest, db: Session = Depends(get_db)):
    """
    Post a comment/message with an invitee_id.
    Returns the comment with message text, message id, invitee name and id, and post datetime.
    Each invitee is limited to MAX_COMMENTS_PER_INVITEE comments (default: 5, configurable via environment variable).
    """
    # Verify invitee exists
    invitee = db.query(WeddingInviteeDB).filter(
        WeddingInviteeDB.id == request.invitee_id
    ).first()
    
    if not invitee:
        raise HTTPException(
            status_code=404,
            detail=f"Invitee with id {request.invitee_id} not found"
        )
    
    # Get comment limit from environment variable, default to 5
    max_comments_per_invitee = int(os.getenv('MAX_COMMENTS_PER_INVITEE', '5'))
    
    # Check how many comments this invitee has already posted
    existing_comments_count = db.query(CommentDB).filter(
        CommentDB.invitee_id == request.invitee_id
    ).count()
    
    if existing_comments_count >= max_comments_per_invitee:
        raise HTTPException(
            status_code=400,
            detail=f"Invitee has reached the maximum limit of {max_comments_per_invitee} comments. Current count: {existing_comments_count}"
        )
    
    # Sanitize message text
    sanitized_message = sanitize_message_text(request.message_text)
    
    if not sanitized_message:
        raise HTTPException(
            status_code=400,
            detail="Message text cannot be empty after sanitization"
        )
    
    # Create comment
    comment = CommentDB(
        invitee_id=request.invitee_id,
        message_text=sanitized_message,
        created_at=datetime.utcnow()
    )
    
    db.add(comment)
    db.commit()
    db.refresh(comment)
    
    return CommentResponse(
        id=comment.id,
        message_text=comment.message_text,
        invitee_id=comment.invitee_id,
        invitee_name=invitee.full_name,
        created_at=comment.created_at
    )


@router.get("/comments", response_model=CommentsListResponse)
async def get_comments(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of comments per page (default: 10, max: 100)"),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of comments.
    Returns comments ordered by creation date (newest first).
    """
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get total count
    total = db.query(CommentDB).count()
    
    # Get paginated comments ordered by created_at descending (newest first)
    comments = db.query(CommentDB).join(WeddingInviteeDB).order_by(
        desc(CommentDB.created_at)
    ).offset(offset).limit(page_size).all()
    
    # Build response
    comments_response = [
        CommentResponse(
            id=comment.id,
            message_text=comment.message_text,
            invitee_id=comment.invitee_id,
            invitee_name=comment.invitee.full_name,
            created_at=comment.created_at
        )
        for comment in comments
    ]
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    
    return CommentsListResponse(
        comments=comments_response,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages
    )


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: UUID, db: Session = Depends(get_db)):
    """
    Delete a single comment by comment_id.
    """
    comment = db.query(CommentDB).filter(CommentDB.id == comment_id).first()
    
    if not comment:
        raise HTTPException(
            status_code=404,
            detail=f"Comment with id {comment_id} not found"
        )
    
    db.delete(comment)
    db.commit()
    
    return {
        "message": f"Comment {comment_id} deleted successfully",
        "comment_id": str(comment_id)
    }


@router.delete("/comments/invitee/{invitee_id}")
async def delete_comments_by_invitee(invitee_id: UUID, db: Session = Depends(get_db)):
    """
    Delete all comments posted by a specific invitee.
    """
    # Verify invitee exists
    invitee = db.query(WeddingInviteeDB).filter(
        WeddingInviteeDB.id == invitee_id
    ).first()
    
    if not invitee:
        raise HTTPException(
            status_code=404,
            detail=f"Invitee with id {invitee_id} not found"
        )
    
    # Get all comments for this invitee
    comments = db.query(CommentDB).filter(
        CommentDB.invitee_id == invitee_id
    ).all()
    
    comment_count = len(comments)
    
    # Delete all comments
    for comment in comments:
        db.delete(comment)
    
    db.commit()
    
    return {
        "message": f"Deleted {comment_count} comment(s) for invitee {invitee_id}",
        "invitee_id": str(invitee_id),
        "invitee_name": invitee.full_name,
        "comments_deleted": comment_count
    }


@router.delete("/comments/all")
async def delete_all_comments(db: Session = Depends(get_db)):
    """
    Delete all comments from the database.
    This is a destructive operation that removes all comment data.
    """
    # Get count before deletion
    comment_count = db.query(CommentDB).count()
    
    # Delete all comments
    db.query(CommentDB).delete()
    
    db.commit()
    
    return {
        "message": f"Deleted all {comment_count} comment(s) from the database",
        "comments_deleted": comment_count
    }

