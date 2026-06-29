"""GitHub API client — fetch releases and filter APK assets."""

import json
import time
import urllib.error
import urllib.request

_GITHUB_API = "https://api.github.com"
_MAX_ATTEMPTS = 3


def _build_headers(token: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "GitHub-Actions",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _build_download_headers(token: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "GitHub-Actions",
        "Accept": "application/octet-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(repo: str, token: str = "") -> dict | None:
    """Fetch the latest release from *repo*.

    Returns the release dict, or *None* if the repository has no
    releases yet.
    """
    url = f"{_GITHUB_API}/repos/{repo}/releases?per_page=1"
    req = urllib.request.Request(url, headers=_build_headers(token))

    releases: list[dict] = []
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                releases = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < _MAX_ATTEMPTS:
                sleep = 2**attempt
                print(f"GitHub API HTTP {e.code} (attempt {attempt}/{_MAX_ATTEMPTS}), retry in {sleep}s …")
                time.sleep(sleep)
                continue
            raise RuntimeError(f"GitHub API HTTP {e.code}: {e.reason}") from e
        except OSError as e:
            if attempt < _MAX_ATTEMPTS:
                sleep = 2**attempt
                print(f"Connection error (attempt {attempt}/{_MAX_ATTEMPTS}), retry in {sleep}s …")
                time.sleep(sleep)
                continue
            raise RuntimeError(f"Failed to fetch releases: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to fetch releases: {e}") from e
        else:
            break

    if not releases:
        return None
    return releases[0]


def get_apk_assets(release_data: dict) -> list[dict]:
    """Filter APK assets (non-empty) from *release_data*.

    Only assets whose *name* ends with ``.apk`` and whose *size* is
    greater than zero are returned.
    """
    assets = release_data.get("assets", [])
    apk_assets = [a for a in assets if a["name"].endswith(".apk") and a["size"] > 0]
    if not apk_assets:
        print("No APK assets available")
    elif len(apk_assets) < len(assets):
        print(f"Filtered to {len(apk_assets)} APK files (skipped {len(assets) - len(apk_assets)} non-APK)")
    return apk_assets


def stream_asset(asset: dict, token: str = ""):
    """Open an HTTP connection to *asset*'s download URL.

    Returns an ``http.client.HTTPResponse`` (file-like object).
    The caller is responsible for an overall timeout (e.g. via
    ``asyncio.wait_for``).
    """
    url = asset["browser_download_url"]
    req = urllib.request.Request(url, headers=_build_download_headers(token))
    return urllib.request.urlopen(req)  # noqa: S310 — caller wraps in wait_for
