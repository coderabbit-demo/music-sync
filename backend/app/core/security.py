from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_fernet = Fernet(settings.token_encryption_key.encode()) if settings.token_encryption_key else None
_serializer = URLSafeTimedSerializer(settings.secret_key) if settings.secret_key else None


def encrypt_token(token: str) -> str:
    if _fernet is None:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    if _fernet is None:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Token decryption failed") from exc


def create_oauth_state(data: dict) -> str:
    """Return a signed, URL-safe token embedding `data` for OAuth CSRF protection."""
    if _serializer is None:
        raise RuntimeError("SECRET_KEY is not configured")
    return _serializer.dumps(data)


def verify_oauth_state(state: str, max_age: int = 600) -> dict:
    """Verify and decode an OAuth state token.  Raises ValueError on failure."""
    if _serializer is None:
        raise RuntimeError("SECRET_KEY is not configured")
    try:
        return _serializer.loads(state, max_age=max_age)
    except SignatureExpired as exc:
        raise ValueError("OAuth state token expired") from exc
    except BadSignature as exc:
        raise ValueError("OAuth state token invalid") from exc
