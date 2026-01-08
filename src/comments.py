from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from .main import (
    SessionLocal,
    MailingAddressDB,
    WeddingInviteeDB,
    CommentDB,
)
from .utils import verify_password, sanitize_phone_number, sanitize_message_text


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
    # Find mailing address by email
    mailing_address = db.query(MailingAddressDB).filter(
        MailingAddressDB.email == request.email
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


@router.post("/comments", response_model=CommentResponse)
async def post_comment(request: CommentPostRequest, db: Session = Depends(get_db)):
    """
    Post a comment/message with an invitee_id.
    Returns the comment with message text, message id, invitee name and id, and post datetime.
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

