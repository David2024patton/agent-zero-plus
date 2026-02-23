"""
Auto-load skills marked as 'auto-load' in Settings > Skills.

Runs before _65_include_loaded_skills.py so that the skill content
gets injected automatically without requiring a manual
`skills_tool method=load` call.

The auto-load list is stored in usr/auto_load_skills.json,
managed via the Skills list UI checkboxes.
"""
import json
import os

from python.helpers.extension import Extension
from python.helpers import files as files_helper
from python.tools.skills_tool import DATA_NAME_LOADED_SKILLS
from agent import LoopData

AUTO_LOAD_FILE = files_helper.get_abs_path("usr", "auto_load_skills.json")


class AutoLoadSkills(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        auto_skills = self._read_auto_load()
        if not auto_skills:
            return

        loaded = self.agent.data.get(DATA_NAME_LOADED_SKILLS) or []

        for skill_name in auto_skills:
            if skill_name not in loaded:
                loaded.append(skill_name)

        self.agent.data[DATA_NAME_LOADED_SKILLS] = loaded

    @staticmethod
    def _read_auto_load() -> list[str]:
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
