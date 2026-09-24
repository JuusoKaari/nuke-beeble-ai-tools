# Purpose:
# - Python 3 helper for Nuke to run Beeble SwitchX 2.0 via the Product API.
# - Uploads source video, custom alpha matte, and optional reference image;
#   submits POST /v1/products/switchx/jobs (model switchx-2.0), polls product-jobs,
#   downloads outputs.render, prints logs/JSON.
#
# Auth:
# - BEEBLE_API_KEY (preferred) or --api-key.
# - Optional BEEBLE_TEAM_ID -> X-Beeble-Team-Id header (Product API / org teams).
#
# Payload fields follow Beeble Product API docs for switchx / switchx-2.0
# (live input_schema requires an organization-bound API key).

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from beeble_common import (
    BeebleApiError,
    PRODUCT_SUCCESS_STATUS,
    PRODUCT_TERMINAL_FAILURE_STATUSES,
    compute_retry_sleep_seconds,
    create_product_job,
    download,
    ensure_dir,
    format_beeble_error_summary,
    generate_idempotency_key,
    get_product_job,
    resolve_team_id,
    should_retry_beeble_error,
    upload_local_file,
)

_PRODUCT = "switchx"
_MODEL_ID = "switchx-2.0"
# Product docs: finished custom matte uses inputs.alpha; pair with alpha_mode custom
# (legacy SwitchX used alpha_mode=custom + alpha_uri; Product API renames alpha_uri -> alpha).
_ALPHA_MODE_CUSTOM = "custom"
_USER_AGENT = "nuke-beeble-switchx2-helper"


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def build_switchx2_inputs(
    source_uri: str,
    alpha_uri: str,
    *,
    prompt: str = "",
    reference_image_uri: str | None = None,
    max_resolution: int = 720,
    mode: str = "standard",
    camera_tracking: bool = True,
) -> dict:
    """
    Build inputs for model switchx-2.0 (custom alpha video workflow).

    Field names from Product API docs (not live schema):
      source, alpha, alpha_mode, prompt, reference_image, max_resolution,
      mode, camera_tracking.
    """
    inputs: dict = {
        "source": source_uri,
        "alpha": alpha_uri,
        "alpha_mode": _ALPHA_MODE_CUSTOM,
        "max_resolution": int(max_resolution),
        "mode": str(mode),
        "camera_tracking": bool(camera_tracking),
    }
    prompt_text = (prompt or "").strip()
    if prompt_text:
        inputs["prompt"] = prompt_text
    ref = (reference_image_uri or "").strip()
    if ref:
        inputs["reference_image"] = ref
    return inputs


def build_switchx2_job_payload(
    inputs: dict,
    *,
    idempotency_key: str | None = None,
    model_id: str = _MODEL_ID,
) -> dict:
    key = (idempotency_key or "").strip() or generate_idempotency_key("nuke-switchx2")
    return {
        "model_id": model_id,
        "billing_unit": "credits",
        "idempotency_key": key,
        "inputs": dict(inputs),
    }


def _format_terminal_job_error(status: dict, state: str) -> str:
    err = status.get("error")
    parts = ["SwitchX 2.0 job ended with status=%s" % state]
    if state == "credit_required":
        parts.append(
            "Beeble Cloud credits are required (or the spend cap was hit). "
            "Check organization credits and any max_credits setting."
        )
    elif state == "cancelled":
        parts.append("The product job was cancelled.")
    elif state == "failed":
        parts.append("The product job failed.")
    if err is not None:
        parts.append(format_beeble_error_summary(BeebleApiError("job error", body=err)))
    else:
        try:
            parts.append(json.dumps(status, indent=2))
        except Exception:
            parts.append(str(status))
    return "\n".join(parts)


