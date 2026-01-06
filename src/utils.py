import re
from typing import Optional
from passlib.context import CryptContext

# Password hashing context
# Using pbkdf2_sha256 instead of bcrypt to avoid 72-byte password limit
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


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
    return pwd_context.verify(plain_password, hashed_password)

