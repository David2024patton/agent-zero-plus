"""Swarm orchestration tool – spawns multi-agent workflows via the Swarms framework."""

import json
import asyncio
import time
from typing import Any

from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers import settings


# Lazy-import swarms to avoid import errors if not installed
def _import_swarms():
    # Ensure site-packages is in path (fixes import issue in some environments)
    import sys
    site_packages = '/opt/venv/lib/python3.13/site-packages'
    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)
    try:
        from swarms import Agent as SwarmAgent
        from swarms import SequentialWorkflow, ConcurrentWorkflow, MixtureOfAgents
        from swarms.structs.swarm_router import SwarmRouter, SwarmType
        return {
            "Agent": SwarmAgent,
            "SequentialWorkflow": SequentialWorkflow,
            "ConcurrentWorkflow": ConcurrentWorkflow,
            "MixtureOfAgents": MixtureOfAgents,
            "SwarmRouter": SwarmRouter,
            "SwarmType": SwarmType,
        }
    except Exception as e:
        raise ImportError(
            f"Failed to import swarms: {type(e).__name__}: {e}"
        ) from e


# Map user-facing swarm type names to SwarmType enum values
SWARM_TYPE_MAP = {
    "sequential": "SequentialWorkflow",
    "concurrent": "ConcurrentWorkflow",
    "mixture": "MixtureOfAgents",
    "group_chat": "GroupChat",
    "hierarchical": "HierarchicalSwarm",
    "dynamic": "DynamicSwarm",
}

DEFAULT_MODEL = "gpt-4o-mini"


def _get_swarm_settings() -> dict:
    """Read swarm-related settings from Agent Zero's settings store."""
    try:
        s = settings.get_settings()
        return {
            "enabled": s.get("swarm_enabled", True),
            "default_type": s.get("swarm_default_type", "sequential"),
            "default_model": s.get("swarm_default_model", ""),
            "max_agents": s.get("swarm_max_agents", 10),
            "max_loops": s.get("swarm_max_loops", 3),
            "timeout": s.get("swarm_timeout", 300),
            "track_tokens": s.get("swarm_track_tokens", True),
            "agent_manifests": s.get("swarm_agent_manifests", "[]"),
            "dynamic_reassignment": s.get("swarm_dynamic_reassignment", False),
            "output_format": s.get("swarm_output_format", "markdown"),
            "tiers": {
                "premium": {
                    "enabled": s.get("swarm_tier_premium_enabled", True),
                    "provider": s.get("swarm_tier_premium_provider", "openrouter"),
                    "name": s.get("swarm_tier_premium_name", "anthropic/claude-sonnet-4-20250514"),
                    "api_base": s.get("swarm_tier_premium_api_base", ""),
                },
                "mid": {
                    "enabled": s.get("swarm_tier_mid_enabled", True),
                    "provider": s.get("swarm_tier_mid_provider", "openrouter"),
                    "name": s.get("swarm_tier_mid_name", "openai/gpt-4o-mini"),
                    "api_base": s.get("swarm_tier_mid_api_base", ""),
                },
                "low": {
                    "enabled": s.get("swarm_tier_low_enabled", True),
                    "provider": s.get("swarm_tier_low_provider", "openrouter"),
                    "name": s.get("swarm_tier_low_name", "openai/gpt-3.5-turbo"),
                    "api_base": s.get("swarm_tier_low_api_base", ""),
                },
            },
        }
    except Exception:
        return {
            "enabled": True,
            "default_type": "sequential",
            "default_model": "",
            "max_agents": 10,
            "max_loops": 3,
            "timeout": 300,
            "track_tokens": True,
            "agent_manifests": "[]",
            "dynamic_reassignment": False,
            "output_format": "markdown",
            "tiers": {
                "premium": {"enabled": True, "provider": "openrouter", "name": "anthropic/claude-sonnet-4-20250514", "api_base": ""},
                "mid": {"enabled": True, "provider": "openrouter", "name": "openai/gpt-4o-mini", "api_base": ""},
                "low": {"enabled": True, "provider": "openrouter", "name": "openai/gpt-3.5-turbo", "api_base": ""},
            },
        }


def _load_manifests(manifests_json: str) -> dict[str, dict]:
    """Parse saved agent manifests into a lookup by name."""
    try:
        manifests = json.loads(manifests_json)
        if isinstance(manifests, list):
            return {m["name"]: m for m in manifests if isinstance(m, dict) and "name" in m}
    except Exception:
        pass
    return {}


