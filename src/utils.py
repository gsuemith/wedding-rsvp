import re
import logging
import html
from typing import Optional
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
    - Limits length to prevent abuse
    """
    if not text:
        return ""
    
    # Limit message length (e.g., 500 characters)
    text = text[:500]
    
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

