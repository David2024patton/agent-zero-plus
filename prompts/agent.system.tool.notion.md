### notion_tool
Manage Notion pages, databases, and blocks. Requires NOTION_API_KEY env var.
Methods: search, get_page, create_page, update_page, query_database, get_block_children, append_block, delete_block, create_database.
**Example — search:**
~~~json
{
    "tool_name": "notion_tool",
    "tool_args": {
        "method": "search",
        "query": "project notes",
        "filter_type": "page"
    }
}
~~~
**Example — create page in database:**
~~~json
{
    "tool_name": "notion_tool",
    "tool_args": {
        "method": "create_page",
        "parent_id": "database-id-here",
        "parent_type": "database",
        "title": "Meeting Notes",
        "content": "Discussion points..."
    }
}
~~~
**Parameters by method:**
- **search**: query, filter_type ("page" or "database")
- **get_page**: page_id (required)
- **create_page**: parent_id, parent_type ("database"/"page"), title, content
- **update_page**: page_id, properties (JSON)
- **query_database**: database_id (required), filter (JSON)
- **get_block_children**: block_id (required)
- **append_block**: parent_id, content, block_type (default "paragraph")
- **delete_block**: block_id (required) — archives/deletes the block
- **create_database**: parent_id (required), title (required), properties (JSON, optional — defaults to Name/Status)
