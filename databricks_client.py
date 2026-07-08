"""
Databricks access template for web apps.

Drop this file into any new Python web app that needs to:
  - Run PySpark queries against a Databricks cluster
  - Call a Databricks-hosted LLM serving endpoint (Claude, etc.)
  - Write audit logs to a Delta table

Required environment variables (.env or host environment):
  DATABRICKS_HOST       Workspace URL, e.g. https://adb-xxx.azuredatabricks.net
  DATABRICKS_CLUSTER_ID Interactive cluster ID for DatabricksSession (Spark)

Auth — one of the following (checked in order):
  DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET   OAuth M2M / service principal
  DATABRICKS_TOKEN                                  Personal access token (PAT)
  (neither)                                         Falls back to WorkspaceClient
                                                    default auth chain (~/.databrickscfg,
                                                    Azure CLI, env vars, etc.)

Optional:
  DATABRICKS_LLM_ENDPOINT   Serving endpoint name for LLM calls
                            (default: databricks-claude-sonnet-4-6)

Usage
-----
  from databricks_client import get_spark, get_llm_client, DATABRICKS_HOST

  spark  = get_spark()           # DatabricksSession (Spark / Delta)
  client = get_llm_client()      # OpenAI-compatible client → serving endpoints
  df     = spark.table("catalog.schema.table")
"""

from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DATABRICKS_HOST: str = os.environ["DATABRICKS_HOST"]
CLUSTER_ID: str = os.environ["DATABRICKS_CLUSTER_ID"]
LLM_ENDPOINT: str = os.environ.get(
    "DATABRICKS_LLM_ENDPOINT", "databricks-claude-sonnet-4-6"
)

# ── Internal auth helpers ─────────────────────────────────────────────────────

def _resolve_token() -> Optional[str]:
    """
    Return a bearer token using the first available auth strategy:
      1. OAuth M2M via DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET
      2. PAT from DATABRICKS_TOKEN
      3. WorkspaceClient default auth chain
    Returns None only if all strategies fail.
    """
    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
    if client_id and client_secret:
        # OAuth M2M: let databricks-sdk fetch and cache a short-lived token
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.config import Config
        cfg = Config(
            host=DATABRICKS_HOST,
            client_id=client_id,
            client_secret=client_secret,
        )
        auth_header = WorkspaceClient(config=cfg).config.authenticate()
        return auth_header["Authorization"].split(" ", 1)[1]

    pat = os.environ.get("DATABRICKS_TOKEN")
    if pat:
        return pat

    try:
        from databricks.sdk import WorkspaceClient
        auth_header = WorkspaceClient().config.authenticate()
        return auth_header["Authorization"].split(" ", 1)[1]
    except Exception as e:
        raise RuntimeError(
            "No Databricks credentials found. Set DATABRICKS_CLIENT_ID+"
            "DATABRICKS_CLIENT_SECRET, or DATABRICKS_TOKEN, or configure "
            "~/.databrickscfg / Azure CLI auth."
        ) from e


# ── Spark (DatabricksSession) ─────────────────────────────────────────────────

_spark_lock = threading.Lock()
_spark = None  # module-level singleton


def _build_spark():
    from databricks.connect import DatabricksSession

    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    if client_id:
        # OAuth M2M path — SDK injects credentials automatically
        return DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()

    token = _resolve_token()
    return DatabricksSession.builder.remote(
        host=DATABRICKS_HOST,
        token=token,
        cluster_id=CLUSTER_ID,
    ).getOrCreate()


def get_spark():
    """
    Return the module-level DatabricksSession, creating it on first call.
    Thread-safe. Use reconnect_spark() to recover from SESSION_CHANGED errors.
    """
    global _spark
    if _spark is None:
        with _spark_lock:
            if _spark is None:
                _spark = _build_spark()
    return _spark


def reconnect_spark():
    """Replace the session after a SESSION_CHANGED / INVALID_HANDLE error."""
    global _spark
    with _spark_lock:
        _spark = _build_spark()
    return _spark


