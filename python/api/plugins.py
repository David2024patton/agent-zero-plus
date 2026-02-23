"""
API endpoint: /plugins
Actions: list, enable, disable, save_config
Discovers plugins from the plugins/ directory by scanning for plugin.json manifests.
"""
import json
import os
from pathlib import Path
from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import files


PLUGINS_DIR = files.get_abs_path("plugins")


class Plugins(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "")

        try:
            if action == "list":
                data = self._list_plugins()
            elif action == "enable":
                data = self._set_enabled(input, True)
            elif action == "disable":
                data = self._set_enabled(input, False)
            elif action == "save_config":
                data = self._save_config(input)
            else:
                raise Exception(f"Invalid action: {action}")

            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_plugins(self) -> list:
        """Discover all plugins from the plugins/ directory."""
        result = []
        plugins_path = Path(PLUGINS_DIR)

        if not plugins_path.exists():
            return result

        for entry in sorted(plugins_path.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)

                plugin_id = manifest.get("id", entry.name)
                config_schema = manifest.get("config", {})

                # Load saved config values (if any)
                saved_config = self._load_saved_config(plugin_id)

                # Merge schema defaults with saved values
                config_fields = []
                for key, schema in config_schema.items():
                    saved_val = saved_config.get(key)
                    if saved_val is not None:
                        value = saved_val
                    elif "env" in schema:
                        value = os.environ.get(schema["env"], schema.get("default", ""))
                    else:
                        value = schema.get("default", "")

                    # Mask sensitive fields
                    display_value = value
                    if schema.get("sensitive", False) and value:
                        display_value = "****PSWD****"

                    config_fields.append({
                        "key": key,
                        "label": schema.get("label", key),
                        "description": schema.get("description", ""),
                        "type": schema.get("type", "text"),
                        "value": display_value,
                        "sensitive": schema.get("sensitive", False),
                        "env": schema.get("env", ""),
                    })

                result.append({
                    "id": plugin_id,
                    "name": manifest.get("name", plugin_id),
                    "description": manifest.get("description", ""),
                    "version": manifest.get("version", ""),
                    "type": manifest.get("type", "channel"),
                    "path": str(entry),
                    "enabled": self._is_enabled(plugin_id),
                    "config": config_fields,
                })
            except Exception as e:
                result.append({
                    "id": entry.name,
                    "name": entry.name,
                    "description": f"Error loading manifest: {e}",
                    "version": "",
                    "type": "unknown",
                    "path": str(entry),
                    "enabled": False,
                    "config": [],
                    "error": str(e),
                })

        return result

    def _set_enabled(self, input: Input, enabled: bool) -> dict:
        """Enable or disable a plugin."""
        plugin_id = input.get("plugin_id", "").strip()
        if not plugin_id:
            raise Exception("plugin_id is required")

        state = self._load_state()
        if "enabled" not in state:
            state["enabled"] = {}
        state["enabled"][plugin_id] = enabled
        self._save_state(state)

        return {"plugin_id": plugin_id, "enabled": enabled}

    def _save_config(self, input: Input) -> dict:
        """Save configuration values for a plugin."""
        plugin_id = input.get("plugin_id", "").strip()
        config = input.get("config", {})
        if not plugin_id:
            raise Exception("plugin_id is required")

        # Load manifest to check for sensitive fields
        manifest = self._load_manifest(plugin_id)
        config_schema = manifest.get("config", {})

        state = self._load_state()
        if "configs" not in state:
            state["configs"] = {}
        if plugin_id not in state["configs"]:
            state["configs"][plugin_id] = {}

        for key, value in config.items():
            schema = config_schema.get(key, {})
            # Don't save masked values
            if value == "****PSWD****":
                continue
            # Save to env file if env key is specified
            if schema.get("env"):
                from python.helpers import dotenv
                dotenv.save_dotenv_value(schema["env"], value)
            state["configs"][plugin_id][key] = value

        self._save_state(state)
        return {"plugin_id": plugin_id, "saved": True}

    # --- State management ---

    def _state_file(self) -> Path:
        return Path(files.get_abs_path("usr", "plugins_state.json"))

    def _load_state(self) -> dict:
        sf = self._state_file()
        if sf.exists():
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_state(self, state: dict):
        sf = self._state_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        with open(sf, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _is_enabled(self, plugin_id: str) -> bool:
        state = self._load_state()
        return state.get("enabled", {}).get(plugin_id, False)

    def _load_saved_config(self, plugin_id: str) -> dict:
        state = self._load_state()
        return state.get("configs", {}).get(plugin_id, {})

    def _load_manifest(self, plugin_id: str) -> dict:
        plugins_path = Path(PLUGINS_DIR)
        for entry in plugins_path.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "plugin.json"
            if not manifest_path.exists():
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                if manifest.get("id") == plugin_id or entry.name == plugin_id:
                    return manifest
            except Exception:
                continue
        return {}
