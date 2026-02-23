### project_tool
Manage Agent Zero projects conversationally — create, clone, list, switch, update, delete, and inspect projects.
Actions: create, clone, list, activate, deactivate, update, delete, status.

## How to use this tool

### When the user asks you to create a project
1. Ask clarifying questions if important info is missing (name, whether to clone from Git)
2. Derive sensible defaults (project name from repo URL, title from name, etc.)
3. Call the tool with the appropriate action

### Conversational behavior
- **Ask before acting** on destructive operations (delete).
- **Infer defaults** for optional fields (title from name, generate name from git URL).
- **One tool call** per action. Don't call create then immediately activate — create auto-activates.
- **Private repos**: If the user provides a Git URL that might be private, ask for an access token.
- **Secrets warning**: If the user provides secrets (API keys, passwords), warn them that the values pass through the conversation before being saved. Suggest using the Web UI for maximum security.

### Available colors
Named colors you can use: red, orange, amber, yellow, lime, green, emerald, teal, cyan, sky, blue, indigo, violet, purple, fuchsia, pink, rose. You can also use hex values like "#3b82f6".

**Create a new empty project:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "create",
        "name": "my-project",
        "title": "My Project Title",
        "description": "What this project is about",
        "instructions": "Rules for working on this project",
        "color": "blue"
    }
}
~~~

**Clone a Git repository as a project:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "clone",
        "name": "project-name",
        "git_url": "https://github.com/user/repo.git",
        "git_token": "ghp_xxxx",
        "title": "Project Title",
        "description": "Description",
        "instructions": "Project rules",
        "color": "green"
    }
}
~~~

**List all projects:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "list"
    }
}
~~~

**Activate a project on the current chat:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "activate",
        "name": "project-name"
    }
}
~~~

**Deactivate the current project:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "deactivate"
    }
}
~~~

**Update project settings** (only include fields you want to change):
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "update",
        "name": "project-name",
        "title": "New Title",
        "instructions": "Updated instructions",
        "variables": "API_URL=https://api.example.com\nDEBUG=true",
        "secrets": "API_KEY=sk-xxxx"
    }
}
~~~

**Get project status and file structure:**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "status",
        "name": "project-name"
    }
}
~~~

**Delete a project (requires confirmation):**
~~~json
{
    "tool_name": "project_tool",
    "tool_args": {
        "action": "delete",
        "name": "project-name",
        "confirm": "yes"
    }
}
~~~

**Parameters:**
- **action** (required): create, clone, list, activate, deactivate, update, delete, status
- **name**: Project folder name (required for most actions, defaults to active project for update/status)
- **title**: Display title (optional, defaults to name)
- **description**: Project description (optional)
- **instructions**: Rules the agent must follow when working on this project (optional)
- **color**: Color tag — use a name (blue, red, green...) or hex (#3b82f6) (optional)
- **git_url** (clone): Repository URL to clone
- **git_token** (clone): Access token for private repos (used once, not stored)
- **variables** (update): Non-sensitive env variables in KEY=VALUE format, one per line
- **secrets** (update): Sensitive secrets in KEY=VALUE format (⚠️ values pass through conversation)
- **confirm** (delete): Must be "yes" to confirm deletion
