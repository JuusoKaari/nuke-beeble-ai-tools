# Purpose:
# - Shared Python 3 utilities for Beeble API helper scripts (stdlib only).
# - HTTP JSON client, presigned uploads, downloads, and retry heuristics.
# - Legacy SwitchX generation helpers plus Product API job helpers.

from __future__ import annotations

import json
import os
import random
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.beeble.ai"
USER_AGENT = "nuke-beeble-switchx-helper"

# Product API terminal statuses (poll until success or one of these).
PRODUCT_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "cancelled", "credit_required"})
PRODUCT_SUCCESS_STATUS = "success"


def configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def safe_print(msg: str, file=None) -> None:
    target = file if file is not None else sys.stdout
    try:
        print(msg, file=target)
    except UnicodeEncodeError:
        enc = getattr(target, "encoding", None) or "utf-8"
        sanitized = str(msg).encode(enc, errors="replace").decode(enc, errors="replace")
        try:
            print(sanitized, file=target)
        except Exception:
            pass


def ensure_dir(path: str) -> None:
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def download(url: str, out_path: str, user_agent: str = USER_AGENT) -> None:
    out_dir = os.path.dirname(os.path.abspath(out_path))
    ensure_dir(out_dir)

    tmp_path = out_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req) as resp:
        with open(tmp_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

    os.replace(tmp_path, out_path)


class BeebleApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _read_response_body(resp) -> Any:
    raw = resp.read()
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return text


def resolve_team_id(team_id: str | None = None) -> str | None:
    """
    Resolve X-Beeble-Team-Id for Product API calls.
    Prefer an explicit value; otherwise use BEEBLE_TEAM_ID when set.
    Returns None when unset so the header is omitted.
    """
    if team_id is not None:
        text = str(team_id).strip()
        return text or None
    text = (os.environ.get("BEEBLE_TEAM_ID") or "").strip()
    return text or None


def api_request(
    method: str,
    path: str,
    api_key: str,
    body: dict | None = None,
    timeout: float = 120.0,
    team_id: str | None = None,
) -> Any:
    url = path if path.startswith("http") else (API_BASE.rstrip("/") + "/" + path.lstrip("/"))
    headers = {
        "User-Agent": USER_AGENT,
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    # Only attach when the caller passes a non-empty team id (Product API helpers
    # should pass resolve_team_id()). Legacy SwitchX callers omit the header.
    if team_id:
        headers["X-Beeble-Team-Id"] = str(team_id).strip()
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _read_response_body(resp)
    except urllib.error.HTTPError as e:
        payload = None
        try:
            payload = _read_response_body(e)
        except Exception:
            payload = None
        raise BeebleApiError(
            "HTTP %s %s failed: %s" % (e.code, method.upper(), _format_error_body(payload)),
            status_code=int(e.code),
            body=payload,
        ) from e
    except urllib.error.URLError as e:
        raise BeebleApiError("Network error: %s" % e) from e


def _format_error_body(body: Any) -> str:
    if body is None:
        return "<empty>"
    if isinstance(body, dict):
        try:
            return json.dumps(body, indent=2)
        except Exception:
            return str(body)
    return str(body)


def should_retry_beeble_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status >= 500 or status == 429):
        return True
    msg = str(exc).lower()
    return (
        (" 500 " in msg)
        or (" 429 " in msg)
        or ("internal server error" in msg)
        or ("rate limit" in msg)
        or ("too many requests" in msg)
        or ("network error" in msg)
    )


def format_beeble_error_summary(exc: BaseException) -> str:
    body = getattr(exc, "body", None)
    if body is not None:
        return _format_error_body(body)
    return str(exc)


def compute_retry_sleep_seconds(attempt: int, retry_base_seconds: float) -> float:
    base = max(0.25, float(retry_base_seconds))
    sleep_s = base * (2 ** max(0, int(attempt) - 1))
    return sleep_s * (0.75 + (0.5 * random.random()))


def create_upload(api_key: str, filename: str, team_id: str | None = None) -> dict:
    result = api_request(
        "POST",
        "/v1/uploads",
        api_key,
        body={"filename": filename},
        team_id=team_id,
    )
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected upload response: %s" % result)
    for key in ("upload_url", "beeble_uri"):
        if not (result.get(key) or "").strip():
            raise BeebleApiError("Upload response missing %s: %s" % (key, result))
    return result


def _guess_content_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _presigned_put_headers(upload_url: str, content_type: str | None = None) -> dict[str, str]:
    """Build PUT headers that match the presigned URL signature."""
    parsed = urllib.parse.urlparse(upload_url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    headers: dict[str, str] = {}

    # AWS SigV4 presigned URLs (X-Amz-SignedHeaders in query string).
    signed_raw = (params.get("X-Amz-SignedHeaders") or params.get("x-amz-signedheaders") or [""])[0]
    signed = {part.strip().lower() for part in signed_raw.split(";") if part.strip()}
    if signed:
        if "content-type" in signed:
            headers["Content-Type"] = content_type or "application/octet-stream"
        if "x-amz-security-token" in signed:
            for key in ("X-Amz-Security-Token", "x-amz-security-token"):
                values = params.get(key)
                if values and values[0]:
                    headers["x-amz-security-token"] = values[0]
                    break
        return headers

    # AWS SigV2 presigned URLs (Signature/Expires + optional query params).
    for key in ("content-type", "Content-Type"):
        values = params.get(key)
        if values and values[0]:
            headers["Content-Type"] = values[0]
            break
    if "Content-Type" not in headers and content_type:
        headers["Content-Type"] = content_type

    for key in ("x-amz-security-token", "X-Amz-Security-Token"):
        values = params.get(key)
        if values and values[0]:
            headers["x-amz-security-token"] = values[0]
            break

    return headers


def upload_file_to_presigned_url(upload_url: str, file_path: str) -> None:
    with open(file_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        upload_url,
        data=data,
        headers=_presigned_put_headers(upload_url, _guess_content_type(os.path.basename(file_path))),
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=600.0) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        payload = None
        try:
            payload = _read_response_body(e)
        except Exception:
            payload = None
        raise BeebleApiError(
            "Presigned upload failed (HTTP %s): %s" % (e.code, _format_error_body(payload)),
            status_code=int(e.code),
            body=payload,
        ) from e


def upload_local_file(
    api_key: str,
    file_path: str,
    verbose: bool = False,
    team_id: str | None = None,
) -> str:
    filename = os.path.basename(file_path)
    if verbose:
        safe_print("Uploading: %s" % file_path)
    info = create_upload(api_key, filename, team_id=team_id)
    upload_file_to_presigned_url(str(info["upload_url"]), file_path)
    beeble_uri = str(info["beeble_uri"])
    if verbose:
        safe_print("Uploaded beeble_uri=%s" % beeble_uri)
    return beeble_uri


def start_switchx_generation(api_key: str, payload: dict) -> dict:
    result = api_request("POST", "/v1/switchx/generations", api_key, body=payload)
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected generation response: %s" % result)
    if not (result.get("id") or "").strip():
        raise BeebleApiError("Generation response missing job id: %s" % result)
    return result


def get_switchx_job_status(api_key: str, job_id: str) -> dict:
    result = api_request("GET", "/v1/switchx/generations/%s" % job_id, api_key)
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected status response: %s" % result)
    return result


def generate_idempotency_key(prefix: str = "nuke-beeble") -> str:
    """Unique idempotency key for each genuinely new Product API job."""
    safe_prefix = (prefix or "nuke-beeble").strip() or "nuke-beeble"
    return "%s-%s" % (safe_prefix, uuid.uuid4().hex)


def create_product_job(
    api_key: str,
    product: str,
    payload: dict,
    team_id: str | None = None,
) -> dict:
    product_id = (product or "").strip()
    if not product_id:
        raise BeebleApiError("product is required")
    result = api_request(
        "POST",
        "/v1/products/%s/jobs" % product_id,
        api_key,
        body=payload,
        team_id=resolve_team_id(team_id),
    )
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected product job response: %s" % result)
    if not (result.get("id") or "").strip():
        raise BeebleApiError("Product job response missing id: %s" % result)
    return result


def get_product_job(api_key: str, job_id: str, team_id: str | None = None) -> dict:
    jid = (job_id or "").strip()
    if not jid:
        raise BeebleApiError("job_id is required")
    result = api_request(
        "GET",
        "/v1/product-jobs/%s" % jid,
        api_key,
        team_id=resolve_team_id(team_id),
    )
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected product job status response: %s" % result)
    return result


def list_product_models(api_key: str, product: str, team_id: str | None = None) -> dict:
    product_id = (product or "").strip()
    if not product_id:
        raise BeebleApiError("product is required")
    result = api_request(
        "GET",
        "/v1/products/%s/models" % product_id,
        api_key,
        team_id=resolve_team_id(team_id),
    )
    if not isinstance(result, dict):
        raise BeebleApiError("Unexpected product models response: %s" % result)
    return result


configure_stdio_utf8()