def _poll_until_done(
    api_key: str,
    job_id: str,
    poll_interval: float,
    verbose: bool,
    team_id: str | None = None,
) -> dict:
    while True:
        status = get_product_job(api_key, job_id, team_id=team_id)
        state = str(status.get("status") or "").strip().lower()
        progress = status.get("progress")
        progress_text = ""
        if progress is not None:
            try:
                progress_text = " progress=%d" % int(progress)
            except Exception:
                progress_text = ""
        print("Polling job %s status=%s%s" % (job_id, state or "unknown", progress_text))

        if state == PRODUCT_SUCCESS_STATUS:
            return status
        if state in PRODUCT_TERMINAL_FAILURE_STATUSES:
            raise BeebleApiError(_format_terminal_job_error(status, state), body=status)

        time.sleep(max(0.5, float(poll_interval)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Beeble SwitchX 2.0 (Product API, custom alpha) and download the result."
    )
    parser.add_argument("--api-key", default=None, help="Beeble API key (otherwise uses BEEBLE_API_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local source video (.mp4/.mov).")
    parser.add_argument("--alpha", required=True, help="Path to local alpha mask video (.mp4/.mov).")
    parser.add_argument("--reference-image", default=None, help="Optional reference still image path.")
    parser.add_argument("--prompt", default="", help="Text prompt describing the desired output.")
    parser.add_argument(
        "--max-resolution",
        type=int,
        default=720,
        choices=[720, 1080],
        help="Output max resolution (Product API examples use 720; 1080 kept for Finish-eligible parents).",
    )
    parser.add_argument(
        "--mode",
        default="standard",
        choices=["standard", "fast"],
        help="Generation mode. Finish later requires a successful standard parent. Default: standard.",
    )
    parser.add_argument(
        "--camera-tracking",
        default="1",
        choices=["0", "1"],
        help="1=generated environment follows source camera motion (SwitchX 2.0). Default: 1.",
    )
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="Optional idempotency key. Auto-generated for each new job when omitted.",
    )
    parser.add_argument(
        "--dry-run-payload",
        action="store_true",
        help="Print the job JSON payload using placeholder URIs and exit (no upload or submit).",
    )
    parser.add_argument("--out", required=True, help="Path to output MP4 file to write.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between status polls. Default: 5.")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient API errors (5xx/429/network). Default: 3.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries. Default: 2.0.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    camera_tracking = str(args.camera_tracking).strip() == "1"
    prompt = (args.prompt or "").strip()
    ref_path = (args.reference_image or "").strip()
    ref_abs = os.path.abspath(ref_path) if ref_path else ""

    if args.dry_run_payload:
        inputs = build_switchx2_inputs(
            "beeble://uploads/dry-run/source.mp4",
            "beeble://uploads/dry-run/alpha.mp4",
            prompt=prompt or "dry-run prompt",
            reference_image_uri=("beeble://uploads/dry-run/reference.png" if ref_abs else None),
            max_resolution=int(args.max_resolution),
            mode=str(args.mode),
            camera_tracking=camera_tracking,
        )
        payload = build_switchx2_job_payload(
            inputs,
            idempotency_key=(args.idempotency_key or "").strip() or "dry-run-key",
        )
        print(json.dumps(payload, indent=2))
        return 0

    api_key = (args.api_key or os.environ.get("BEEBLE_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: missing Beeble API key. Provide --api-key or set BEEBLE_API_KEY env var.", file=sys.stderr)
        return 2

    video_path = os.path.abspath(args.video)
    alpha_path = os.path.abspath(args.alpha)
    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path))

    for label, path in (("source video", video_path), ("alpha mask", alpha_path)):
        if not os.path.isfile(path):
            print("ERROR: %s file not found: %s" % (label, path), file=sys.stderr)
            return 2
        ext = _norm_ext(path)
        if ext not in {"mp4", "mov"}:
            print("ERROR: %s must be .mp4 or .mov. Got: %s" % (label, path), file=sys.stderr)
            return 2

    if ref_abs and not os.path.isfile(ref_abs):
        print("ERROR: reference image not found: %s" % ref_abs, file=sys.stderr)
        return 2
    if ref_abs:
        ref_ext = _norm_ext(ref_abs)
        if ref_ext not in {"png", "jpg", "jpeg", "webp"}:
            print("ERROR: reference image must be png/jpg/jpeg/webp. Got: %s" % ref_abs, file=sys.stderr)
            return 2

    if not prompt and not ref_abs:
        print("ERROR: provide --prompt and/or --reference-image (Beeble requires at least one).", file=sys.stderr)
        return 2

    team_id = resolve_team_id()

    if args.verbose:
        print("Uploading source video: %s" % video_path)
    source_uri = upload_local_file(api_key, video_path, verbose=args.verbose, team_id=team_id)

    if args.verbose:
        print("Uploading alpha mask: %s" % alpha_path)
    alpha_uri = upload_local_file(api_key, alpha_path, verbose=args.verbose, team_id=team_id)

    reference_uri = None
    if ref_abs:
        if args.verbose:
            print("Uploading reference image: %s" % ref_abs)
        reference_uri = upload_local_file(api_key, ref_abs, verbose=args.verbose, team_id=team_id)

    inputs = build_switchx2_inputs(
        source_uri,
        alpha_uri,
        prompt=prompt,
        reference_image_uri=reference_uri,
        max_resolution=int(args.max_resolution),
        mode=str(args.mode),
        camera_tracking=camera_tracking,
    )
    idem_key = (args.idempotency_key or "").strip() or generate_idempotency_key("nuke-switchx2")
    payload = build_switchx2_job_payload(inputs, idempotency_key=idem_key)

    job = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            print("Starting SwitchX 2.0 product job (attempt %d/%d)" % (attempt, max_attempts))
            # Reuse the same body + idempotency_key on retries (Product API safe retry).
            job = create_product_job(api_key, _PRODUCT, payload, team_id=team_id)
            last_exc = None
            break
        except BeebleApiError as e:
            last_exc = e
            if (attempt >= max_attempts) or (not should_retry_beeble_error(e)):
                break
            sleep_s = compute_retry_sleep_seconds(attempt, float(args.retry_base_seconds))
            print(
                "WARNING: Beeble request failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, format_beeble_error_summary(e)),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
        except Exception as e:
            last_exc = e
            break

    if job is None:
        print(
            "ERROR: SwitchX 2.0 start request failed.\n%s"
            % (format_beeble_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    job_id = str(job.get("id") or "").strip()
    if not job_id:
        print("ERROR: SwitchX 2.0 response missing job id:\n%s" % json.dumps(job, indent=2), file=sys.stderr)
        return 4

    try:
        final_status = _poll_until_done(
            api_key,
            job_id,
            float(args.poll_interval),
            args.verbose,
            team_id=team_id,
        )
    except BeebleApiError as e:
        print("ERROR: SwitchX 2.0 job failed.\n%s" % format_beeble_error_summary(e), file=sys.stderr)
        return 5

    outputs = final_status.get("outputs") or {}
    if not isinstance(outputs, dict):
        outputs = {}
    render_url = outputs.get("render")
    if not render_url:
        print(
            "ERROR: successful job missing outputs.render URL:\n%s" % json.dumps(final_status, indent=2),
            file=sys.stderr,
        )
        return 4

    if args.verbose:
        print("Downloading output video -> %s" % out_path)
    print("Downloading output render")
    download(str(render_url), out_path, user_agent=_USER_AGENT)

    print(
        json.dumps(
            {
                "ok": True,
                "job_id": job_id,
                "product": _PRODUCT,
                "model_id": _MODEL_ID,
                "alpha_mode": _ALPHA_MODE_CUSTOM,
                "mode": str(args.mode),
                "camera_tracking": camera_tracking,
                "out_path": out_path,
                "render_url": str(render_url),
                "max_resolution": int(args.max_resolution),
                "idempotency_key": idem_key,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
