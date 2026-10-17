import hashlib
import hmac
import os
import re
import uuid

from fastapi import HTTPException


PUBLIC_CHAT_ERROR = "Unable to complete the response. Please try again."


def is_hosted_runtime():
    return (
        "PORT" in os.environ
        or "K_SERVICE" in os.environ
        or "RAILWAY_ENVIRONMENT_ID" in os.environ
        or any(os.getenv(name, "").lower() in {"production", "prod"}
               for name in ("ENVIRONMENT", "APP_ENV"))
    )


def require_admin(configured_key, supplied_key):
    if not configured_key:
        raise HTTPException(status_code=404, detail="Diagnostics are not configured")
    if not supplied_key or not hmac.compare_digest(
        configured_key.encode("utf-8"), supplied_key.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_local_maintenance(configured_key, supplied_key):
    if is_hosted_runtime():
        raise HTTPException(status_code=403, detail="Maintenance is disabled on hosted services")
    require_admin(configured_key, supplied_key)


def resolve_session(session_id):
    if session_id is None or not session_id.strip() or session_id.strip().lower() == "default":
        return uuid.uuid4().hex, False
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", session_id):
        raise HTTPException(status_code=422, detail="Invalid session identifier")
    return session_id, True


def session_log_id(session_id):
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def private_access_required():
    return (
        bool(os.getenv("K_SERVICE") or os.getenv("RAILWAY_ENVIRONMENT_ID"))
        or any(os.getenv(name, "").lower() in {"production", "prod"} for name in ("ENVIRONMENT", "APP_ENV"))
        or os.getenv("PRIVATE_CV_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        or bool(os.getenv("CV_API_PROXY_SECRET"))
    )


def require_private_proxy(request):
    if not private_access_required() or (request.url.path == "/health" and request.method in {"GET", "HEAD"}):
        return
    expected = os.getenv("CV_API_PROXY_SECRET", "")
    supplied = request.headers.getlist("X-CV-Proxy-Key")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", expected) or len(supplied) != 1 or not hmac.compare_digest(
        expected.encode("utf-8"), supplied[0].encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    if request.url.path == "/chat":
        visitors = request.headers.getlist("X-CV-Visitor")
        if len(visitors) != 1 or not re.fullmatch(r"[a-f0-9]{64}", visitors[0]):
            raise HTTPException(status_code=403, detail="Forbidden")
        request.state.private_cv_visitor = visitors[0]


def private_session_id(request, session_id):
    visitor = getattr(request.state, "private_cv_visitor", None)
    if visitor is None:
        return session_id
    return hmac.new(
        os.environ["CV_API_PROXY_SECRET"].encode("utf-8"),
        f"{visitor}:{session_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
