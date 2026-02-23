"""
API endpoint: /plugins_import
Actions: preview, import
Accepts a .zip file upload containing plugin folders with plugin.json manifests.
Extracts valid plugin folders into the plugins/ directory.
"""

import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from python.helpers.api import ApiHandler, Request, Response
from python.helpers import files
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


PLUGINS_DIR = files.get_abs_path("plugins")


class PluginsImport(ApiHandler):
    """Import plugin packs (.zip) into the plugins/ directory."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        if "plugins_file" not in request.files:
            return {"ok": False, "error": "No plugins file provided"}

        plugins_file: FileStorage = request.files["plugins_file"]
        if not plugins_file.filename:
            return {"ok": False, "error": "No file selected"}

        action = (request.form.get("action", "preview") or "preview").strip().lower()

        # Save upload to temp file
        tmp_dir = Path(files.get_abs_path("tmp", "uploads"))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        base = secure_filename(plugins_file.filename)  # type: ignore[arg-type]
        if not base.lower().endswith(".zip"):
            base = f"{base}.zip"
        unique = uuid.uuid4().hex[:8]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        tmp_path = tmp_dir / f"plugins_import_{stamp}_{unique}_{base}"
        plugins_file.save(str(tmp_path))

        try:
            if action == "preview":
                return {"ok": True, "data": self._preview(tmp_path)}
            elif action == "import":
                return {"ok": True, "data": self._import(tmp_path)}
            else:
                return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _scan_zip(self, zip_path: Path) -> list[str]:
        """Scan a zip file and return list of plugin folder names that contain plugin.json."""
        plugin_dirs = []
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            names = zf.namelist()
            # Find all plugin.json files in the archive
            for name in names:
                parts = Path(name).parts
                # plugin.json at top level of a folder: folder/plugin.json
                if len(parts) == 2 and parts[1] == "plugin.json":
                    plugin_dirs.append(parts[0])
                # Or directly at root: plugin.json (single plugin zip)
                elif len(parts) == 1 and parts[0] == "plugin.json":
                    plugin_dirs.append(".")
        return sorted(set(plugin_dirs))

    def _preview(self, zip_path: Path) -> dict:
        """Preview what plugins will be imported."""
        plugin_dirs = self._scan_zip(zip_path)
        plugin_names = []
        for d in plugin_dirs:
            if d == ".":
                plugin_names.append(f"(root plugin from {zip_path.name})")
            else:
                plugin_names.append(d)
        return {
            "plugin_count": len(plugin_dirs),
            "plugins": plugin_names,
        }

    def _import(self, zip_path: Path) -> dict:
        """Extract valid plugin folders into the plugins/ directory."""
        plugin_dirs = self._scan_zip(zip_path)
        if not plugin_dirs:
            return {
                "imported_count": 0,
                "skipped_count": 0,
                "imported": [],
                "skipped": [],
            }

        plugins_path = Path(PLUGINS_DIR)
        plugins_path.mkdir(parents=True, exist_ok=True)

        imported = []
        skipped = []

        # Extract to a temp directory first
        extract_dir = zip_path.parent / f"extract_{uuid.uuid4().hex[:8]}"
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(extract_dir))

            for d in plugin_dirs:
                if d == ".":
                    # Root-level plugin — need to pick a name from plugin.json
                    manifest_path = extract_dir / "plugin.json"
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                        folder_name = manifest.get("id", zip_path.stem)
                    except Exception:
                        folder_name = zip_path.stem
                    src = extract_dir
                else:
                    folder_name = d
                    src = extract_dir / d

                dest = plugins_path / folder_name

                if dest.exists():
                    skipped.append(folder_name)
                    continue

                shutil.copytree(str(src), str(dest))
                imported.append(folder_name)

        finally:
            try:
                shutil.rmtree(str(extract_dir), ignore_errors=True)
            except Exception:
                pass

        return {
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "imported": imported,
            "skipped": skipped,
        }
