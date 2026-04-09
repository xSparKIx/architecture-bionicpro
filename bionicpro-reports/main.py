from fastapi import FastAPI, HTTPException, Depends, Header
from clickhouse_driver import Client
from jose import jwt, JWTError
from jose.exceptions import JWKError
import httpx
import logging
from config import (
    CLICKHOUSE_HOST, CLICKHOUSE_PORT,
    CLICKHOUSE_USER, CLICKHOUSE_PASSWORD,
    CLICKHOUSE_DATABASE,
    KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID,
    MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY,
    MINIO_BUCKET, MINIO_SECURE, CDN_BASE_URL
)
from aiobotocore.session import get_session
from contextlib import asynccontextmanager
import json

# Глобальный клиент S3
s3_session = get_session()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reports-api")

app = FastAPI(title="BionicPRO Reports API", version="1.0")

# Кэш для публичного ключа Keycloak (JWKS)
_jwks_cache = None

async def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url)
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch JWKS")
            _jwks_cache = resp.json()
    return _jwks_cache

async def get_current_user(authorization: str = Header(...)):
    """
    Извлекает и верифицирует JWT токен из заголовка Authorization.
    Возвращает user_id (sub) или выбрасывает 401.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ")[1]

    try:
        jwks = await get_jwks()
        # Получаем заголовок токена, чтобы найти нужный ключ
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break
        if not rsa_key:
            raise HTTPException(status_code=401, detail="Unable to find appropriate key")

        payload = jwt.decode(
            token, rsa_key,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            options={"verify_aud": False}  # можно уточнить audience
        )
        # В качестве идентификатора используем sub (или email)
        user_id = payload.get("sub")
        if not user_id:
            user_id = payload.get("email")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject")
        return user_id
    except JWTError as e:
        logger.error(f"JWT validation error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

# Зависимость для получения клиента ClickHouse
def get_clickhouse_client():
    client = Client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DATABASE,
    )
    try:
        yield client
    finally:
        client.disconnect()

@app.get("/reports/{requested_user_id}", summary="Получить отчёт по пользователю")
async def get_report(
    requested_user_id: str,
    current_user_id: str = Depends(get_current_user),
):
    if requested_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Проверяем, есть ли отчёт в S3
    exists = await report_exists(requested_user_id)
    if exists:
        return {"report_url": get_cdn_url(requested_user_id)}

    # Генерируем отчёт из ClickHouse
    ch_client = get_clickhouse_client()
    try:
        # Используем новую витрину для запроса данных
        query = "SELECT * FROM crm_target FINAL WHERE user_id = %(user_id)s AND deleted = 0"
        rows = ch_client.execute(query, {'user_id': requested_user_id})

        if not rows:
            raise HTTPException(status_code=404, detail="User not found")
        columns = [col[0] for col in ch_client.execute('DESCRIBE crm_target')]
        report_data = dict(zip(columns, rows[0]))
    finally:
        ch_client.disconnect()

    # Сохраняем в S3
    await save_report(requested_user_id, report_data)
    return {"report_url": get_cdn_url(requested_user_id)}

@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok"}

@asynccontextmanager
async def get_s3_client():
    async with s3_session.create_client(
        "s3",
        endpoint_url=f"http://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        use_ssl=MINIO_SECURE,
    ) as client:
        yield client

async def ensure_bucket():
    """Создаёт bucket, если его нет"""
    async with get_s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=MINIO_BUCKET)
        except Exception:
            await s3.create_bucket(Bucket=MINIO_BUCKET)

@app.on_event("startup")
async def startup_event():
    await ensure_bucket()

async def report_exists(user_id: str) -> bool:
    """Проверяет, существует ли отчёт в S3"""
    key = f"user_{user_id}.json"
    async with get_s3_client() as s3:
        try:
            await s3.head_object(Bucket=MINIO_BUCKET, Key=key)
            return True
        except Exception:
            return False

async def save_report(user_id: str, data: dict):
    """Сохраняет отчёт в S3"""
    key = f"user_{user_id}.json"
    async with get_s3_client() as s3:
        await s3.put_object(
            Bucket=MINIO_BUCKET,
            Key=key,
            Body=json.dumps(data, indent=2).encode("utf-8"),
            ContentType="application/json"
        )

def get_cdn_url(user_id: str) -> str:
    """Возвращает URL отчёта на CDN"""
    return f"{CDN_BASE_URL}user_{user_id}.json"