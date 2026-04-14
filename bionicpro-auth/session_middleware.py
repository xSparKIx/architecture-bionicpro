from sessions import get_session, get_tokens, store_session
from config import SESSION_COOKIE_NAME, SESSION_MAX_AGE
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# Сессионная middleware
# Добавляет сессию к ответу
class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        request.state.session = None
        if session_id:
            s = get_session(session_id)
            t = get_tokens(session_id)
            if s and t:
                s["last_used"] = int(time.time())
                store_session(session_id, s, ttl=SESSION_MAX_AGE)
                request.state.session = {"id": session_id, "meta": s, "tokens": t}
        response = await call_next(request)
        return response
