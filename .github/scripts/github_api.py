"""GitHub API client — fetch releases and filter assets."""

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


def _parse_filter(filter_str: str) -> list[list[tuple[str, str]]]:
    """Parse a filter string into a list of AND-groups (OR'd together).

    Comma separates OR groups; ``+`` within a group means AND.
    A token starting with ``.`` is a suffix match, otherwise a
    case-insensitive substring match.
    """
    if not filter_str:
        return []

    or_groups: list[list[tuple[str, str]]] = []
    for part in filter_str.split(","):
        part = part.strip()
        if not part:
            continue
        and_tokens: list[tuple[str, str]] = []
        for token in part.split("+"):
            token = token.strip()
            if not token:
                continue
            if token.startswith("."):
                and_tokens.append(("suffix", token.lower()))
            else:
                and_tokens.append(("substr", token.lower()))
        if and_tokens:
            or_groups.append(and_tokens)
    return or_groups


def _asset_matches(name: str, include_rules: list[list[tuple[str, str]]],
                   exclude_rules: list[list[tuple[str, str]]]) -> bool:
    """Return ``True`` if *name* passes include/exclude rules."""

    def _match_and_group(group: list[tuple[str, str]]) -> bool:
        n = name.lower()
        return all(
            n.endswith(token) if kind == "suffix" else token in n
            for kind, token in group
        )

    # Include: if rules exist, asset must match at least one OR-group.
    if include_rules and not any(_match_and_group(g) for g in include_rules):
        return False

    # Exclude: if any OR-group matches, asset is rejected.
    if exclude_rules and any(_match_and_group(g) for g in exclude_rules):
        return False

    return True


def get_matching_assets(release_data: dict,
                        include_filter: str = "",
                        exclude_filter: str = "") -> list[dict]:
    """Filter release assets by include/exclude rules.

    Parameters
    ----------
    release_data
        The release dict from GitHub API.
    include_filter
        Comma-separated OR groups (``+`` = AND).
        Empty means every asset is eligible.
    exclude_filter
        Same syntax; assets matching any exclude rule are dropped.

    Returns assets whose *size* > 0 and that pass the filters.
    """
    assets = release_data.get("assets", [])
    if not assets:
        return []

    include_rules = _parse_filter(include_filter)
    exclude_rules = _parse_filter(exclude_filter)

    matched = [a for a in assets
               if a["size"] > 0 and _asset_matches(a["name"], include_rules, exclude_rules)]

    # -- logging --
    if include_filter or exclude_filter:
        out = len(matched)
        total = len(assets)
        skipped = total - out
        bits = []
        if include_filter:
            bits.append(f"inc=[{include_filter}]")
        if exclude_filter:
            bits.append(f"exc=[{exclude_filter}]")
        print(f"Asset filter: {' '.join(bits)} -> {out}/{total} matched"
              + (f" (skipped {skipped})" if skipped else ""))
    else:
        print(f"No filter — including all {len(assets)} assets")

    return matched


def stream_asset(asset: dict, token: str = ""):
    """Open an HTTP connection to *asset*'s download URL.

    Returns an ``http.client.HTTPResponse`` (file-like object).
    The caller is responsible for an overall timeout (e.g. via
    ``asyncio.wait_for``).
    """
    url = asset["browser_download_url"]
    req = urllib.request.Request(url, headers=_build_download_headers(token))
    return urllib.request.urlopen(req)  # noqa: S310 — caller wraps in wait_for
