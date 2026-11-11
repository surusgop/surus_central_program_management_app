"""Roles, usage tracking and the /admin page, from surus-auth v2 (surus_auth.platform).

Kept out of app.py so the Dash layout stays readable. Everything is stored in
the shared universal.ops tables under app_id "central_pm". Variables: see
.env.example.
"""

import os
import re

from surus_auth.flask import get_current_user
from surus_auth.platform import from_env, memory_kit

APP_ID = "central_pm"
TITLE = "Central Program Management"
ENV = os.environ.get("APP_ENV", "dev").strip().lower()
# What gets kept until an admin picks a level on /admin (the app's `apps` row):
# standard = sign-ins, page views, admin actions, errors, plus filters applied
# and PDF reports downloaded.
TRACKING_LEVEL = "standard"

# The admin page is shared by every Surus app; this makes it look like this one
# (assets/styles.css): Surus Illinois red header, navy text, Open Sans, 4px corners.
ADMIN_THEME = {
    "light": {
        "bg": "#F4F6F8",
        "surface": "#FFFFFF",
        "sunk": "#EEF0F3",
        "ink": "#2A313C",
        # The app's slate (#75859E) is too light for the admin page's small
        # text; this is the same hue, darker, so it stays readable.
        "muted": "#5C6A80",
        "line": "#E1E5EA",
        "accent": "#C1272D",
        "accent-soft": "#F8E4E5",
        "on-accent": "#FFFFFF",
        "header-bg": "#C1272D",
        "header-ink": "#FFFFFF",
        "radius": "4px",
        "radius-sm": "4px",
    },
    "dark": False,  # the app has no dark mode
    "font": '"Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    "stylesheets": ["https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700;800&display=swap"],
    "css": "header.top h1 { text-transform: uppercase; letter-spacing: .02em; font-size: 17px; }",
    "back_url": "/",
    "back_label": "Back to Program Management",
}


def make_kit():
    """The shared tables, or an in-memory copy for a local run with no warehouse.

    Production must have PLATFORM_SCHEMA: from_env() refuses to start without
    it, so a missing variable never silently drops admin changes.
    """
    if ENV != "prod" and not os.environ.get("PLATFORM_SCHEMA"):
        admins = [e.strip() for e in os.environ.get("ADMIN_BOOTSTRAP_EMAILS", "").split(",") if e.strip()]
        print(f"[{APP_ID}] PLATFORM_SCHEMA is not set: roles and activity are kept in memory only.")
        return memory_kit(APP_ID, title=TITLE, admins=admins, tracking_level=TRACKING_LEVEL)
    # Non-prod environments create their own tables on first start; prod's
    # already exist in universal.ops (made once by an admin).
    return from_env(APP_ID, title=TITLE, create_tables=ENV != "prod", default_level=TRACKING_LEVEL)


# Built once per process; app.py wires it into sign-in and /admin, pages log through track().
kit = make_kit()

_PAGE = re.compile(r"^[a-z0-9-]{1,60}$")


def page_name(pathname):
    """'/' -> 'home', '/some-page' -> 'some-page'; anything odd -> None (not logged)."""
    name = (pathname or "/").strip("/").lower() or "home"
    return name if _PAGE.match(name) else None


def track(action, *, event_type, page=None, **fields):
    """Log an action by the signed-in user (no-op when signed out).

    Never raises and writes on a background thread, so it can sit in any
    callback. The app's tracking level decides whether the event is kept.
    Put ids, counts and filter names in `metadata`, never personal data.
    """
    try:
        user = get_current_user()
    except Exception:
        return None
    if not user or not user.get("email"):
        return None
    return kit.log.log(user["email"], action, event_type=event_type, page=page,
                       session_id=user.get("session_id"), **fields)


def filter_counts(filters):
    """How many values each filter that is set has, e.g. {"state": 2, "date_range": 1}.
    Never the values themselves."""
    return {name: len(v) if isinstance(v, (list, tuple)) else 1 for name, v in filters.items() if v}


def track_filter(page, filters, *, changed=None, row_count=None):
    """analytics.filter (query) after the user changes a filter: the filters
    that are set (counts only) and the id of the control that changed."""
    metadata = {"filters": filter_counts(filters)}
    if changed:
        metadata["changed"] = str(changed)
    return track("analytics.filter", event_type="query", page=page, metadata=metadata, row_count=row_count)
