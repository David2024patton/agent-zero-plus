### github_tool
Manage GitHub repos, issues, PRs via `gh` CLI. Requires `gh auth login` or GITHUB_PERSONAL_ACCESS_TOKEN.
Methods: list_repos, create_repo, list_issues, create_issue, create_pr, list_prs, clone, status, get_file, create_gist, list_workflows.
**Example — list repos:**
~~~json
{
    "tool_name": "github_tool",
    "tool_args": {
        "method": "list_repos",
        "limit": 10
    }
}
~~~
**Example — create issue:**
~~~json
{
    "tool_name": "github_tool",
    "tool_args": {
        "method": "create_issue",
        "repo": "owner/repo",
        "title": "Bug: login fails",
        "body": "Steps to reproduce..."
    }
}
~~~
**Parameters by method:**
- **list_repos**: owner (optional), limit (default 30)
- **create_repo**: name (required), private (default true), description
- **list_issues**: repo, state (open/closed/all), limit
- **create_issue**: title (required), body, repo
- **create_pr**: title (required), base (default main), head, body, repo
- **list_prs**: repo, state, limit
- **clone**: repo (required), directory
- **status**: (no args — shows auth status)
- **get_file**: repo (required, "owner/repo"), path (required), ref (optional branch/tag/sha)
- **create_gist**: content (required), filename, description, public (true/false)
- **list_workflows**: repo (optional), limit (default 10)
