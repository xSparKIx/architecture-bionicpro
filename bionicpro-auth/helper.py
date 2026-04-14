from config import CLIENT_ID, AUTH_URL

def build_auth_redirect(state: str, redirect_uri: str) -> str:
    import urllib.parse
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)