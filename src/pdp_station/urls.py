"""Helpers for links that remain valid behind a stripped proxy prefix."""


def relative_app_root(path: str) -> str:
    """Return a relative reference from *path* to the application root."""
    parts = [part for part in path.split("/") if part]
    parent_depth = len(parts) if path.endswith("/") else max(len(parts) - 1, 0)
    return "../" * parent_depth or "./"
