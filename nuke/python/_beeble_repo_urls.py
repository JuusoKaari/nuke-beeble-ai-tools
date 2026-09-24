# Purpose: Canonical GitHub URLs for nuke-beeble-ai-tools (install hints and docs).
# Named _beeble_repo_urls so it does not collide with nuke-fal-ai-tools _repo_urls
# when both plugins are on sys.path.
# Resolves a download URL by probing releases/latest, then falling back to the repo
# when GitHub has no published release (latest redirects to the empty /releases list).

from __future__ import print_function

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError, URLError  # type: ignore # noqa: F401

GITHUB_REPO_URL = "https://github.com/JuusoKaari/nuke-beeble-ai-tools"
GITHUB_RELEASES_URL = "https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases/latest"
_RELEASES_LIST_URL = "https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases"


def _final_url_looks_like_a_release(final_url):
    """True when GitHub sent us to an actual tag page, not the empty releases list."""
    url = (final_url or "").strip().rstrip("/")
    if not url:
        return False
    # Successful latest -> .../releases/tag/<name>
    if "/releases/tag/" in url:
        return True
    # Empty repo: GitHub redirects /releases/latest -> /releases (no tag).
    if url == _RELEASES_LIST_URL.rstrip("/") or url.endswith("/releases"):
        return False
    return False


def resolve_install_download_url(timeout=5.0):
    """
    Prefer the latest GitHub release when a tag exists; otherwise use the repo page.
    /releases/latest returns 200 even with zero releases (redirects to the list),
    so we inspect the final URL instead of trusting status alone.
    """
    try:
        try:
            req = Request(GITHUB_RELEASES_URL, method="HEAD")
        except TypeError:
            req = Request(GITHUB_RELEASES_URL)
            req.get_method = lambda: "HEAD"  # type: ignore[attr-defined]
        try:
            resp = urlopen(req, timeout=float(timeout))
        except TypeError:
            resp = urlopen(req)
        try:
            code = getattr(resp, "getcode", lambda: None)()
            final = getattr(resp, "geturl", lambda: "")() or ""
            if code is not None and int(code) >= 400:
                return GITHUB_REPO_URL
            if _final_url_looks_like_a_release(final):
                return GITHUB_RELEASES_URL
            return GITHUB_REPO_URL
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except HTTPError as e:
        code = getattr(e, "code", None)
        if code in (404, 410):
            return GITHUB_REPO_URL
        return GITHUB_REPO_URL
    except (URLError, OSError, ValueError):
        return GITHUB_REPO_URL
    except Exception:
        return GITHUB_REPO_URL


def install_download_lines():
    """Two-line install source hint used in Nuke messages."""
    primary = resolve_install_download_url()
    if primary == GITHUB_RELEASES_URL:
        return (
            "  Latest release zip: %s\n"
            "  Or clone: %s"
            % (GITHUB_RELEASES_URL, GITHUB_REPO_URL)
        )
    return (
        "  Repo (clone or download zip): %s\n"
        "  Releases (when published): %s"
        % (GITHUB_REPO_URL, GITHUB_RELEASES_URL)
    )
