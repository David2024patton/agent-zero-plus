### browser_agent:

subordinate agent controls playwright browser
message argument talks to agent give clear instructions credentials task based
reset argument spawns new agent
do not reset if iterating
max_steps controls how many actions the browser agent can take (default 50, range 5-200)
use low max_steps (10-15) for simple navigation, higher (50-100) for complex multi-page workflows
be precise descriptive like: open google login and end task, log in using ... and end task
when following up start: considering open pages
dont use phrase wait for instructions use end task
downloads default in /a0/tmp/downloads
pass secrets and variables in message when needed
if browser agent reports HUMAN_HELP_NEEDED, relay the message to the user and wait for their input
cookies and login sessions persist across browser tasks — no need to re-login each time

usage:
```json
{
  "thoughts": ["I need to log in to..."],
  "headline": "Opening new browser session for login",
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Open and log me into...",
    "reset": "true",
    "max_steps": "20"
  }
}
```

```json
{
  "thoughts": ["I need to log in to..."],
  "headline": "Continuing with existing browser session",
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Considering open pages, click...",
    "reset": "false"
  }
}
```
