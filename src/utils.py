import re
from typing import Optional
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def sanitize_phone_number(phone: Optional[str]) -> Optional[str]:
    """Remove all non-digit characters from phone number."""
    if phone is None:
        return None
    return re.sub(r'\D', '', phone)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

