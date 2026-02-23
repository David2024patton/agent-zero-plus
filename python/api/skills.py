import json
import os

from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import runtime, skills, projects, files

AUTO_LOAD_FILE = files.get_abs_path("usr", "auto_load_skills.json")


class Skills(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "")

        try:
            if action == "list":
                data = self.list_skills(input)
            elif action == "delete":
                data = self.delete_skill(input)
            elif action == "get_auto_load":
                data = self.get_auto_load()
            elif action == "set_auto_load":
                data = self.set_auto_load(input)
            else:
                raise Exception("Invalid action")

            return {
                "ok": True,
                "data": data,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }

    def list_skills(self, input: Input):
        skill_list = skills.list_skills()

        # filter by project
        if project_name := (input.get("project_name") or "").strip() or None:
            project_folder = projects.get_project_folder(project_name)
            if runtime.is_development():
                project_folder = files.normalize_a0_path(project_folder)
            skill_list = [
                s for s in skill_list if files.is_in_dir(str(s.path), project_folder)
            ]

        # filter by agent profile
        if agent_profile := (input.get("agent_profile") or "").strip() or None:
            roots: list[str] = [
                files.get_abs_path("agents", agent_profile, "skills"),
                files.get_abs_path("usr", "agents", agent_profile, "skills"),
            ]
            if project_name:
                roots.append(
                    projects.get_project_meta_folder(project_name, "agents", agent_profile, "skills")
                )

            skill_list = [
                s
                for s in skill_list
                if any(files.is_in_dir(str(s.path), r) for r in roots)
            ]

        result = []
        for skill in skill_list:
            result.append({
                "name": skill.name,
                "description": skill.description,
                "path": str(skill.path),
            })
        result.sort(key=lambda x: (x["name"], x["path"]))
        return result

    def delete_skill(self, input: Input):
        skill_path = str(input.get("skill_path") or "").strip()
        if not skill_path:
            raise Exception("skill_path is required")

        skills.delete_skill(skill_path)
        return {"ok": True, "skill_path": skill_path}

    # ── auto-load helpers ────────────────────────────────────────
    @staticmethod
    def _read_auto_load() -> list[str]:
        """Read the list of auto-load skill names from the JSON file."""
        if not os.path.isfile(AUTO_LOAD_FILE):
            return []
        try:
            with open(AUTO_LOAD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [s for s in data if isinstance(s, str) and s.strip()]
            return []
        except Exception:
            return []

    @staticmethod
    def _write_auto_load(names: list[str]) -> None:
        """Write the list of auto-load skill names to the JSON file."""
        os.makedirs(os.path.dirname(AUTO_LOAD_FILE), exist_ok=True)
        with open(AUTO_LOAD_FILE, "w", encoding="utf-8") as f:
            json.dump(names, f, indent=2)

    def get_auto_load(self) -> dict:
        return {"auto_load_skills": self._read_auto_load()}

    def set_auto_load(self, input: Input) -> dict:
        raw = input.get("auto_load_skills")
        if not isinstance(raw, list):
            raise Exception("auto_load_skills must be a list of strings")
        clean = [s.strip() for s in raw if isinstance(s, str) and s.strip()]
        self._write_auto_load(clean)
        return {"auto_load_skills": clean}
