import uuid
import redis
from config import REDIS_URL, fernet, CLIENT_ID, CLIENT_SECRET, TOKEN_URL, ACCESS_TOKEN_LIFESPAN, SESSION_MAX_AGE, SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_COOKIE_SAMESITE
import json
from typing import Optional, Dict, Any
from logger import logger
import time
import httpx
from fastapi import Request, Response, HTTPException

# Хранилище сессий
use_redis = True
redis_client = None

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception as e:
    logger.warning(f"Redis not available, falling back to in-memory store: {e}")
    use_redis = False

_in_memory_sessions: Dict[str, Dict[str, Any]] = {}
_in_memory_tokens: Dict[str, Dict[str, Any]] = {}


def store_session(session_id: str, payload: dict, ttl: Optional[int] = None):
    if use_redis:
        redis_client.set(f"session:{session_id}", json.dumps(payload))
        if ttl:
            redis_client.expire(f"session:{session_id}", ttl)
    else:
        _in_memory_sessions[session_id] = payload


def get_session(session_id: str) -> Optional[dict]:
    if use_redis:
        v = redis_client.get(f"session:{session_id}")
        return json.loads(v) if v else None
    return _in_memory_sessions.get(session_id)


def delete_session(session_id: str):
    if use_redis:
        redis_client.delete(f"session:{session_id}")
    else:
        _in_memory_sessions.pop(session_id, None)


def store_tokens(session_id: str, access_token: dict, refresh_token_enc: str, ttl: Optional[int] = None):
    payload = {
        "access_token": access_token,
        "refresh_token_enc": refresh_token_enc,
        "updated_at": int(time.time()),
    }
    if use_redis:
        redis_client.set(f"tokens:{session_id}", json.dumps(payload))
        if ttl:
            redis_client.expire(f"tokens:{session_id}", ttl)
    else:
        _in_memory_tokens[session_id] = payload


def get_tokens(session_id: str) -> Optional[dict]:
    if use_redis:
        v = redis_client.get(f"tokens:{session_id}")
        return json.loads(v) if v else None
    return _in_memory_tokens.get(session_id)


def delete_tokens(session_id: str):
    if use_redis:
        redis_client.delete(f"tokens:{session_id}")
    else:
        _in_memory_tokens.pop(session_id, None)

async def refresh_access_token(session_id: str) -> bool:
    tokens = get_tokens(session_id)
    if not tokens:
        return False
    refresh_token_enc = tokens.get("refresh_token_enc")
    try:
        refresh_token = fernet.decrypt(refresh_token_enc.encode()).decode()
    except Exception:
        return False

    async with httpx.AsyncClient() as client:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = await client.post(TOKEN_URL, data=data, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            logger.warning(f"Refresh failed for session {session_id}: {resp.text}")
            return False
        new_tokens = resp.json()

    new_access = {
        "token": new_tokens["access_token"],
        "expires_at": int(time.time()) + int(new_tokens.get("expires_in", ACCESS_TOKEN_LIFESPAN)),
    }
    new_refresh_enc = fernet.encrypt(new_tokens["refresh_token"].encode()).decode()
    store_tokens(session_id, new_access, new_refresh_enc, ttl=SESSION_MAX_AGE)
    return True

async def require_session(request: Request, response: Response) -> Dict[str, Any]:
    sess = request.state.session
    if not sess:
        raise HTTPException(401, "Not authenticated")

    session_id = sess["id"]
    tokens = get_tokens(session_id)
    if not tokens:
        raise HTTPException(401, "No tokens stored")

    access = tokens.get("access_token")
    expires_at = access.get("expires_at", 0)
    now = int(time.time())

    rotated = False
    if now >= expires_at - 5:   # скоро истекает – обновляем токен и ротируем сессию
        ok = await refresh_access_token(session_id)
        if not ok:
            delete_tokens(session_id)
            delete_session(session_id)
            raise HTTPException(401, "Session expired and refresh failed")
        tokens = get_tokens(session_id)
        rotated = True

    # Если токен не обновлялся – сессия остаётся прежней, ротация не нужна
    if rotated:
        new_session_id = str(uuid.uuid4())
        meta = get_session(session_id)
        tokens_data = get_tokens(session_id)
        if not meta or not tokens_data:
            raise HTTPException(401, "Session missing during rotation")

        meta["rotated_from"] = session_id
        meta["last_used"] = now
        store_session(new_session_id, meta, ttl=SESSION_MAX_AGE)
        store_tokens(
            new_session_id,
            tokens_data["access_token"],
            tokens_data["refresh_token_enc"],
            ttl=SESSION_MAX_AGE,
        )
        delete_session(session_id)
        delete_tokens(session_id)

        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=new_session_id,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            max_age=SESSION_MAX_AGE,
        )
        session_id = new_session_id
        meta["id"] = new_session_id

    else:
        meta = get_session(session_id)
        if meta:
            meta["last_used"] = now
            store_session(session_id, meta, ttl=SESSION_MAX_AGE)

    return {
        "session_id": session_id,
        "meta": meta,
        "tokens": tokens,
    }

async def get_current_session(request: Request, response: Response) -> Dict[str, Any]:
    """Dependency, возвращает результат require_session для использования в эндпоинтах."""
    return await require_session(request, response)