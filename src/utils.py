import re
import hashlib
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
    """
    Hash a password using bcrypt.
    Pre-hashes with SHA-256 to handle passwords longer than 72 bytes (bcrypt limit).
    """
    # Pre-hash with SHA-256 to ensure we never exceed bcrypt's 72-byte limit
    # This produces a fixed 32-byte output regardless of input length
    sha256_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    # Now bcrypt the SHA-256 hash (which is always 64 hex characters = 32 bytes)
    return pwd_context.hash(sha256_hash)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    Pre-hashes with SHA-256 to match the hashing process.
    """
    # Pre-hash with SHA-256 to match the hashing process
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    # Verify the SHA-256 hash against the bcrypt hash
    return pwd_context.verify(sha256_hash, hashed_password)

