"""Checks for the manifest-based importer, independent of the API service."""

import json
from pathlib import Path
import tempfile
import unittest

import yaml

from import_portal import local_files, manifest_paths, read_source, write_guide


class PortalImportTests(unittest.TestCase):
    def files(self):
        return {
            "docs/user/manifest.yaml": b"- root.rst\n- images:\n    - map.svg\n",
            "docs/user/root.rst": b"Portal\n======\n\nGuide content.\n",
            "docs/user/images/map.svg": b"<svg/>",
            "package.json": json.dumps({"version": "2.0.0"}).encode(),
        }

    def test_uses_same_recursive_manifest_structure_as_pdp(self):
        self.assertEqual(manifest_paths(
            b"- root.rst\n- images:\n    - map.svg\n    - detail:\n        - zoom.png\n"
        ), ["root.rst", "images/map.svg", "images/detail/zoom.png"])

    def test_fetches_only_listed_files_and_version_metadata(self):
        source = self.files()
        source["docs/user/conf.py"] = b"raise RuntimeError('must not run')"
        requested = []

        def read_file(path):
            requested.append(path)
            return source[path]

        files = read_source(read_file)
        self.assertNotIn("docs/user/conf.py", requested)
        self.assertEqual(set(files), {
            "docs/user/root.rst", "docs/user/images/map.svg", "package.json",
        })

    def test_rejects_unsafe_or_malformed_manifests(self):
        for content in [
            b"- ../outside.rst", b"- /outside.rst", b"- '..': [root.rst]",
            b"- root.rst\n- 'images/../../outside.rst'", b"- root.rst\n- conf.py",
            b"- root.rst\n- attack.js", b"- root.rst\n- raw.html",
            b"- root.rst\n- root.rst", b"- images: [map.png]", b"[]", b"{}",
            b"- root.rst\n- 42", b"- root.rst\n- &loop {images: [*loop]}",
        ]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                manifest_paths(content)

    def test_rejects_executable_yaml_tags(self):
        with self.assertRaises(yaml.YAMLError):
            manifest_paths(b"!!python/object/apply:os.system ['echo must-not-run']")

    def test_missing_listed_file_fails(self):
        source = self.files()
        del source["docs/user/images/map.svg"]
        with self.assertRaises(KeyError):
            read_source(source.__getitem__)

    def test_local_import_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp)
            for name, content in self.files().items():
                path = checkout / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            (checkout / "docs/user/images/map.svg").unlink()
            (checkout / "docs/user/images/map.svg").symlink_to(
                checkout / "package.json"
            )
            with self.assertRaises(ValueError):
                local_files(checkout)

    def test_import_replaces_stale_files_and_identifies_portal_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "portal"
            target.mkdir()
            (target / "stale.rst").write_text("old guide")
            files = read_source(self.files().__getitem__)
            write_guide(files, target, "pacificclimate/station-data-portal", "a" * 40)
            text = (target / "root.rst").read_text()
            self.assertTrue(text.startswith("Portal\n======\n"))
            self.assertIn("Portal version: **2.0.0**", text)
            self.assertIn("a" * 40, text)
            self.assertNotIn("Local preview", text)
            self.assertFalse((target / "stale.rst").exists())
            self.assertTrue((target / "images/map.svg").exists())
            write_guide(files, target, "pacificclimate/station-data-portal", "a" * 40, True)
            self.assertIn("Local preview", (target / "root.rst").read_text())

    def test_invalid_source_keeps_previous_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "portal"
            target.mkdir()
            (target / "root.rst").write_text("previous guide")
            with self.assertRaises(KeyError):
                write_guide({}, target, "pacificclimate/station-data-portal", "a" * 40)
            self.assertEqual((target / "root.rst").read_text(), "previous guide")


if __name__ == "__main__":
    unittest.main()