class SwarmOrchestrator(Tool):

    def _swarm_log(self, heading: str, content: str = "", **kvps):
        """Log a SWARM-level orchestration event."""
        self.agent.context.log.log(
            type="swarm",
            heading=f"icon://hub {self.agent.agent_name}: {heading}",
            content=content,
            kvps=kvps if kvps else None,
        )

    async def execute(self, task="", swarm_type="", agents="[]", model="", **kwargs) -> Response:
        # Load settings
        cfg = _get_swarm_settings()

        # Master kill switch
        if not cfg["enabled"]:
            self._swarm_log("Swarm Blocked", "Swarm orchestration is disabled in settings.")
            return Response(
                message="Swarm orchestration is disabled in settings. Enable it in Settings → Swarms.",
                break_loop=False,
            )

        try:
            sw = _import_swarms()
        except Exception as e:
            self._swarm_log("Swarm Import Failed", str(e))
            return Response(message=f"Swarms import failed: {e}", break_loop=False)

        # Parse agent definitions
        try:
            if isinstance(agents, str):
                agent_defs = json.loads(agents)
            elif isinstance(agents, list):
                agent_defs = agents
            else:
                agent_defs = []
        except json.JSONDecodeError as e:
            return Response(
                message=f"Error parsing agents JSON: {e}. Provide a valid JSON array.",
                break_loop=False,
            )

        if not agent_defs:
            return Response(
                message="No agents defined. Provide at least one agent with 'name' and 'system_prompt' fields.",
                break_loop=False,
            )

        if not task:
            return Response(message="No task provided.", break_loop=False)

        # Enforce max agents limit
        max_agents = cfg["max_agents"]
        if len(agent_defs) > max_agents:
            return Response(
                message=f"Too many agents ({len(agent_defs)}). Maximum is {max_agents}. Reduce agents or increase limit in Settings → Swarms → Limits.",
                break_loop=False,
            )

        # Resolve swarm type: use provided or fall back to settings default
        swarm_type_lower = (swarm_type or cfg["default_type"]).lower().strip()

        # Log swarm start
        self._swarm_log(
            "Swarm Starting",
            f"Task: {task[:200]}",
            swarm_type=swarm_type_lower,
            agent_count=len(agent_defs),
            max_agents=cfg["max_agents"],
            timeout=cfg["timeout"],
        )

        # Resolve model – use provided, settings default, agent's chat model, or hardcoded default
        default_model = model or cfg["default_model"] or DEFAULT_MODEL
        try:
            if not model and not cfg["default_model"]:
                if hasattr(self.agent, "config") and hasattr(self.agent.config, "chat_model"):
                    cfg_model = self.agent.config.chat_model
                    if hasattr(cfg_model, "name") and cfg_model.name:
                        default_model = cfg_model.name
        except Exception:
            pass

        # Load saved manifests for merging with agent definitions
        manifests = _load_manifests(cfg["agent_manifests"])

        # Build Swarms Agent objects
        swarm_agents = []
        agent_metadata = []  # Track metadata for each agent
        max_loops_setting = cfg["max_loops"]

        for defn in agent_defs:
            agent_name = defn.get("name", f"Agent-{len(swarm_agents)+1}")

            # Merge with saved manifest if name matches
            if agent_name in manifests:
                manifest = manifests[agent_name]
                merged = {**manifest, **{k: v for k, v in defn.items() if v}}
            else:
                merged = defn

            system_prompt = merged.get("system_prompt", merged.get("prompt", "You are a helpful assistant."))

            # Resolve model: explicit model > tier > default
            agent_model = merged.get("model", "")
            tier = merged.get("tier", "").lower().strip()
            if not agent_model and tier and tier in cfg.get("tiers", {}):
                tier_cfg = cfg["tiers"][tier]
                if tier_cfg.get("enabled", False):
                    agent_model = tier_cfg["name"]
                    self._swarm_log("Tier Routing", f"Agent '{agent_name}' routed to tier '{tier}' → model '{agent_model}'")
                else:
                    self._swarm_log("Tier Disabled", f"Tier '{tier}' is disabled for agent '{agent_name}', falling back to default model.")
                    self.add_progress(f"Warning: Tier '{tier}' is disabled. Falling back to default model.")
            if not agent_model:
                agent_model = default_model
            max_loops = min(int(merged.get("max_loops", 1)), max_loops_setting)

            # Agent manifest fields
            capabilities = merged.get("capabilities", [])
            constraints = merged.get("constraints", [])

            # Append capability/constraint info to system prompt if present
            enhanced_prompt = system_prompt
            if capabilities:
                enhanced_prompt += f"\n\nYour capabilities: {', '.join(capabilities)}"
            if constraints:
                enhanced_prompt += f"\n\nYour constraints: {', '.join(constraints)}"

            try:
                swarm_agent = sw["Agent"](
                    agent_name=agent_name,
                    system_prompt=enhanced_prompt,
                    model_name=agent_model,
                    max_loops=max_loops,
                )
                swarm_agents.append(swarm_agent)
                agent_metadata.append({
                    "name": agent_name,
                    "model": agent_model,
                    "max_loops": max_loops,
                    "capabilities": capabilities,
                    "constraints": constraints,
                })
                self.add_progress(f"Created agent: {agent_name} (model: {agent_model}, loops: {max_loops})")
            except Exception as e:
                import traceback
                error_detail = f"Failed to create agent '{agent_name}' (model: {agent_model}): {type(e).__name__}: {e}\n{traceback.format_exc()}"
                self.add_progress(f"Warning: {error_detail}")
                if not hasattr(self, '_agent_errors'):
                    self._agent_errors = []
                self._agent_errors.append(error_detail)

        if not swarm_agents:
            error_details = getattr(self, '_agent_errors', [])
            error_text = "\n".join(error_details) if error_details else "No specific errors captured."
            return Response(
                message=f"Failed to create any Swarms agents. Errors:\n{error_text}",
                break_loop=False,
            )

        self.add_progress(f"Running {swarm_type_lower} swarm with {len(swarm_agents)} agents...")
        self._swarm_log(
            "Swarm Executing",
            f"Running {swarm_type_lower} workflow with {len(swarm_agents)} agents",
            agents=", ".join(m["name"] for m in agent_metadata),
        )

        # Execute with timeout
        timeout = cfg["timeout"]
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._run_swarm, sw, swarm_type_lower, swarm_agents, task, kwargs, cfg
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            self._swarm_log("Swarm Timeout", f"Execution timed out after {elapsed:.0f}s (limit: {timeout}s)", elapsed=f"{elapsed:.1f}s")
            return Response(
                message=f"Swarm execution timed out after {elapsed:.0f}s (limit: {timeout}s). Increase timeout in Settings → Swarms → Limits.",
                break_loop=False,
            )
        except Exception as e:
            self._swarm_log("Swarm Error", f"{type(e).__name__}: {e}")
            return Response(
                message=f"Swarm execution error: {type(e).__name__}: {e}",
                break_loop=False,
            )

        elapsed = time.time() - start_time

        # Log swarm completion
        self._swarm_log(
            "Swarm Completed",
            f"{swarm_type_lower} swarm finished with {len(swarm_agents)} agents",
            elapsed=f"{elapsed:.1f}s",
            agent_count=len(swarm_agents),
            swarm_type=swarm_type_lower,
        )

        # Format result based on output_format setting
        formatted = self._format_output(result, cfg["output_format"])

        # Build token usage report
        token_report = ""
        if cfg["track_tokens"]:
            token_report = self._build_token_report(swarm_agents, agent_metadata, elapsed)

        # Compose final response
        header = f"**Swarm ({swarm_type_lower})** completed with {len(swarm_agents)} agents in {elapsed:.1f}s"
        parts = [header, "", formatted]
        if token_report:
            parts.extend(["", "---", "", token_report])

        return Response(
            message="\n".join(parts),
            break_loop=False,
        )

    def _run_swarm(self, sw: dict, swarm_type: str, agents: list, task: str, extra_kwargs: dict, cfg: dict) -> Any:
        """Run the swarm synchronously (called via asyncio.to_thread)."""

        if swarm_type == "sequential":
            workflow = sw["SequentialWorkflow"](agents=agents)
            return workflow.run(task)

        elif swarm_type == "concurrent":
            workflow = sw["ConcurrentWorkflow"](agents=agents, max_loops=1)
            return workflow.run(task)

        elif swarm_type == "mixture":
            aggregator_def = extra_kwargs.get("aggregator", {})
            if isinstance(aggregator_def, str):
                try:
                    aggregator_def = json.loads(aggregator_def)
                except Exception:
                    aggregator_def = {}

            aggregator = sw["Agent"](
                agent_name=aggregator_def.get("name", "Aggregator"),
                system_prompt=aggregator_def.get(
                    "system_prompt",
                    "Synthesize and combine all agent outputs into a comprehensive, well-structured final answer."
                ),
                model_name=aggregator_def.get("model", agents[0].model_name if agents else DEFAULT_MODEL),
                max_loops=1,
            )
            moa = sw["MixtureOfAgents"](agents=agents, aggregator_agent=aggregator)
            return moa.run(task)

        elif swarm_type == "dynamic":
            # Dynamic swarm: agents process in sequence but can be re-ordered
            # based on intermediate results (simplified implementation)
            if cfg.get("dynamic_reassignment", False):
                # Run each agent, let the last output inform the next agent's context
                results = []
                running_context = task
                for agent in agents:
                    result = agent.run(running_context)
                    results.append({"agent": agent.agent_name, "output": str(result)})
                    # Feed output forward as enriched context
                    running_context = f"Previous analysis:\n{result}\n\nOriginal task: {task}"
                return results
            else:
                # Without reassignment, dynamic acts like sequential
                workflow = sw["SequentialWorkflow"](agents=agents)
                return workflow.run(task)

        elif swarm_type in ("group_chat", "hierarchical"):
            type_map = {
                "group_chat": "GroupChat",
                "hierarchical": "HierarchicalSwarm",
            }
            router = sw["SwarmRouter"](
                swarm_type=type_map[swarm_type],
                agents=agents,
            )
            return router.run(task)

        else:
            try:
                router = sw["SwarmRouter"](
                    swarm_type=swarm_type,
                    agents=agents,
                )
                return router.run(task)
            except Exception:
                raise ValueError(
                    f"Unknown swarm_type: '{swarm_type}'. "
                    f"Supported types: sequential, concurrent, mixture, dynamic, group_chat, hierarchical"
                )

    def _format_output(self, result: Any, output_format: str) -> str:
        """Format swarm output based on settings."""
        if output_format == "json":
            if isinstance(result, (dict, list)):
                return "```json\n" + json.dumps(result, indent=2, default=str) + "\n```"
            else:
                return json.dumps({"result": str(result)}, indent=2)

        elif output_format == "plain":
            if isinstance(result, dict):
                return "\n".join(f"{k}: {v}" for k, v in result.items())
            elif isinstance(result, list):
                return "\n\n".join(str(r) for r in result)
            else:
                return str(result)

        else:  # markdown (default)
            if isinstance(result, dict):
                parts = []
                for k, v in result.items():
                    parts.append(f"### {k}\n{v}")
                return "\n\n".join(parts)
            elif isinstance(result, list):
                parts = []
                for i, r in enumerate(result):
                    if isinstance(r, dict):
                        agent_name = r.get("agent", f"Agent {i+1}")
                        output = r.get("output", str(r))
                        parts.append(f"### {agent_name}\n{output}")
                    else:
                        parts.append(f"### Result {i+1}\n{r}")
                return "\n\n---\n\n".join(parts)
            else:
                return str(result)

    def _build_token_report(self, agents: list, metadata: list, elapsed: float) -> str:
        """Build a token usage summary report."""
        lines = ["**📊 Token Usage Report**", ""]
        total_input = 0
        total_output = 0

        for i, agent in enumerate(agents):
            name = metadata[i]["name"] if i < len(metadata) else f"Agent {i+1}"
            model = metadata[i]["model"] if i < len(metadata) else "unknown"

            # Try to get token counts from the agent (swarms may expose these)
            input_tokens = 0
            output_tokens = 0
            try:
                if hasattr(agent, "total_input_tokens"):
                    input_tokens = agent.total_input_tokens or 0
                if hasattr(agent, "total_output_tokens"):
                    output_tokens = agent.total_output_tokens or 0
            except Exception:
                pass

            total_input += input_tokens
            total_output += output_tokens
            if input_tokens or output_tokens:
                lines.append(f"| {name} | {model} | {input_tokens:,} in / {output_tokens:,} out |")

        if total_input or total_output:
            lines.insert(2, "| Agent | Model | Tokens |")
            lines.insert(3, "|-------|-------|--------|")
            lines.append(f"| **Total** | | **{total_input:,} in / {total_output:,} out** |")
        else:
            lines.append("_Token counts not available from swarm agents._")

        lines.append(f"\n⏱️ Execution time: {elapsed:.1f}s")
        return "\n".join(lines)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="swarm",
            heading=f"icon://hub {self.agent.agent_name}: Swarm Orchestration ({self.args.get('swarm_type', 'sequential')})",
            content="",
            kvps=self.args,
        )
