### browser_read:

reads text content from the currently open browser page
no LLM sub-agent needed, direct page scraping
requires an active browser session from browser_agent
optional selector arg to target specific page sections via CSS selector
use this when you need to read or analyze page content without navigating

usage:
```json
{
  "thoughts": ["I need to read the content on the current page..."],
  "headline": "Reading content from current browser page",
  "tool_name": "browser_read",
  "tool_args": {}
}
```

```json
{
  "thoughts": ["I need to read just the main article..."],
  "headline": "Reading specific section from browser page",
  "tool_name": "browser_read",
  "tool_args": {
    "selector": "article.main-content"
  }
}
```
