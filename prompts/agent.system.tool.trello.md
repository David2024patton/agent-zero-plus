### trello_tool
Manage Trello boards, lists, and cards. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.
Methods: list_boards, list_lists, list_cards, create_card, move_card, comment_card, archive_card, create_list, update_card, add_label, search.
**Example — list boards:**
~~~json
{
    "tool_name": "trello_tool",
    "tool_args": {
        "method": "list_boards"
    }
}
~~~
**Example — create card:**
~~~json
{
    "tool_name": "trello_tool",
    "tool_args": {
        "method": "create_card",
        "list_id": "abc123",
        "name": "Fix login bug",
        "description": "Login fails on mobile"
    }
}
~~~
**Parameters by method:**
- **list_boards**: (no args)
- **list_lists**: board_id (required)
- **list_cards**: list_id (required)
- **create_card**: list_id, name (required), description
- **move_card**: card_id, list_id (required)
- **comment_card**: card_id, text (required)
- **archive_card**: card_id (required)
- **create_list**: board_id, name (required)
- **update_card**: card_id (required), name, description, due
- **add_label**: card_id (required), label_id or color (required), label_name
- **search**: query (required) — searches boards and cards
