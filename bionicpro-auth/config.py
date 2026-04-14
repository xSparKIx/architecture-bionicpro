import os
from cryptography.fernet import Fernet

# Конфигурация (env)
KEYCLOAK_URL = os.getenv("AUTH_KEYCLOAK_BASE_URL", "https://keycloak.example.com/auth")
KEYCLOAK_CONTAINER_URL = os.getenv("AUTH_KEYCLOAK_CONTAINER_URL", "http://keycloak:8080")
REALM = os.getenv("AUTH_KEYCLOAK_REALM", "myrealm")
CLIENT_ID = os.getenv("AUTH_KEYCLOAK_CLIENT_ID", "bionicpro-auth")
CLIENT_SECRET = os.getenv("AUTH_KEYCLOAK_CLIENT_SECRET", "")
BIONIC_HOST = os.getenv("BIONIC_HOST", "localhost:3010")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

SESSION_COOKIE_NAME = "bionicpro_session"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true" # True в проде
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_MAX_AGE = int(os.getenv("AUTH_SESSION_LIFETIME_SECONDS", 60 * 30))
ACCESS_TOKEN_LIFESPAN = int(os.getenv("AUTH_ACCESS_TOKEN_LIFETIME", 120))

FERNET_KEY = os.getenv("FERNET_KEY") or Fernet.generate_key().decode()
fernet = Fernet(FERNET_KEY.encode())

# Эндпоинты Keycloak
AUTH_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth"
TOKEN_URL = f"{KEYCLOAK_CONTAINER_URL}/realms/{REALM}/protocol/openid-connect/token"