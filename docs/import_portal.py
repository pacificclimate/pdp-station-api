"""Import the portal user guide from an immutable commit, or a local preview."""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote
from urllib.request import urlopen

import yaml

DOCS = Path(__file__).resolve().parent


def manifest_paths(content):
    """Use PDP's recursive file-list format, without executable YAML tags."""
    manifest = yaml.safe_load(content)
    paths = []

    def component(value):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_. -]*", value
        ):
            raise ValueError(f"Invalid manifest path component: {value!r}")
        return value

    def flatten(items, parent=(), depth=0):
        if depth > 16 or not isinstance(items, list):
            raise ValueError("Manifest must contain nested file lists")
        for item in items:
            if isinstance(item, str):
                path = PurePosixPath(*parent, component(item))
                if path.suffix.lower() not in {
                    ".rst", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".txt"
                }:
                    raise ValueError(f"Unsupported documentation file: {path}")
                paths.append(path.as_posix())
            elif isinstance(item, dict) and len(item) == 1:
                directory, children = next(iter(item.items()))
                flatten(children, (*parent, component(directory)), depth + 1)
            else:
                raise ValueError("Manifest entries must be files or directories")

    flatten(manifest)
    if "root.rst" not in paths or len(set(paths)) != len(paths):
        raise ValueError("Manifest must list root.rst and contain no duplicates")
    return paths


def read_source(read_file):
    """Fetch only manifest-listed documentation, plus version metadata."""
    paths = manifest_paths(read_file("docs/user/manifest.yaml"))
    files = {f"docs/user/{path}": read_file(f"docs/user/{path}") for path in paths}
    files["package.json"] = read_file("package.json")
    return files


def local_files(checkout):
    def read_file(name):
        path = checkout
        for part in PurePosixPath(name).parts:
            path = path / part
            if path.is_symlink():
                raise ValueError(f"Symlinks are not supported: {path}")
        return path.read_bytes()

    return read_source(read_file)


def write_guide(files, destination, repository, revision, preview=False):
    root = files["docs/user/root.rst"].decode("utf-8")
    version = json.loads(files["package.json"])["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise ValueError("Invalid portal version in package.json")
    source_url = f"https://github.com/{repository}/tree/{revision}"
    note = (
        f".. note::\n\n"
        f"   Portal version: **{version}**; "
        f"`source revision {revision[:12]} <{source_url}>`_.\n"
        "   This version identifies the portal UI; the API version is listed\n"
        "   separately in the API guide.\n"
    )
    if preview:
        note += "\n   **Local preview**: includes uncommitted portal files.\n"
    # Validate and assemble everything before replacing the generated directory.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".portal-") as tmp:
        stage = Path(tmp) / "portal"
        stage.mkdir()
        for name, content in files.items():
            relative = PurePosixPath(name)
            if not relative.is_relative_to("docs/user"):
                continue
            target = stage.joinpath(*relative.relative_to("docs/user").parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        # Insert the version note after the document title.
        lines = root.splitlines(keepends=True)
        lines[2:2] = ["\n", note, "\n"]
        (stage / "root.rst").write_text("".join(lines), encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(stage, destination)
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-preview", type=Path, metavar="PORTAL_CHECKOUT",
        help="Include local, possibly uncommitted guide changes instead of the pin",
    )
    args = parser.parse_args()
    pin = json.loads((DOCS / "portal-source.json").read_text())
    repository = pin["repository"]
    revision = pin["revision"]
    if repository != "pacificclimate/station-data-portal":
        raise ValueError("Unexpected portal repository")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Portal revision must be a full, immutable commit SHA")
    if args.local_preview:
        checkout = args.local_preview.resolve()
        revision = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True,
        ).strip()
        files = local_files(checkout)
    else:
        base_url = f"https://raw.githubusercontent.com/{repository}/{revision}"

        def read_file(name):
            with urlopen(f"{base_url}/{quote(name)}", timeout=30) as response:
                return response.read()

        files = read_source(read_file)
    version = write_guide(
        files, DOCS / "source/portal", repository, revision,
        preview=args.local_preview is not None,
    )
    print(f"Imported portal {version} ({revision})" + (
        " — LOCAL PREVIEW" if args.local_preview else ""
    ))


if __name__ == "__main__":
    main()
