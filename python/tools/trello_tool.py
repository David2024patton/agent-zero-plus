"""
Agent Zero Tool: trello_tool
==============================
Manage Trello boards, lists, and cards via the Trello REST API.
Requires TRELLO_API_KEY and TRELLO_TOKEN environment variables.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://api.trello.com/1"


class TrelloTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        api_key = os.environ.get("TRELLO_API_KEY", "").strip()
        token = os.environ.get("TRELLO_TOKEN", "").strip()

        if not api_key or not token:
            return Response(
                message="Error: TRELLO_API_KEY and TRELLO_TOKEN environment variables are required.",
                break_loop=False,
            )

        self._auth = {"key": api_key, "token": token}

        methods = {
            "list_boards": self._list_boards,
            "list_lists": self._list_lists,
            "list_cards": self._list_cards,
            "create_card": self._create_card,
            "move_card": self._move_card,
            "comment_card": self._comment_card,
            "archive_card": self._archive_card,
            "create_list": self._create_list,
            "update_card": self._update_card,
            "add_label": self._add_label,
            "search": self._search,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"Trello tool error: {e}")
            return Response(message=f"Trello error: {e}", break_loop=False)

    async def _api_get(self, path: str, params: dict = {}) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BASE_URL}{path}",
                params={**self._auth, **params},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json()

    async def _api_post(self, path: str, data: dict = {}) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}{path}",
                params=self._auth,
                json=data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json()

    async def _api_put(self, path: str, data: dict = {}) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{BASE_URL}{path}",
                params={**self._auth, **data},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json()

    async def _list_boards(self) -> Response:
        data = await self._api_get("/members/me/boards", {"fields": "name,url,dateLastActivity"})
        if not data:
            return Response(message="No boards found.", break_loop=False)
        lines = [f"**Trello Boards ({len(data)}):**\n"]
        for b in data:
            lines.append(f"- **{b['name']}** (id: `{b['id']}`)\n  {b.get('url', '')}")
        return Response(message="\n".join(lines), break_loop=False)

    async def _list_lists(self) -> Response:
        board_id = (self.args.get("board_id") or "").strip()
        if not board_id:
            return Response(message="Error: 'board_id' is required.", break_loop=False)
        data = await self._api_get(f"/boards/{board_id}/lists", {"fields": "name,id"})
        lines = [f"**Lists on board:**\n"]
        for l in data:
            lines.append(f"- **{l['name']}** (id: `{l['id']}`)")
        return Response(message="\n".join(lines), break_loop=False)

    async def _list_cards(self) -> Response:
        list_id = (self.args.get("list_id") or "").strip()
        if not list_id:
            return Response(message="Error: 'list_id' is required.", break_loop=False)
        data = await self._api_get(f"/lists/{list_id}/cards", {"fields": "name,id,desc,due,labels"})
        if not data:
            return Response(message="No cards in this list.", break_loop=False)
        lines = [f"**Cards ({len(data)}):**\n"]
        for c in data:
            due = f" (due: {c['due']})" if c.get('due') else ""
            lines.append(f"- **{c['name']}**{due} (id: `{c['id']}`)")
        return Response(message="\n".join(lines), break_loop=False)

    async def _create_card(self) -> Response:
        list_id = (self.args.get("list_id") or "").strip()
        name = (self.args.get("name") or "").strip()
        desc = (self.args.get("description") or "").strip()

        if not list_id or not name:
            return Response(message="Error: 'list_id' and 'name' are required.", break_loop=False)

        params = {**self._auth, "idList": list_id, "name": name}
        if desc:
            params["desc"] = desc

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BASE_URL}/cards", params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()

        return Response(message=f"Card created: **{data.get('name', name)}** (id: `{data.get('id', 'unknown')}`)", break_loop=False)

    async def _move_card(self) -> Response:
        card_id = (self.args.get("card_id") or "").strip()
        list_id = (self.args.get("list_id") or "").strip()
        if not card_id or not list_id:
            return Response(message="Error: 'card_id' and 'list_id' are required.", break_loop=False)
        await self._api_put(f"/cards/{card_id}", {"idList": list_id})
        return Response(message=f"Card `{card_id}` moved to list `{list_id}`", break_loop=False)

    async def _comment_card(self) -> Response:
        card_id = (self.args.get("card_id") or "").strip()
        text = (self.args.get("text") or "").strip()
        if not card_id or not text:
            return Response(message="Error: 'card_id' and 'text' are required.", break_loop=False)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/cards/{card_id}/actions/comments",
                params={**self._auth, "text": text},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                await resp.json()

        return Response(message=f"Comment added to card `{card_id}`", break_loop=False)

    async def _archive_card(self) -> Response:
        card_id = (self.args.get("card_id") or "").strip()
        if not card_id:
            return Response(message="Error: 'card_id' is required.", break_loop=False)
        await self._api_put(f"/cards/{card_id}", {"closed": "true"})
        return Response(message=f"Card `{card_id}` archived.", break_loop=False)

    async def _create_list(self) -> Response:
        board_id = (self.args.get("board_id") or "").strip()
        name = (self.args.get("name") or "").strip()
        if not board_id or not name:
            return Response(message="Error: 'board_id' and 'name' are required.", break_loop=False)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/lists",
                params={**self._auth, "name": name, "idBoard": board_id},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        return Response(message=f"List created: **{data.get('name', name)}** (id: `{data.get('id', 'unknown')}`)", break_loop=False)

    async def _update_card(self) -> Response:
        card_id = (self.args.get("card_id") or "").strip()
        if not card_id:
            return Response(message="Error: 'card_id' is required.", break_loop=False)

        params: dict = {}
        name = (self.args.get("name") or "").strip()
        desc = (self.args.get("description") or "").strip()
        due = (self.args.get("due") or "").strip()

        if name:
            params["name"] = name
        if desc:
            params["desc"] = desc
        if due:
            params["due"] = due

        if not params:
            return Response(message="Error: at least one of 'name', 'description', 'due' is required.", break_loop=False)

        await self._api_put(f"/cards/{card_id}", params)
        return Response(message=f"Card `{card_id}` updated.", break_loop=False)

    async def _add_label(self) -> Response:
        card_id = (self.args.get("card_id") or "").strip()
        label_id = (self.args.get("label_id") or "").strip()
        color = (self.args.get("color") or "").strip()
        label_name = (self.args.get("label_name") or "").strip()

        if not card_id:
            return Response(message="Error: 'card_id' is required.", break_loop=False)

        if label_id:
            # Attach existing label
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BASE_URL}/cards/{card_id}/idLabels",
                    params={**self._auth, "value": label_id},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    await resp.json()
            return Response(message=f"Label `{label_id}` added to card `{card_id}`.", break_loop=False)
        elif color:
            # Create new label on the card
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BASE_URL}/cards/{card_id}/labels",
                    params={**self._auth, "color": color, "name": label_name},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
            return Response(message=f"Label created and added: {data.get('color', color)} (id: `{data.get('id', '?')}`)", break_loop=False)
        else:
            return Response(message="Error: 'label_id' or 'color' is required.", break_loop=False)

    async def _search(self) -> Response:
        query = (self.args.get("query") or "").strip()
        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        data = await self._api_get("/search", {"query": query, "modelTypes": "cards,boards"})

        lines = [f"**Trello Search: '{query}'**\n"]

        boards = data.get("boards", [])
        if boards:
            lines.append(f"**Boards ({len(boards)}):**")
            for b in boards[:5]:
                lines.append(f"- **{b['name']}** (id: `{b['id']}`)")

        cards = data.get("cards", [])
        if cards:
            lines.append(f"\n**Cards ({len(cards)}):**")
            for c in cards[:10]:
                lines.append(f"- **{c['name']}** (id: `{c['id']}`)")

        if not boards and not cards:
            lines.append("No results found.")

        return Response(message="\n".join(lines), break_loop=False)
    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://view_kanban {self.agent.agent_name}: Trello",
            content="",
            kvps=kvps,
        )
