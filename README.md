# surus_turnout_impact_assessment_app


## Critical Infrastructure Requirements

See `.env.example` for the full variable list.

### Google OAuth (login)

- Login is Google OAuth 2.0 via the shared [surus-auth](https://github.com/surusgop/surus-auth) package (`register_auth(server, dash=True, ...)` in [app.py](app.py)). Every page (including `/`) requires a signed-in account from an allowed domain; `/healthz` stays public for Railway's healthcheck.
- Required env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAIL_DOMAIN`, `APP_URL` (used to build the redirect URI), and `SESSION_SECRET` (app raises at startup if this is unset).
- `ALLOWED_EMAIL_DOMAIN` accepts a comma-separated list of domains (e.g. `surusenterprises.com,example.com`). The older `GOOGLE_WORKSPACE_DOMAIN` is still read when it's unset. `ALLOWED_EMAILS` admits individual outside addresses; `ADMIN_BOOTSTRAP_EMAILS` are the first admins; everyone else's role is set on `/admin`. Leaving both allowlists empty admits any Google account. Run `python -m surus_auth someone@example.com` to check whether an address would get in.
- If `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are not set, auth is disabled entirely.
- surus-auth lives in a private repo, so installing it needs a read-only GitHub token in `GH_PAT` at build time (a Railway variable). Locally, set `GH_PAT` or install the package once with your own git login: `pip install "surus-auth[flask,databricks] @ git+https://github.com/surusgop/surus-auth@v2.2.3"`.
- Setup: in Google Cloud Console → APIs & Services → Credentials, create an OAuth 2.0 Client ID (Web application) and add `https://{your-domain}/auth/callback` as an authorized redirect URI.

### Roles, usage tracking and `/admin`

surus-auth v2 keeps who-can-do-what and who-did-what in the shared `universal.ops` tables, under `app_id = "central_pm"` (see [platform_setup.py](platform_setup.py)). Tracking level: starts at **basic** (sign-ins, page views, admin actions, errors); raise it to **standard** on `/admin` for the events below.

- **Logged:** sign-ins (`login`), each page opened (`page.view`: `home`, `analytics`, `analytics-2`, `contacts`), each filter change on Overview and Analytics 2 (`analytics.filter`, a `query` event with how many values are picked per filter and which control changed, never the names of states, nations, field directors or orgs) and each PDF downloaded (`report.export`, an `export` event; a failed one is logged as an `error`). Kept or dropped by the tracking level set on `/admin` (basic keeps sign-ins and page views only).
- **`/admin`:** admins see people and roles, the activity feed and the tracking level. The navbar shows an **Admin** link to admins. The page comes from surus-auth and is themed to match this app (`ADMIN_THEME` in [platform_setup.py](platform_setup.py)). Turning someone off there blocks their pages and the data callbacks (`app.py` guards Dash's callback endpoint, which surus-auth leaves public in Dash mode).
- **Databricks:** the tables are reached with the same `DATABRICKS_HOST`, `DATABRICKS_SQL_HTTP_PATH` and `DATABRICKS_TOKEN` as the dashboards; the token's owner needs read/write on the `universal.ops` tables.
- **Locally**, leave `PLATFORM_SCHEMA` unset: roles and activity stay in memory.
- **Variables:** see the surus-auth v2 section of [.env.example](.env.example).
