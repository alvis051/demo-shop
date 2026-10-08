import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


class LoginRequired(Exception):
    def __init__(self, next_url: str):
        self.next_url = next_url


def current_user(request: Request, db: Session = Depends(get_session)) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None:
        request.session.pop("user_id", None)
    return user


def require_user(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        if request.method == "GET":
            next_url = request.url.path
        else:
            next_url = urlsplit(request.headers.get("referer", "/")).path or "/"
        raise LoginRequired(next_url)
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403)
    return user


def safe_next(url: str | None) -> str:
    """Only allow redirects to paths on this site."""
    if not url or not url.startswith("/") or url.startswith("//") or "\\" in url:
        return "/"
    return url
