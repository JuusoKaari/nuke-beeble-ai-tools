# Purpose:
# - Python 3 helper for Nuke to run Beeble SwitchX (custom alpha mode) via REST API.
# - Uploads source video, alpha mask video, and optional reference image; polls job status;
#   downloads the composited MP4 and prints logs/JSON.
#
# Auth:
# - Provide `--api-key` or set environment variable `BEEBLE_API_KEY`.

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from beeble_common import (
    BeebleApiError,
    compute_retry_sleep_seconds,
    download,
    ensure_dir,
    format_beeble_error_summary,
    get_switchx_job_status,
    should_retry_beeble_error,
    start_switchx_generation,
    upload_local_file,
)

_ALPHA_MODE = "custom"
_USER_AGENT = "nuke-beeble-switchx-helper"


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def _parse_optional_seed(raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        seed = int(text)
    except Exception:
        print("ERROR: seed must be an integer.", file=sys.stderr)
        raise SystemExit(2)
    if seed < 0 or seed > 4294967295:
        print("ERROR: seed must be between 0 and 4294967295.", file=sys.stderr)
        raise SystemExit(2)
    return seed


def _poll_until_done(api_key: str, job_id: str, poll_interval: float, verbose: bool) -> dict:
    while True:
        status = get_switchx_job_status(api_key, job_id)
        state = str(status.get("status") or "").strip().lower()
        progress = status.get("progress")
        progress_text = ""
        if progress is not None:
            try:
                progress_text = " progress=%d" % int(progress)
            except Exception:
                progress_text = ""
        print("Polling job %s status=%s%s" % (job_id, state or "unknown", progress_text))

        if state == "completed":
            return status
        if state == "failed":
            err = status.get("error") or "SwitchX job failed"
            raise BeebleApiError(str(err), body=status)

        time.sleep(max(0.5, float(poll_interval)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Beeble SwitchX (custom alpha) on a source video and download the result."
    )
    parser.add_argument("--api-key", default=None, help="Beeble API key (otherwise uses BEEBLE_API_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local source video (.mp4/.mov).")
    parser.add_argument("--alpha", required=True, help="Path to local alpha mask video (.mp4/.mov).")
    parser.add_argument("--reference-image", default=None, help="Optional reference still image path.")
    parser.add_argument("--prompt", default="", help="Text prompt describing the desired output.")
    parser.add_argument("--max-resolution", type=int, default=1080, choices=[720, 1080], help="Output max resolution.")
    parser.add_argument("--seed", default="", help="Optional seed (0-4294967295).")
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

    prompt = (args.prompt or "").strip()
    ref_path = (args.reference_image or "").strip()
    ref_abs = os.path.abspath(ref_path) if ref_path else ""
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

    try:
        seed = _parse_optional_seed(args.seed)
    except SystemExit as e:
        return int(e.code)

    if args.verbose:
        print("Uploading source video: %s" % video_path)
    source_uri = upload_local_file(api_key, video_path, verbose=args.verbose)

    if args.verbose:
        print("Uploading alpha mask: %s" % alpha_path)
    alpha_uri = upload_local_file(api_key, alpha_path, verbose=args.verbose)

    reference_uri = None
    if ref_abs:
        if args.verbose:
            print("Uploading reference image: %s" % ref_abs)
        reference_uri = upload_local_file(api_key, ref_abs, verbose=args.verbose)

    payload: dict = {
        "generation_type": "video",
        "source_uri": source_uri,
        "alpha_mode": _ALPHA_MODE,
        "alpha_uri": alpha_uri,
        "max_resolution": int(args.max_resolution),
    }
    if prompt:
        payload["prompt"] = prompt
    if reference_uri:
        payload["reference_image_uri"] = reference_uri
    if seed is not None:
        payload["seed"] = seed

    job = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            print("Starting SwitchX generation (attempt %d/%d)" % (attempt, max_attempts))
            job = start_switchx_generation(api_key, payload)
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
            "ERROR: SwitchX start request failed.\n%s"
            % (format_beeble_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    job_id = str(job.get("id") or "").strip()
    if not job_id:
        print("ERROR: SwitchX response missing job id:\n%s" % json.dumps(job, indent=2), file=sys.stderr)
        return 4

    try:
        final_status = _poll_until_done(api_key, job_id, float(args.poll_interval), args.verbose)
    except BeebleApiError as e:
        print("ERROR: SwitchX job failed.\n%s" % format_beeble_error_summary(e), file=sys.stderr)
        return 5

    output = final_status.get("output") or {}
    if not isinstance(output, dict):
        output = {}
    render_url = output.get("render")
    if not render_url:
        print("ERROR: completed job missing output.render URL:\n%s" % json.dumps(final_status, indent=2), file=sys.stderr)
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
                "alpha_mode": _ALPHA_MODE,
                "out_path": out_path,
                "render_url": str(render_url),
                "seed": final_status.get("seed"),
                "max_resolution": int(args.max_resolution),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
