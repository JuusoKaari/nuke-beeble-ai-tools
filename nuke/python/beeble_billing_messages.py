# Purpose:
# - Turn Beeble credit and billing API failures into a short Nuke dialog.
# - Safe to import from Nuke (Python 2.7 / 3.x) and from the Python 3 helpers.

from __future__ import print_function

import json


_CREDITS_DIALOG = (
    "Beeble credits are used up, so this job did not run.\n\n"
    "Top up your balance or organization credits, then try again. "
    "If a team budget or max_credits cap is set, raise that too.\n\n"
    "https://developer.beeble.ai"
)

_SPENDING_LIMIT_DIALOG = (
    "Beeble blocked this job because it would pass your spending limit.\n\n"
    "Wait for the next billing period, or raise the limit, then try again."
)

_BILLING_SETUP_DIALOG = (
    "Beeble billing is not set up for this API key, so this job did not run.\n\n"
    "Set up billing at https://developer.beeble.ai and try again."
)

_CREDIT_MARKERS = (
    "insufficient_balance",
    "budget_exceeded",
    "credit_required",
    "insufficient balance",
    "insufficient credit",
    "not enough credit",
    "out of credit",
    "credits are required",
    "credits are used up",
    "credit balance",
    "no remaining credit",
)


def billing_failure_dialog(text):
    """
    Return a Nuke dialog when text is a Beeble credit or billing failure.
    Return None for every other error.
    """
    low = (text or "").lower()
    if ("hard_limit_exceeded" in low) or ("spending limit" in low):
        return _SPENDING_LIMIT_DIALOG
    if ("billing_not_configured" in low) or ("billing is not set up" in low):
        return _BILLING_SETUP_DIALOG
    for marker in _CREDIT_MARKERS:
        if marker in low:
            return _CREDITS_DIALOG
    if ("http 402" in low) or ("status 402" in low):
        return _CREDITS_DIALOG
    return None


def short_api_message(body):
    """Return a short human message from a Beeble error body, or None."""
    message = _message_from_body(body)
    if not message:
        return None
    text = message.strip()
    if not text or text.startswith("{") or text.startswith("["):
        return None
    if len(text) > 300:
        text = text[:300].rstrip() + "..."
    return text


def billing_summary_for_exception(exc):
    """
    Return the dialog, plus Beeble's own sentence when it adds detail.
    Return None when this is not a credit or billing failure.
    """
    chunks = [str(exc or "")]
    status = getattr(exc, "status_code", None)
    if status is not None:
        chunks.append("HTTP %s" % status)
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            chunks.append(json.dumps(body))
        except Exception:
            chunks.append(str(body))
    dialog = billing_failure_dialog("\n".join(chunks))
    if not dialog:
        return None
    detail = short_api_message(body)
    if detail and (detail.lower() not in dialog.lower()):
        return dialog + "\n\nBeeble said: " + detail
    return dialog


def _message_from_body(body):
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return _as_text(err.get("message"))
        if isinstance(err, str):
            return err
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            for key in ("message", "detail", "error_message"):
                text = _as_text(detail.get(key))
                if text:
                    return text
        return None
    if isinstance(body, str):
        return body
    return None


def _as_text(value):
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text or None
