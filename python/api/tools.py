import os
import inspect
from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import files


class Tools(ApiHandler):
    """API handler for managing tools — list available tools and toggle enable/disable."""

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "")

        try:
            if action == "list":
                data = self._list_tools()
            elif action == "toggle":
                data = self._toggle_tool(input)
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

    def _list_tools(self) -> list[dict]:
        """Scan python/tools/ for both active (.py) and disabled (._py) tool files."""
        tools_dir = files.get_abs_path("python", "tools")
        result = []

        if not os.path.isdir(tools_dir):
            return result

        for filename in sorted(os.listdir(tools_dir)):
            # Active tools: *.py (exclude __init__.py, __pycache__)
            # Disabled tools: *._py
            is_active = filename.endswith(".py") and not filename.startswith("__")
            is_disabled = filename.endswith("._py")

            if not is_active and not is_disabled:
                continue

            filepath = os.path.join(tools_dir, filename)
            if not os.path.isfile(filepath):
                continue

            # Extract name (strip extension)
            if is_active:
                name = filename[:-3]  # remove .py
            else:
                name = filename[:-4]  # remove ._py

            # Try to extract docstring from the file
            description = self._extract_docstring(filepath)

            result.append({
                "name": name,
                "filename": filename,
                "path": filepath,
                "enabled": is_active,
                "description": description,
            })

        return result

    def _extract_docstring(self, filepath: str) -> str:
        """Extract the first class docstring from a tool file."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Simple regex-free extraction: find class ... : then triple-quoted string
            lines = content.split("\n")
            in_class = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("class ") and ":" in stripped:
                    in_class = True
                    continue
                if in_class and stripped.startswith('"""'):
                    # Single-line docstring
                    if stripped.count('"""') >= 2:
                        return stripped.strip('"""').strip()
                    # Multi-line: collect until closing """
                    doc_lines = [stripped.lstrip('"""')]
                    for j in range(i + 1, min(i + 20, len(lines))):
                        dline = lines[j].strip()
                        if '"""' in dline:
                            doc_lines.append(dline.rstrip('"""').strip())
                            break
                        doc_lines.append(dline)
                    return " ".join(dl for dl in doc_lines if dl)[:300]
                elif in_class and stripped.startswith("'"):
                    if stripped.count("'''") >= 2:
                        return stripped.strip("'''").strip()
                    doc_lines = [stripped.lstrip("'''")]
                    for j in range(i + 1, min(i + 20, len(lines))):
                        dline = lines[j].strip()
                        if "'''" in dline:
                            doc_lines.append(dline.rstrip("'''").strip())
                            break
                        doc_lines.append(dline)
                    return " ".join(dl for dl in doc_lines if dl)[:300]
                elif in_class and stripped and not stripped.startswith("#"):
                    # Non-docstring content found, no docstring
                    break
        except Exception:
            pass
        return ""

    def _toggle_tool(self, input: Input) -> dict:
        """Toggle a tool between enabled (.py) and disabled (._py)."""
        tool_path = str(input.get("tool_path", "")).strip()
        if not tool_path:
            raise Exception("tool_path is required")

        if not os.path.isfile(tool_path):
            raise Exception(f"Tool file not found: {tool_path}")

        tools_dir = files.get_abs_path("python", "tools")
        # Security: ensure the file is in the tools directory
        if not os.path.abspath(tool_path).startswith(os.path.abspath(tools_dir)):
            raise Exception("Tool file must be in the tools directory")

        filename = os.path.basename(tool_path)
        if filename.endswith(".py"):
            # Disable: rename .py -> ._py
            new_path = tool_path[:-3] + "._py"
            os.rename(tool_path, new_path)
            return {"ok": True, "new_path": new_path, "enabled": False}
        elif filename.endswith("._py"):
            # Enable: rename ._py -> .py
            new_path = tool_path[:-4] + ".py"
            os.rename(tool_path, new_path)
            return {"ok": True, "new_path": new_path, "enabled": True}
        else:
            raise Exception("Invalid tool file extension")
