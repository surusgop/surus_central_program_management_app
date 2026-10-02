# surus_turnout_impact_assessment_app


## Critical Infrastructure Requirements

See `.env.example` for the full variable list.

### Google OAuth (login)

- Login is Google OAuth 2.0 via the shared [surus-auth](https://github.com/surusgop/surus-auth) package (`register_auth(server, dash=True)` in [app.py](app.py)). Every page (including `/`) requires a signed-in account from an allowed domain; `/healthz` stays public for Railway's healthcheck.
- Required env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAIL_DOMAIN`, `APP_URL` (used to build the redirect URI), and `SESSION_SECRET` (app raises at startup if this is unset).
- `ALLOWED_EMAIL_DOMAIN` accepts a comma-separated list of domains (e.g. `surusenterprises.com,example.com`). The older `GOOGLE_WORKSPACE_DOMAIN` is still read when it's unset. `ALLOWED_EMAILS` admits individual outside addresses; `ADMIN_BOOTSTRAP_EMAILS` grants `role="admin"`. Leaving both allowlists empty admits any Google account. Run `python -m surus_auth someone@example.com` to check whether an address would get in.
- If `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are not set, auth is disabled entirely.
- surus-auth lives in a private repo, so installing it needs a read-only GitHub token in `GH_PAT` at build time (a Railway variable). Locally, set `GH_PAT` or install the package once with your own git login: `pip install "surus-auth[flask] @ git+https://github.com/surusgop/surus-auth@v1.1.1"`.
- Setup: in Google Cloud Console → APIs & Services → Credentials, create an OAuth 2.0 Client ID (Web application) and add `https://{your-domain}/auth/callback` as an authorized redirect URI.
