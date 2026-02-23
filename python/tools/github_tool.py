"""
Agent Zero Tool: github_tool
==============================
GitHub operations via the `gh` CLI and REST API.
Requires GITHUB_PERSONAL_ACCESS_TOKEN env var or `gh auth login`.
"""

import os
import asyncio
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class GitHubTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        methods = {
            "list_repos": self._list_repos,
            "create_repo": self._create_repo,
            "list_issues": self._list_issues,
            "create_issue": self._create_issue,
            "create_pr": self._create_pr,
            "list_prs": self._list_prs,
            "clone": self._clone,
            "status": self._status,
            "get_file": self._get_file,
            "create_gist": self._create_gist,
            "list_workflows": self._list_workflows,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"GitHub tool error: {e}")
            return Response(message=f"GitHub error: {e}", break_loop=False)

    async def _run_gh(self, *args: str) -> tuple[str, str, int]:
        """Run a gh CLI command and return (stdout, stderr, returncode)."""
        proc = await asyncio.create_subprocess_exec(
            "gh", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
            proc.returncode or 0,
        )

    async def _list_repos(self) -> Response:
        owner = self.args.get("owner", "")
        limit = str(self.args.get("limit", 30))

        if owner:
            out, err, rc = await self._run_gh("repo", "list", owner, "--limit", limit, "--json", "name,description,visibility,updatedAt")
        else:
            out, err, rc = await self._run_gh("repo", "list", "--limit", limit, "--json", "name,description,visibility,updatedAt")

        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=out or "No repositories found.", break_loop=False)

    async def _create_repo(self) -> Response:
        name = (self.args.get("name") or "").strip()
        private = str(self.args.get("private", "true")).lower() == "true"
        description = (self.args.get("description") or "").strip()

        if not name:
            return Response(message="Error: 'name' is required.", break_loop=False)

        cmd = ["repo", "create", name, "--confirm"]
        cmd.append("--private" if private else "--public")
        if description:
            cmd.extend(["--description", description])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=f"Repository created: {out}", break_loop=False)

    async def _list_issues(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        state = self.args.get("state", "open")
        limit = str(self.args.get("limit", 20))

        cmd = ["issue", "list", "--state", state, "--limit", limit, "--json", "number,title,state,author,createdAt"]
        if repo:
            cmd.extend(["-R", repo])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=out or "No issues found.", break_loop=False)

    async def _create_issue(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        title = (self.args.get("title") or "").strip()
        body = (self.args.get("body") or "").strip()

        if not title:
            return Response(message="Error: 'title' is required.", break_loop=False)

        cmd = ["issue", "create", "--title", title]
        if body:
            cmd.extend(["--body", body])
        if repo:
            cmd.extend(["-R", repo])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=f"Issue created: {out}", break_loop=False)

    async def _create_pr(self) -> Response:
        title = (self.args.get("title") or "").strip()
        body = (self.args.get("body") or "").strip()
        base = (self.args.get("base") or "main").strip()
        head = (self.args.get("head") or "").strip()
        repo = (self.args.get("repo") or "").strip()

        if not title:
            return Response(message="Error: 'title' is required.", break_loop=False)

        cmd = ["pr", "create", "--title", title, "--base", base]
        if body:
            cmd.extend(["--body", body])
        if head:
            cmd.extend(["--head", head])
        if repo:
            cmd.extend(["-R", repo])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=f"PR created: {out}", break_loop=False)

    async def _list_prs(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        state = self.args.get("state", "open")
        limit = str(self.args.get("limit", 20))

        cmd = ["pr", "list", "--state", state, "--limit", limit, "--json", "number,title,state,author,createdAt"]
        if repo:
            cmd.extend(["-R", repo])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=out or "No pull requests found.", break_loop=False)

    async def _clone(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        directory = (self.args.get("directory") or "").strip()

        if not repo:
            return Response(message="Error: 'repo' is required.", break_loop=False)

        cmd = ["repo", "clone", repo]
        if directory:
            cmd.append(directory)

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=f"Cloned: {out or repo}", break_loop=False)

    async def _status(self) -> Response:
        out, err, rc = await self._run_gh("auth", "status")
        return Response(message=out or err or "gh CLI not configured", break_loop=False)

    async def _get_file(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        path = (self.args.get("path") or "").strip()
        ref = (self.args.get("ref") or "").strip()

        if not repo or not path:
            return Response(message="Error: 'repo' and 'path' are required.", break_loop=False)

        cmd = ["api", f"/repos/{repo}/contents/{path}"]
        if ref:
            cmd.extend(["-f", f"ref={ref}"])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)

        try:
            data = json.loads(out)
            import base64
            if "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return Response(
                    message=f"**{data.get('name', path)}** ({data.get('size', '?')} bytes):\n\n```\n{content[:5000]}\n```",
                    break_loop=False,
                )
            return Response(message=out[:3000], break_loop=False)
        except Exception:
            return Response(message=out[:3000], break_loop=False)

    async def _create_gist(self) -> Response:
        filename = (self.args.get("filename") or "snippet.txt").strip()
        content = (self.args.get("content") or "").strip()
        description = (self.args.get("description") or "").strip()
        public = str(self.args.get("public", "false")).lower() == "true"

        if not content:
            return Response(message="Error: 'content' is required.", break_loop=False)

        cmd = ["gist", "create", "-"]
        if description:
            cmd.extend(["--desc", description])
        if public:
            cmd.append("--public")

        # Write content to stdin via a temp file approach
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{filename}", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            out, err, rc = await self._run_gh("gist", "create", tmp_path,
                                               *(["--desc", description] if description else []),
                                               *(["--public"] if public else []))
        finally:
            os.remove(tmp_path)

        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=f"Gist created: {out}", break_loop=False)

    async def _list_workflows(self) -> Response:
        repo = (self.args.get("repo") or "").strip()
        limit = str(self.args.get("limit", 10))

        cmd = ["run", "list", "--limit", limit, "--json", "databaseId,displayTitle,status,conclusion,createdAt"]
        if repo:
            cmd.extend(["-R", repo])

        out, err, rc = await self._run_gh(*cmd)
        if rc != 0:
            return Response(message=f"Error: {err or out}", break_loop=False)
        return Response(message=out or "No workflow runs found.", break_loop=False)
    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://code {self.agent.agent_name}: GitHub",
            content="",
            kvps=kvps,
        )
