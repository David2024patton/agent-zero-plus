### swarm

Multi-agent orchestration using the Swarms framework.
Spawn multiple specialized agents that work together on complex tasks.
Use this when a task benefits from multiple expert perspectives working in parallel or in sequence.

Settings for swarm orchestration (default type, model, limits, etc.) are configured in Settings → Swarms.

**swarm_type options:**
- "sequential": agents run one after another in a pipeline (output of one feeds into the next)
- "concurrent": all agents run in parallel on the same task
- "mixture": agents run in parallel, then an aggregator synthesizes their outputs
- "group_chat": agents collaborate in a group discussion
- "hierarchical": director agent delegates to worker agents
- "dynamic": agents process sequentially with context enrichment; supports role reassignment when enabled in settings

If swarm_type is omitted, the default from Settings → Swarms → General is used.

**agents field:** JSON array of agent definitions. Each agent needs:
- "name": agent name/role (if matching a saved manifest in Settings, the manifest fields are merged)
- "system_prompt": detailed instructions for the agent
- "tier": (optional) cost tier — "premium", "mid", or "low". Uses the model configured for that tier in Settings → Swarms → Model Tiers. Takes precedence over default model but is overridden by explicit "model".
- "model": (optional) explicit model to use, overrides tier setting
- "capabilities": (optional) array of strings describing what the agent can do
- "constraints": (optional) array of strings describing limitations

**Model Tiers** (configured in Settings → Swarms → Model Tiers):
- ⭐ **premium** — best quality for critical tasks (default: claude-sonnet-4)
- 🔹 **mid** — balanced quality/cost for general tasks (default: gpt-4o-mini)
- 💚 **low** — fast & cheap for simple tasks (default: gpt-3.5-turbo)
Each tier can be enabled/disabled and its model edited independently.
- Max agents per swarm (default 10)
- Max loops per agent (default 3)
- Execution timeout (default 300s)
- Token usage tracking (enabled by default)

example usage
~~~json
{
    "thoughts": [
        "This task needs multiple expert perspectives...",
        "I will use a concurrent swarm with 3 specialized agents"
    ],
    "tool_name": "swarm",
    "tool_args": {
        "task": "Analyze the pros and cons of microservices vs monolith architecture",
        "swarm_type": "concurrent",
        "agents": "[{\"name\": \"Backend Expert\", \"system_prompt\": \"You are a backend architecture expert.\", \"capabilities\": [\"system_design\", \"scalability\"], \"constraints\": [\"server_side_only\"]}, {\"name\": \"DevOps Expert\", \"system_prompt\": \"You are a DevOps engineer.\", \"capabilities\": [\"deployment\", \"monitoring\"], \"constraints\": [\"infrastructure_focus\"]}, {\"name\": \"Business Analyst\", \"system_prompt\": \"You are a business analyst.\", \"capabilities\": [\"cost_analysis\", \"team_productivity\"]}]"
    }
}
~~~

**when to use swarm vs call_subordinate:**
- use **swarm** when you need multiple agents with different expertise working on the same task simultaneously
- use **call_subordinate** when you need to delegate a single specific subtask to one agent
