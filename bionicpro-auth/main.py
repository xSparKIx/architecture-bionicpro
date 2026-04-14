import uuid
import time
from typing import Dict, Any
from jose import jwt
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
from fastapi.middleware.cors import CORSMiddleware
from config import fernet, TOKEN_URL, CLIENT_ID, CLIENT_SECRET, FRONTEND_URL, BIONIC_HOST, ACCESS_TOKEN_LIFESPAN, SESSION_COOKIE_NAME, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, SESSION_MAX_AGE
from logger import logger
from sessions import store_session, store_tokens, get_tokens, delete_session, delete_tokens, refresh_access_token, get_current_session
from helper import build_auth_redirect
from session_middleware import SessionMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware)

# Роут авторизации
@app.get("/login")
async def login():
    state = str(uuid.uuid4())
    redirect_uri = f"http://{BIONIC_HOST}/callback"
    url = build_auth_redirect(state, redirect_uri)
    return RedirectResponse(url)

# Роут деавторизации
@app.post("/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        delete_tokens(session_id)
        delete_session(session_id)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp

# Роут обработки ответа Keycloak
@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(400, "Missing code")

    redirect_uri = f"http://{BIONIC_HOST}/callback"
    async with httpx.AsyncClient() as client:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = await client.post(TOKEN_URL, data=data, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            logger.error(f"Token exchange failed: {resp.text}")
            raise HTTPException(502, "Token exchange failed")
        token_resp = resp.json()

    session_id = str(uuid.uuid4())
    now = int(time.time())

    # Словарь с access_token и временем истечения
    access_token_dict = {
        "token": token_resp["access_token"],
        "expires_at": now + int(token_resp.get("expires_in", ACCESS_TOKEN_LIFESPAN)),
    }
    refresh_token_enc = fernet.encrypt(token_resp["refresh_token"].encode()).decode()

    # Получаем id пользователя из raw access_token
    raw_access_token = token_resp["access_token"]
    payload = jwt.get_unverified_claims(raw_access_token)
    user_id = payload.get("email") or payload.get("preferred_username") or payload.get("sub")

    session_payload = {
        "session_id": session_id,
        "created_at": now,
        "last_used": now,
        "user_id": user_id,
        "user": None,
    }

    store_session(session_id, session_payload, ttl=SESSION_MAX_AGE)
    store_tokens(session_id, access_token_dict, refresh_token_enc, ttl=SESSION_MAX_AGE)

    response = RedirectResponse(url=f"{FRONTEND_URL}/")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        max_age=SESSION_MAX_AGE,
    )
    return response

# Пример защищенного апи
@app.get("/api/protected")
async def protected(session_data: Dict[str, Any] = Depends(get_current_session)):
    access_token = session_data["tokens"]["access_token"]["token"]
    try:
        payload = jwt.get_unverified_claims(access_token)
    except Exception:
        raise HTTPException(401, "Cannot decode access_token")
    user_id = payload.get("email") or payload.get("preferred_username") or payload.get("sub")
    if not user_id:
        raise HTTPException(500, "Cannot extract user identifier")
    return JSONResponse({"ok": True, "user_id": user_id, "user": payload})

# Роут проверки сессии
@app.get("/session")
async def check_session(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        raise HTTPException(401, "No session")

    tokens = get_tokens(session_id)
    if not tokens:
        raise HTTPException(401, "Session expired")

    access = tokens.get("access_token")

    # Проверка формата
    if isinstance(access, dict) and "expires_at" in access:
        if int(time.time()) >= access["expires_at"]:
            if not await refresh_access_token(session_id):
                raise HTTPException(401, "Session expired")
    else:
        # Неправильный формат – удаляем сессию и просим войти заново
        delete_session(session_id)
        delete_tokens(session_id)
        raise HTTPException(401, "Invalid session format, please login again")

    return {"ok": True, "user": "authenticated"}

# Роут валидации сессии
@app.get("/validate")
async def validate_session(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    request_email = request.headers.get("x-user-email")
    if not session_id:
        raise HTTPException(401, "No session")
    tokens = get_tokens(session_id)
    if not tokens:
        raise HTTPException(401, "Session expired")
    access = tokens["access_token"]["token"]
    try:
        payload = jwt.get_unverified_claims(access)
    except Exception:
        raise HTTPException(403, "Cannot decode access_token")
    user_email = payload.get("email")
    if not user_email or user_email != request_email:
        raise HTTPException(403, "Invalid user")
    response = Response(status_code=200)
    response.headers["X-User-Email"] = user_email
    return response

@app.get("/api/reports")
async def get_report(request: Request, response: Response, session_data: Dict[str, Any] = Depends(get_current_session)):
    """
    Возвращает отчёт по текущему пользователю.
    Запрашивает данные из reports-api, передавая access_token.
    """

    access_token = session_data["tokens"]["access_token"]["token"]
    user_id = session_data["meta"].get("user_id")

    if not user_id:
        payload = jwt.get_unverified_claims(access_token)
        user_id = payload.get("email") or payload.get("preferred_username") or payload.get("sub")

    reports_api_url = f"http://reports-api:8000/reports/{user_id}"
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = await client.get(reports_api_url, headers=headers)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Report not found")
        if resp.status_code != 200:
            logger.error(f"Reports API error: {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch report")
        report_data = resp.json()

    return JSONResponse(report_data)