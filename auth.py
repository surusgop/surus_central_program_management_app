import os
import secrets as _secrets
from urllib.parse import urlencode

import requests as _requests
from flask import make_response, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_WORKSPACE_DOMAIN = os.environ.get("GOOGLE_WORKSPACE_DOMAIN")
APP_URL = os.environ.get("APP_URL", "http://localhost:8050").rstrip("/")
SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET environment variable is not set. "
        "Set it to a long random string in your .env file. "
        "See .env.example for details."
    )
REDIRECT_URI = f"{APP_URL}/auth/callback"
SESSION_MAX_AGE = 8 * 3600  # 8 hours
_OAUTH_STATE_MAX_AGE = 600  # 10 minutes

google_auth_enabled = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

_serializer = URLSafeTimedSerializer(SESSION_SECRET)
# Separate salt so a session cookie can't be replayed as an oauth state or vice versa
_state_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="oauth-state")


def get_current_user() -> str | None:
    """Return the authenticated user's email, or None if not logged in."""
    cookie = request.cookies.get("surus_session")
    if not cookie:
        return None
    try:
        data = _serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        return data.get("email")
    except (BadSignature, SignatureExpired):
        return None


def register_auth(server) -> None:
    """Register Google OAuth routes and auth guard on the Flask server."""
    print(f"[auth] Google auth {'enabled' if google_auth_enabled else 'DISABLED (env vars missing)'}")
    if GOOGLE_WORKSPACE_DOMAIN:
        print(f"[auth] Restricting login to @{GOOGLE_WORKSPACE_DOMAIN}")

    _secure = APP_URL.startswith("https://")

    @server.route("/auth/login")
    def auth_login():
        if not google_auth_enabled:
            return "Google auth not configured.", 503
        state = _secrets.token_hex(16)
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
        }
        if GOOGLE_WORKSPACE_DOMAIN:
            params["hd"] = GOOGLE_WORKSPACE_DOMAIN
        resp = make_response(redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)))
        resp.set_cookie(
            "surus_oauth_state",
            _state_serializer.dumps(state),
            httponly=True,
            secure=_secure,
            samesite="lax",
            max_age=_OAUTH_STATE_MAX_AGE,
        )
        return resp

    @server.route("/auth/callback")
    def auth_callback():
        error = request.args.get("error")
        code = request.args.get("code")
        state_param = request.args.get("state")
        if error:
            return f"Authentication error: {error}", 400

        state_cookie = request.cookies.get("surus_oauth_state")
        if not state_cookie or not state_param:
            return "Invalid or expired login request. Please try again.", 400
        try:
            expected_state = _state_serializer.loads(state_cookie, max_age=_OAUTH_STATE_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return "Invalid or expired login request. Please try again.", 400
        if state_param != expected_state:
            return "Invalid or expired login request. Please try again.", 400

        token_resp = _requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if not token_resp.ok:
            print(f"[auth] Token exchange failed: {token_resp.text}")
            return "Login failed. Please try again.", 400

        access_token = token_resp.json().get("access_token")
        userinfo_resp = _requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not userinfo_resp.ok:
            return "Failed to fetch user info.", 400

        email = userinfo_resp.json().get("email", "")
        if GOOGLE_WORKSPACE_DOMAIN and not email.endswith(f"@{GOOGLE_WORKSPACE_DOMAIN}"):
            return f"Access denied: only @{GOOGLE_WORKSPACE_DOMAIN} accounts are allowed.", 403

        print(f"[auth] Login successful: {email}")
        resp = make_response(redirect("/", 302))
        resp.set_cookie(
            "surus_session",
            _serializer.dumps({"email": email}),
            httponly=True,
            secure=_secure,
            samesite="lax",
            max_age=SESSION_MAX_AGE,
        )
        resp.delete_cookie("surus_oauth_state")
        return resp

    @server.route("/auth/logout")
    def auth_logout():
        resp = make_response(redirect("/auth/login", 302))
        resp.delete_cookie("surus_session")
        return resp

    @server.before_request
    def check_auth():
        if not google_auth_enabled:
            return
        if request.path.startswith("/auth/"):
            return

        session_cookie = request.cookies.get("surus_session")
        if not session_cookie:
            return redirect("/auth/login", 302)

        try:
            _serializer.loads(session_cookie, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            resp = make_response(redirect("/auth/login", 302))
            resp.delete_cookie("surus_session")
            return resp
