"""Request dependencies: the ONLY way routes obtain the current user and enforce permissions."""
from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import NotAuthenticated, PermissionDenied
from app.core.permissions import Permission, has_permission
from app.core.security import password_version, verify_token
from app.db.session import get_db
from app.models import User


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NotAuthenticated("Sign in to continue.")
    user_id, pv = verify_token(authorization.split(" ", 1)[1].strip())
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise NotAuthenticated("Your account is not active. Sign in again.")
    if pv != password_version(user.password_hash):  # the password was changed or reset after this token was issued
        raise NotAuthenticated("Your password was changed. Sign in again.", code="SESSION_EXPIRED")
    return user


def current_user(user: User = Depends(get_current_user)) -> User:
    """The signed-in user for every working route. An account still on the temporary password the
    administrator set can only read its own session and change that password."""
    if user.must_change_password:
        raise PermissionDenied("Change your temporary password to continue.", code="PASSWORD_CHANGE_REQUIRED")
    return user


def require(*permissions: Permission, any_of: bool = False) -> Callable[..., User]:
    """`Depends(require(Permission.PLANS_IMPORT))` - role is read from the database, never from the client."""

    def dependency(user: User = Depends(current_user)) -> User:
        checks = [has_permission(user.role_code, p) for p in permissions]
        if not (any(checks) if any_of else all(checks)):
            raise PermissionDenied("You do not have access to this action.")
        return user

    return dependency
