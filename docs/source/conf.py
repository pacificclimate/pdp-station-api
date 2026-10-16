"""Build user documentation without importing the application or its dependencies."""

from pathlib import Path
from datetime import datetime, timezone
import os
import tomllib

project = "Station Data API"
author = "Pacific Climate Impacts Consortium"
copyright = "Pacific Climate Impacts Consortium"
release = tomllib.loads(
    (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
)["tool"]["poetry"]["version"]
version = release
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# A release tag must describe the package actually checked out for this build.
if os.environ.get("GITHUB_REF_TYPE") == "tag":
    if os.environ["GITHUB_REF_NAME"] != release:
        raise ValueError("Release tag must match the version in pyproject.toml")

extensions = []
root_doc = "index"
nitpicky = True
html_theme = "furo"
html_title = f"{project} — v{release}"
html_static_path = ["_static"]
html_css_files = ["pcic.css"]

# PCIC Style Quick Reference: official palette and web application colours.
# Keep Furo's dark neutral surfaces; the guide does not specify a dark palette.
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#003F5E",
        "color-brand-content": "#003F5E",
        "color-brand-visited": "#205768",
        "color-link--hover": "#205768",
        "color-foreground-primary": "#333333",
        "color-foreground-secondary": "#666666",
        "color-foreground-muted": "#666666",
        "color-background-primary": "#FFFFFF",
        "color-background-secondary": "#F5F5F5",
        "color-background-hover": "#E8F4F8",
        "color-background-hover--transparent": "#E8F4F800",
        "color-inline-code-background": "#F0F0F0",
        "color-sidebar-brand-text": "#003F5E",
        "color-sidebar-caption-text": "#2B6733",
        "color-sidebar-item-background--current": "#E8F4F8",
        "color-table-header-background": "#E4EADA",
        "color-highlighted-background": "#BBDC9B",
        "color-highlight-on-target": "#E4EADA",
        "pcic-heading": "#003F5E",
        "pcic-section-heading": "#2B6733",
        "pcic-callout-accent": "#2B6733",
        "pcic-callout-background": "#E4EADA",
        "pcic-note-accent": "#205768",
        "pcic-note-background": "#E8F4F8",
    },
    "dark_css_variables": {
        "color-brand-primary": "#6D9FB9",
        "color-brand-content": "#6D9FB9",
        "color-brand-visited": "#C1CDA4",
        "color-link--hover": "#BBDC9B",
        "color-sidebar-brand-text": "#6D9FB9",
        "color-sidebar-caption-text": "#BBDC9B",
        "color-sidebar-item-background--current": "var(--color-background-hover)",
        "color-table-header-background": "#003F5E",
        "color-highlighted-background": "#205768",
        "color-highlight-on-target": "#003F5E",
        "pcic-heading": "#6D9FB9",
        "pcic-section-heading": "#BBDC9B",
        "pcic-callout-accent": "#BBDC9B",
        "pcic-callout-background": "#2B673333",
        "pcic-note-accent": "#6D9FB9",
        "pcic-note-background": "#003F5E33",
    },
}
