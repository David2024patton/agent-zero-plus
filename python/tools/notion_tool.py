"""
Agent Zero Tool: notion_tool
==============================
Manage Notion pages, databases, and blocks via the Notion API.
Requires NOTION_API_KEY environment variable.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        api_key = os.environ.get("NOTION_API_KEY", "").strip()
        if not api_key:
            return Response(
                message="Error: NOTION_API_KEY environment variable is required.",
                break_loop=False,
            )

        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

        methods = {
            "search": self._search,
            "get_page": self._get_page,
            "create_page": self._create_page,
            "update_page": self._update_page,
            "query_database": self._query_database,
            "get_block_children": self._get_block_children,
            "append_block": self._append_block,
            "delete_block": self._delete_block,
            "create_database": self._create_database,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"Notion tool error: {e}")
            return Response(message=f"Notion error: {e}", break_loop=False)

    async def _api(self, http_method: str, path: str, body: dict | None = None) -> dict:
        async with aiohttp.ClientSession() as session:
            method_fn = getattr(session, http_method)
            kwargs = {"headers": self._headers, "timeout": aiohttp.ClientTimeout(total=30)}
            if body:
                kwargs["json"] = body
            async with method_fn(f"{BASE_URL}{path}", **kwargs) as resp:
                return await resp.json()

    async def _search(self) -> Response:
        query = (self.args.get("query") or "").strip()
        filter_type = (self.args.get("filter_type") or "").strip()

        body: dict = {}
        if query:
            body["query"] = query
        if filter_type in ("page", "database"):
            body["filter"] = {"value": filter_type, "property": "object"}

        data = await self._api("post", "/search", body)
        results = data.get("results", [])
        if not results:
            return Response(message="No results found.", break_loop=False)

        lines = [f"**Notion Search Results ({len(results)}):**\n"]
        for r in results:
            obj_type = r.get("object", "")
            title_parts = []
            if "properties" in r and "title" in r["properties"]:
                for t in r["properties"]["title"].get("title", []):
                    title_parts.append(t.get("plain_text", ""))
            elif "properties" in r and "Name" in r["properties"]:
                name_prop = r["properties"]["Name"]
                if "title" in name_prop:
                    for t in name_prop["title"]:
                        title_parts.append(t.get("plain_text", ""))
            title = "".join(title_parts) or "(untitled)"
            lines.append(f"- [{obj_type}] **{title}** (id: `{r['id']}`)")

        return Response(message="\n".join(lines), break_loop=False)

    async def _get_page(self) -> Response:
        page_id = (self.args.get("page_id") or "").strip()
        if not page_id:
            return Response(message="Error: 'page_id' is required.", break_loop=False)

        data = await self._api("get", f"/pages/{page_id}")
        return Response(message=json.dumps(data, indent=2)[:5000], break_loop=False)

    async def _create_page(self) -> Response:
        parent_id = (self.args.get("parent_id") or "").strip()
        parent_type = (self.args.get("parent_type") or "database").strip()
        title = (self.args.get("title") or "").strip()
        content = (self.args.get("content") or "").strip()

        if not parent_id or not title:
            return Response(message="Error: 'parent_id' and 'title' are required.", break_loop=False)

        if parent_type == "database":
            parent = {"database_id": parent_id}
            properties = {"Name": {"title": [{"text": {"content": title}}]}}
        else:
            parent = {"page_id": parent_id}
            properties = {"title": {"title": [{"text": {"content": title}}]}}

        body: dict = {"parent": parent, "properties": properties}

        if content:
            body["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]

        data = await self._api("post", "/pages", body)
        return Response(
            message=f"Page created: **{title}** (id: `{data.get('id', 'unknown')}`)",
            break_loop=False,
        )

    async def _update_page(self) -> Response:
        page_id = (self.args.get("page_id") or "").strip()
        properties_json = (self.args.get("properties") or "").strip()

        if not page_id:
            return Response(message="Error: 'page_id' is required.", break_loop=False)
        if not properties_json:
            return Response(message="Error: 'properties' JSON object is required.", break_loop=False)

        try:
            properties = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
        except json.JSONDecodeError:
            return Response(message="Error: 'properties' must be valid JSON.", break_loop=False)

        data = await self._api("patch", f"/pages/{page_id}", {"properties": properties})
        return Response(message=f"Page `{page_id}` updated.", break_loop=False)

    async def _query_database(self) -> Response:
        database_id = (self.args.get("database_id") or "").strip()
        if not database_id:
            return Response(message="Error: 'database_id' is required.", break_loop=False)

        filter_json = (self.args.get("filter") or "").strip()
        body: dict = {}
        if filter_json:
            try:
                body["filter"] = json.loads(filter_json) if isinstance(filter_json, str) else filter_json
            except json.JSONDecodeError:
                return Response(message="Error: 'filter' must be valid JSON.", break_loop=False)

        data = await self._api("post", f"/databases/{database_id}/query", body)
        results = data.get("results", [])

        lines = [f"**Database Query ({len(results)} results):**\n"]
        for r in results[:20]:
            props = r.get("properties", {})
            title = ""
            for key, val in props.items():
                if val.get("type") == "title":
                    title_parts = val.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    break
            lines.append(f"- **{title or '(untitled)'}** (id: `{r['id']}`)")

        return Response(message="\n".join(lines), break_loop=False)

    async def _get_block_children(self) -> Response:
        block_id = (self.args.get("block_id") or "").strip()
        if not block_id:
            return Response(message="Error: 'block_id' is required.", break_loop=False)

        data = await self._api("get", f"/blocks/{block_id}/children")
        results = data.get("results", [])

        lines = [f"**Block Children ({len(results)}):**\n"]
        for b in results[:30]:
            btype = b.get("type", "unknown")
            text = ""
            if btype in b:
                rich_text = b[btype].get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in rich_text)
            lines.append(f"- [{btype}] {text[:200]}")

        return Response(message="\n".join(lines), break_loop=False)

    async def _append_block(self) -> Response:
        parent_id = (self.args.get("parent_id") or "").strip()
        content = (self.args.get("content") or "").strip()
        block_type = (self.args.get("block_type") or "paragraph").strip()

        if not parent_id or not content:
            return Response(message="Error: 'parent_id' and 'content' are required.", break_loop=False)

        block = {
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{"type": "text", "text": {"content": content}}]
            },
        }

        data = await self._api("patch", f"/blocks/{parent_id}/children", {"children": [block]})
        return Response(message=f"Block appended to `{parent_id}`.", break_loop=False)

    async def _delete_block(self) -> Response:
        block_id = (self.args.get("block_id") or "").strip()
        if not block_id:
            return Response(message="Error: 'block_id' is required.", break_loop=False)

        data = await self._api("delete", f"/blocks/{block_id}")
        return Response(message=f"Block `{block_id}` archived/deleted.", break_loop=False)

    async def _create_database(self) -> Response:
        parent_id = (self.args.get("parent_id") or "").strip()
        title = (self.args.get("title") or "").strip()
        properties_json = (self.args.get("properties") or "").strip()

        if not parent_id or not title:
            return Response(message="Error: 'parent_id' and 'title' are required.", break_loop=False)

        # Default properties if none specified
        if properties_json:
            try:
                properties = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
            except json.JSONDecodeError:
                return Response(message="Error: 'properties' must be valid JSON.", break_loop=False)
        else:
            properties = {
                "Name": {"title": {}},
                "Status": {"select": {"options": [
                    {"name": "To Do", "color": "red"},
                    {"name": "In Progress", "color": "yellow"},
                    {"name": "Done", "color": "green"},
                ]}},
            }

        body = {
            "parent": {"page_id": parent_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }

        data = await self._api("post", "/databases", body)
        return Response(
            message=f"Database created: **{title}** (id: `{data.get('id', 'unknown')}`)",
            break_loop=False,
        )
    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://article {self.agent.agent_name}: Notion",
            content="",
            kvps=kvps,
        )
