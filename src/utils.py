import re
import logging
import html
import os
import requests
import json
from typing import Optional, List
from passlib.context import CryptContext

# Password hashing context
# Using pbkdf2_sha256 instead of bcrypt to avoid 72-byte password limit
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

logger = logging.getLogger(__name__)


def sanitize_phone_number(phone: Optional[str]) -> Optional[str]:
    """Remove all non-digit characters from phone number."""
    if phone is None:
        return None
    # Strip whitespace first
    phone = phone.strip()
    if not phone:
        return None
    # Remove all non-digit characters
    sanitized = re.sub(r'\D', '', phone)
    # Return None if result is empty, otherwise return the sanitized number
    return sanitized if sanitized else None


def hash_password(password: str) -> str:
    """
    Hash a password using pbkdf2_sha256.
    This scheme doesn't have the 72-byte limit that bcrypt has.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    """
    logger.info(f"Verifying password - plain_password: {plain_password}, hashed_password: {hashed_password}")
    result = pwd_context.verify(plain_password, hashed_password)
    logger.info(f"Password verification result: {result}")
    return result


def sanitize_message_text(text: str) -> str:
    """
    Sanitize message text to prevent XSS while allowing emojis and reasonable characters.
    - Escapes HTML/XML special characters
    - Allows emojis and unicode characters
    - Removes script tags and dangerous patterns
    - Limits length to prevent abuse (configurable via MAX_COMMENT_LENGTH env var, default: 1500)
    """
    if not text:
        return ""
    
    # Get comment length limit from environment variable, default to 1500
    max_comment_length = int(os.getenv('MAX_COMMENT_LENGTH', '1500'))
    
    # Limit message length
    text = text[:max_comment_length]
    
    # Remove null bytes and control characters (except newlines, tabs, carriage returns)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # Escape HTML/XML special characters to prevent XSS
    text = html.escape(text)
    
    # Allow newlines and tabs back (they were escaped, but we want them)
    text = text.replace('&#x0A;', '\n').replace('&#x09;', '\t')
    
    # Remove any remaining script-like patterns (case insensitive)
    text = re.sub(r'&lt;script.*?&gt;.*?&lt;/script&gt;', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)  # Remove event handlers like onclick=
    
    return text.strip()


def send_confirmation_email(email: str, invitee_names: List[str], phone_number: Optional[str]) -> bool:
    """
    Send a confirmation email to the guest after RSVP creation.
    Returns True if successful, False otherwise.
    """
    try:
        # Get Mailgun API key from environment
        api_key = os.getenv('MAIL_GUN_API_KEY')
        if not api_key:
            logger.warning("MAIL_GUN_API_KEY not set, skipping email send")
            return False
        
        # Format invitee names
        if len(invitee_names) == 1:
            names_text = invitee_names[0]
        elif len(invitee_names) == 2:
            names_text = f"{invitee_names[0]} and {invitee_names[1]}"
        else:
            # Multiple names: "Name1, Name2, and Name3"
            names_text = ", ".join(invitee_names[:-1]) + f", and {invitee_names[-1]}"
        
        # Format phone number for display
        phone_display = phone_number if phone_number else "Not provided"
        
        # Prepare template variables as JSON
        template_variables = {
            "names_text": names_text,
            "email": email,
            "phone_number": phone_display
        }
        
        # Send email via Mailgun using template
        response = requests.post(
            "https://api.mailgun.net/v3/carlosandelizabeth2026.com/messages",
            auth=("api", api_key),
            data={
                "from": "Honourable.mention96@gmail.com",
                "to": email,
                "subject": "RSVP Confirmation - Carlos & Elizabeth's Wedding",
                "template": "base template",
                "h:X-Mailgun-Variables": json.dumps(template_variables)
            },
            timeout=10  # 10 second timeout
        )
        
        if response.status_code == 200:
            logger.info(f"Confirmation email sent successfully to {email}")
            return True
        else:
            logger.error(f"Failed to send confirmation email to {email}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending confirmation email to {email}: {str(e)}")
        return False

