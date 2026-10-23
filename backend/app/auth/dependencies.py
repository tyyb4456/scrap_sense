import logging
from dataclasses import dataclass
from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request_async
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ClerkUser:
    user_id: str
    session_id: str | None
    claims: dict[str, object]


def _authentication_options(settings: Settings) -> AuthenticateRequestOptions | None:
    secret_key = settings.clerk_secret_key.get_secret_value() if settings.clerk_secret_key else None
    jwt_key = settings.clerk_jwt_key.get_secret_value() if settings.clerk_jwt_key else None
    if not secret_key and not jwt_key:
        return None
    return AuthenticateRequestOptions(
        secret_key=secret_key or None,
        jwt_key=jwt_key or None,
        authorized_parties=settings.clerk_authorized_parties,
        accepts_token=["session_token"],
    )


async def require_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClerkUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    options = _authentication_options(settings)
    if options is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    state = await authenticate_request_async(request, options)
    if not state.is_signed_in or not state.payload:
        logger.info("Clerk session verification failed: %s", state.reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = state.payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_id = state.payload.get("sid")
    return ClerkUser(
        user_id=user_id,
        session_id=session_id if isinstance(session_id, str) else None,
        claims=dict(state.payload),
    )


async def require_admin(
    user: Annotated[ClerkUser, Depends(require_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClerkUser:
    if not settings.admin_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Review access is not configured",
        )
    if user.user_id not in settings.admin_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer access required",
        )
    return user
