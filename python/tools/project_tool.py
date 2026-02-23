"""
Agent Zero Tool: project_tool
================================
Create, clone, list, activate, deactivate, update, delete,
and inspect projects conversationally.
Wraps the existing python/helpers/projects.py logic.
"""

import asyncio
import random
from python.helpers.tool import Tool, Response
from python.helpers import projects
from python.helpers.print_style import PrintStyle


# Available color map for conversational color selection
COLOR_MAP = {
    "red": "#ef4444",
    "orange": "#f97316",
    "amber": "#f59e0b",
    "yellow": "#eab308",
    "lime": "#84cc16",
    "green": "#22c55e",
    "emerald": "#10b981",
    "teal": "#14b8a6",
    "cyan": "#06b6d4",
    "sky": "#0ea5e9",
    "blue": "#3b82f6",
    "indigo": "#6366f1",
    "violet": "#8b5cf6",
    "purple": "#a855f7",
    "fuchsia": "#d946ef",
    "pink": "#ec4899",
    "rose": "#f43f5e",
}


class ProjectTool(Tool):

    async def execute(self, **kwargs) -> Response:
        action = (self.args.get("action") or "").strip().lower()

        try:
            if action == "create":
                return await asyncio.to_thread(self._create)
            elif action == "clone":
                return await self._clone()
            elif action == "list":
                return await asyncio.to_thread(self._list)
            elif action == "activate":
                return await asyncio.to_thread(self._activate)
            elif action == "deactivate":
                return await asyncio.to_thread(self._deactivate)
            elif action == "update":
                return await asyncio.to_thread(self._update)
            elif action == "delete":
                return await asyncio.to_thread(self._delete)
            elif action == "status":
                return await asyncio.to_thread(self._status)
            else:
                return Response(
                    message=(
                        "Error: 'action' is required. Supported actions: "
                        "create, clone, list, activate, deactivate, update, delete, status."
                    ),
                    break_loop=False,
                )
        except Exception as e:
            PrintStyle().error(f"Project tool error: {e}")
            return Response(message=f"Project error: {e}", break_loop=False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _create(self) -> Response:
        name = (self.args.get("name") or "").strip()
        if not name:
            return Response(message="Error: 'name' is required.", break_loop=False)

        title = (self.args.get("title") or "").strip() or name
        description = (self.args.get("description") or "").strip()
        instructions = (self.args.get("instructions") or "").strip()
        color = self._resolve_color(self.args.get("color", ""))

        data = projects.BasicProjectData(
            title=title,
            description=description,
            instructions=instructions,
            color=color,
            git_url="",
            memory="own",
            file_structure=projects._default_file_structure_settings(),
        )
        created_name = projects.create_project(name, data)

        # Auto-activate on the current context
        context_id = self.agent.context.id
        projects.activate_project(context_id, created_name)

        return Response(
            message=(
                f"✅ Project created and activated!\n"
                f"- **Name**: {created_name}\n"
                f"- **Title**: {title}\n"
                f"- **Path**: /usr/projects/{created_name}\n"
                f"- **Color**: {color or 'none'}\n"
                f"- **Instructions**: {instructions[:100] + '...' if len(instructions) > 100 else instructions or '(none)'}"
            ),
            break_loop=False,
        )

    async def _clone(self) -> Response:
        name = (self.args.get("name") or "").strip()
        git_url = (self.args.get("git_url") or "").strip()
        git_token = (self.args.get("git_token") or "").strip()

        if not name:
            return Response(message="Error: 'name' is required.", break_loop=False)
        if not git_url:
            return Response(message="Error: 'git_url' is required for cloning.", break_loop=False)

        title = (self.args.get("title") or "").strip() or name
        description = (self.args.get("description") or "").strip()
        instructions = (self.args.get("instructions") or "").strip()
        color = self._resolve_color(self.args.get("color", ""))

        data = projects.BasicProjectData(
            title=title,
            description=description,
            instructions=instructions,
            color=color,
            git_url=git_url,
            memory="own",
            file_structure=projects._default_file_structure_settings(),
        )

        # Clone can take a while — run in thread
        created_name = await asyncio.to_thread(
            projects.clone_git_project, name, git_url, git_token, data
        )

        # Auto-activate
        context_id = self.agent.context.id
        projects.activate_project(context_id, created_name)

        # Get git status for the response
        edit_data = projects.load_edit_project_data(created_name)
        git_status = edit_data.get("git_status", {})
        branch = git_status.get("current_branch", "unknown")

        return Response(
            message=(
                f"✅ Repository cloned and project activated!\n"
                f"- **Name**: {created_name}\n"
                f"- **Title**: {title}\n"
                f"- **Path**: /usr/projects/{created_name}\n"
                f"- **Git**: {git_url} (branch: {branch})\n"
                f"- **Color**: {color or 'none'}\n"
                f"- **Instructions**: {instructions[:100] + '...' if len(instructions) > 100 else instructions or '(none)'}"
            ),
            break_loop=False,
        )

    def _list(self) -> Response:
        project_list = projects.get_active_projects_list()
        if not project_list:
            return Response(
                message="No projects found. Use action='create' or action='clone' to start one.",
                break_loop=False,
            )

        # Check which project is active on this context
        active_name = projects.get_context_project_name(self.agent.context)

        lines = [f"**Projects ({len(project_list)}):**\n"]
        for i, p in enumerate(project_list, 1):
            name = p.get("name", "")
            title = p.get("title", "") or name
            desc = p.get("description", "")
            color = p.get("color", "")
            active_marker = " ← **ACTIVE**" if name == active_name else ""

            color_dot = ""
            if color:
                # Find the color name from our map
                color_name = next((k for k, v in COLOR_MAP.items() if v == color), "")
                color_dot = f"🔵 " if color_name == "blue" else f"● "

            line = f"{i}. {color_dot}**{title}** (`{name}`)"
            if desc:
                line += f" — {desc[:60]}"
            line += active_marker
            lines.append(line)

        return Response(message="\n".join(lines), break_loop=False)

    def _activate(self) -> Response:
        name = (self.args.get("name") or "").strip()
        if not name:
            return Response(message="Error: 'name' is required.", break_loop=False)

        context_id = self.agent.context.id
        projects.activate_project(context_id, name)

        data = projects.load_basic_project_data(name)
        title = data.get("title", name)

        return Response(
            message=f"✅ Project **{title}** (`{name}`) is now active. I will work inside /usr/projects/{name}.",
            break_loop=False,
        )

    def _deactivate(self) -> Response:
        context_id = self.agent.context.id
        current = projects.get_context_project_name(self.agent.context)

        if not current:
            return Response(message="No project is currently active.", break_loop=False)

        projects.deactivate_project(context_id)
        return Response(
            message=f"✅ Project `{current}` deactivated. No project is active now.",
            break_loop=False,
        )

    def _update(self) -> Response:
        name = (self.args.get("name") or "").strip()
        if not name:
            # Try to use the currently active project
            name = projects.get_context_project_name(self.agent.context) or ""
        if not name:
            return Response(
                message="Error: 'name' is required (or activate a project first).",
                break_loop=False,
            )

        # Load current data
        current = projects.load_edit_project_data(name)

        # Apply updates only for provided fields
        if "title" in self.args:
            current["title"] = self.args["title"]
        if "description" in self.args:
            current["description"] = self.args["description"]
        if "instructions" in self.args:
            current["instructions"] = self.args["instructions"]
        if "color" in self.args:
            current["color"] = self._resolve_color(self.args["color"])
        if "variables" in self.args:
            current["variables"] = self.args["variables"]
        if "secrets" in self.args:
            current["secrets"] = self.args["secrets"]

        projects.update_project(name, current)

        updated_fields = [k for k in ("title", "description", "instructions", "color", "variables", "secrets") if k in self.args]
        return Response(
            message=f"✅ Project `{name}` updated. Changed: {', '.join(updated_fields)}.",
            break_loop=False,
        )

    def _delete(self) -> Response:
        name = (self.args.get("name") or "").strip()
        confirm = (self.args.get("confirm") or "").strip().lower()

        if not name:
            return Response(message="Error: 'name' is required.", break_loop=False)

        if confirm != "yes":
            return Response(
                message=(
                    f"⚠️ **Delete confirmation required.** Deleting project `{name}` "
                    f"will permanently remove all files in /usr/projects/{name}.\n\n"
                    f"To confirm, call project_tool again with action='delete', name='{name}', confirm='yes'."
                ),
                break_loop=False,
            )

        projects.delete_project(name)
        return Response(
            message=f"✅ Project `{name}` has been deleted.",
            break_loop=False,
        )

    def _status(self) -> Response:
        name = (self.args.get("name") or "").strip()
        if not name:
            name = projects.get_context_project_name(self.agent.context) or ""
        if not name:
            return Response(
                message="Error: 'name' is required (or activate a project first).",
                break_loop=False,
            )

        data = projects.load_edit_project_data(name)
        git_status = data.get("git_status", {})

        lines = [
            f"**Project: {data.get('title', name)}** (`{name}`)\n",
            f"- **Path**: /usr/projects/{name}",
            f"- **Description**: {data.get('description', '') or '(none)'}",
            f"- **Color**: {data.get('color', '') or '(none)'}",
            f"- **Memory**: {data.get('memory', 'own')}",
            f"- **Instruction files**: {data.get('instruction_files_count', 0)}",
            f"- **Knowledge files**: {data.get('knowledge_files_count', 0)}",
        ]

        if git_status.get("is_git_repo"):
            lines.append(f"\n**Git Status:**")
            lines.append(f"- **Remote**: {git_status.get('remote_url', 'none')}")
            lines.append(f"- **Branch**: {git_status.get('current_branch', 'unknown')}")
            lines.append(f"- **Status**: {'● Dirty' if git_status.get('is_dirty') else '✓ Clean'}")
            last_commit = git_status.get("last_commit", {})
            if last_commit:
                lines.append(
                    f"- **Last commit**: {last_commit.get('hash', '')[:8]} "
                    f"\"{last_commit.get('message', '')}\" "
                    f"by {last_commit.get('author', '')} on {last_commit.get('date', '')}"
                )

        # File structure
        try:
            tree = projects.get_file_structure(name)
            if tree.strip():
                lines.append(f"\n**File structure:**\n```\n{tree}\n```")
        except Exception:
            pass

        return Response(message="\n".join(lines), break_loop=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_color(self, color_input: str) -> str:
        """Resolve a color name or hex value. Auto-assigns a random color if empty."""
        if not color_input:
            # Auto-assign a random color from the palette
            return random.choice(list(COLOR_MAP.values()))
        color_input = color_input.strip().lower()
        # Check if it's a named color
        if color_input in COLOR_MAP:
            return COLOR_MAP[color_input]
        # Check if it's already a hex color
        if color_input.startswith("#"):
            return color_input
        # Unknown name — auto-assign
        return random.choice(list(COLOR_MAP.values()))

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        # Don't log sensitive fields
        kvps.pop("git_token", None)
        kvps.pop("secrets", None)
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://folder_open {self.agent.agent_name}: Project",
            content="",
            kvps=kvps,
        )
