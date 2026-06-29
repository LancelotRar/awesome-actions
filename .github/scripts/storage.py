"""Persistent data file helpers for release monitoring."""


def read_last_updated(path: str) -> str:
    """Read the last persisted *updated_at* from *path*.

    Returns the last non-empty line, or empty string if the file
    does not exist or is empty.
    """
    try:
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()]
            return lines[-1] if lines else ""
    except (FileNotFoundError, IndexError):
        return ""


def write_last_updated(path: str, timestamp: str) -> None:
    """Write *timestamp* (trailing newline) into *path*."""
    with open(path, "w") as f:
        f.write(timestamp + "\n")
