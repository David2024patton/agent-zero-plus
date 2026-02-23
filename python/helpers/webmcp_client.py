"""
WebMCP Client for Agent Zero
==============================
Server-side coordinator for Google's WebMCP (Web Model Context Protocol).
Calls the client-side JS bridge (`webmcp_bridge.js`) via Playwright
page.evaluate() to discover and invoke structured tools.

WebMCP allows websites to expose functions via `navigator.modelContext`,
replacing fragile DOM scraping with direct API calls (67% less compute).
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent-zero.webmcp")


@dataclass
class WebMCPTool:
    """A single tool exposed by a page via WebMCP."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    source: str = "imperative"  # "imperative" | "declarative"
    manifest_url: str = ""


@dataclass  
class WebMCPResult:
    """Result from calling a WebMCP tool."""
    success: bool
    result: Any = None
    error: Optional[str] = None


async def check_status(page) -> dict:
    """
    Quick check if WebMCP is available on the current page.
    Returns status dict with availability flags.
    """
    try:
        status = await page.evaluate("window.__A0_webmcp_status ? window.__A0_webmcp_status() : null")
        if status is None:
            return {"available": False, "imperative": False, "declarative": False}
        return status
    except Exception as e:
        logger.debug(f"WebMCP status check failed: {e}")
        return {"available": False, "imperative": False, "declarative": False}


async def discover_tools(page) -> List[WebMCPTool]:
    """
    Discover all WebMCP tools available on the current page.
    Executes the JS bridge's __A0_webmcp_discover() function.
    
    Returns list of WebMCPTool objects.
    """
    try:
        raw_tools = await page.evaluate(
            "window.__A0_webmcp_discover ? window.__A0_webmcp_discover() : []"
        )
        if not raw_tools or not isinstance(raw_tools, list):
            return []

        tools = []
        for t in raw_tools:
            tools.append(WebMCPTool(
                name=t.get("name", "unknown"),
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
                source=t.get("source", "imperative"),
                manifest_url=t.get("manifestUrl", ""),
            ))

        if tools:
            logger.info(f"WebMCP: Discovered {len(tools)} tools on page")
            for tool in tools:
                logger.debug(f"  - {tool.name}: {tool.description} ({tool.source})")

        return tools

    except Exception as e:
        logger.debug(f"WebMCP tool discovery failed: {e}")
        return []


async def call_tool(page, tool_name: str, params: dict) -> WebMCPResult:
    """
    Call a WebMCP tool by name with the given parameters.
    Executes the JS bridge's __A0_webmcp_call() function.
    
    Returns WebMCPResult with success/error status.
    """
    try:
        result = await page.evaluate(
            """([name, params]) => {
                if (window.__A0_webmcp_call) {
                    return window.__A0_webmcp_call(name, params);
                }
                return {success: false, result: null, error: 'WebMCP bridge not loaded'};
            }""",
            [tool_name, params]
        )

        return WebMCPResult(
            success=result.get("success", False),
            result=result.get("result"),
            error=result.get("error"),
        )

    except Exception as e:
        logger.error(f"WebMCP call_tool({tool_name}) failed: {e}")
        return WebMCPResult(success=False, error=str(e))


def format_tools_for_prompt(tools: List[WebMCPTool]) -> str:
    """
    Format discovered WebMCP tools as a prompt section for the LLM.
    This tells the browser agent what structured tools are available.
    """
    if not tools:
        return ""

    lines = [
        "\n## 🔧 WebMCP Tools Available on This Page",
        "The following structured tools are available via WebMCP.",
        "Use the \"Use WebMCP tool\" action to call them instead of clicking/typing.\n",
    ]

    for tool in tools:
        lines.append(f"### `{tool.name}`")
        if tool.description:
            lines.append(f"{tool.description}")
        if tool.parameters:
            lines.append("**Parameters:**")
            if isinstance(tool.parameters, dict):
                props = tool.parameters.get("properties", tool.parameters)
                for pname, pinfo in props.items():
                    ptype = pinfo.get("type", "any") if isinstance(pinfo, dict) else "any"
                    pdesc = pinfo.get("description", "") if isinstance(pinfo, dict) else ""
                    lines.append(f"- `{pname}` ({ptype}): {pdesc}")
        lines.append("")

    return "\n".join(lines)
