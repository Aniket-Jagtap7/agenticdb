import hashlib
import secrets
from pwdlib import PasswordHash


password_hasher = PasswordHash.recommended()

def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_hasher.verify(
        plain_password,
        password_hash,
    )


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(session_token: str) -> str:
    return hashlib.sha256(
        session_token.encode("utf-8")
    ).hexdigest()