def run_with_reconnect(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs). On SESSION_CHANGED or INVALID_HANDLE, reconnect
    and retry once. Surfaces any other exception normally.

    Example:
        result = run_with_reconnect(lambda: spark.sql("SELECT 1").collect())
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if "SESSION_CHANGED" in str(e) or "INVALID_HANDLE" in str(e):
            reconnect_spark()
            return fn(*args, **kwargs)
        raise


# ── LLM client (serving endpoints) ───────────────────────────────────────────

@lru_cache(maxsize=4)
def get_llm_client(user_token: Optional[str] = None):
    """
    Return an OpenAI-compatible client pointed at Databricks serving endpoints.

    Pass user_token to use a per-request PAT (e.g. forwarded from a UI auth
    flow). Omit to use the server-side resolved token.

    Results are cached by token so repeated calls within a request are free.
    Clear cache with get_llm_client.cache_clear().
    """
    from openai import OpenAI

    token = user_token or _resolve_token()
    return OpenAI(
        api_key=token,
        base_url=f"{DATABRICKS_HOST}/serving-endpoints",
    )


# ── Per-session execution namespace (for code-execution chatbots) ─────────────

def get_exec_namespace(session_state: dict) -> dict:
    """
    Return (or lazily create) a per-user execution namespace that includes
    `spark`, `px` (plotly.express), and `go` (plotly.graph_objects).

    Pass Gradio's `gr.State` dict (or any plain dict) as session_state.
    Namespaces are isolated per user session so variable state doesn't leak.
    """
    if "exec_namespace" not in session_state:
        import plotly.express as px
        import plotly.graph_objects as go
        import plotly.io as pio

        pio.show = lambda *a, **kw: None  # suppress blocking browser opens

        session_state["exec_namespace"] = {
            "spark": get_spark(),
            "px": px,
            "go": go,
        }
    return session_state["exec_namespace"]


def execute_code(code: str, session_state: dict) -> str:
    """
    Execute arbitrary Python in the session's isolated namespace.
    `spark`, `px`, and `go` are pre-injected.

    Returns stdout + the string value of `result` if set, or an ERROR block.
    Auto-reconnects on SESSION_CHANGED / INVALID_HANDLE.
    """
    import sys
    import io
    import traceback

    ns = get_exec_namespace(session_state)

    def _exec():
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            exec(compile(code, "<chatbot>", "exec"), ns)
            printed = buf.getvalue()
            result_val = ns.get("result", "")
            parts = [p for p in [printed, str(result_val) if result_val else ""] if p]
            return "\n".join(parts) or "(no output)"
        finally:
            sys.stdout = old_stdout

    try:
        return _exec()
    except Exception as e:
        if "SESSION_CHANGED" in str(e) or "INVALID_HANDLE" in str(e):
            try:
                reconnect_spark()
                ns["spark"] = get_spark()
                return _exec()
            except Exception:
                return f"ERROR (after reconnect):\n{traceback.format_exc()}"
        return f"ERROR:\n{traceback.format_exc()}"


# ── Startup diagnostics ───────────────────────────────────────────────────────

def print_startup_info():
    """Log credential and config state at app startup."""
    has_pat    = bool(os.environ.get("DATABRICKS_TOKEN"))
    has_oauth  = bool(os.environ.get("DATABRICKS_CLIENT_ID"))
    has_secret = bool(os.environ.get("DATABRICKS_CLIENT_SECRET"))

    auth_mode = (
        "OAuth M2M (client_id + client_secret)" if (has_oauth and has_secret)
        else "OAuth M2M (client_id only — secret missing!)" if has_oauth
        else "PAT (DATABRICKS_TOKEN)" if has_pat
        else "WorkspaceClient default chain"
    )

    print(f"[databricks] host        = {DATABRICKS_HOST}")
    print(f"[databricks] cluster_id  = {CLUSTER_ID}")
    print(f"[databricks] llm endpoint= {LLM_ENDPOINT}")
    print(f"[databricks] auth mode   = {auth_mode}")
