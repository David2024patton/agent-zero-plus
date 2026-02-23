"""Fetch system and chat logs for the logs viewer."""

import logging
import logging.handlers
import time
import traceback

from agent import AgentContext
from python.helpers.api import ApiHandler, Request, Response


# Color/severity hints for the frontend
LEVEL_MAP = {
    "error": "ERROR",
    "warning": "WARN",
    "hint": "INFO",
    "info": "INFO",
    "progress": "INFO",
    "agent": "INFO",
    "browser": "INFO",
    "code_exe": "INFO",
    "subagent": "INFO",
    "swarm": "INFO",
    "tool": "INFO",
    "mcp": "INFO",
    "http": "INFO",
    "util": "DEBUG",
    "user": "INFO",
    "response": "INFO",
    "input": "INFO",
}


class LogsGet(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        max_lines = int(input.get("max_lines", 200) or 200)
        category_filter = input.get("category")  # optional filter

        # Collect chat/agent logs from all agent contexts via ctx.log.logs
        context_logs: list[dict] = []
        sys_logs: list[dict] = []
        categories: dict[str, int] = {}

        try:
            for ctx in AgentContext.all():
                log_obj = getattr(ctx, "log", None)
                if not log_obj:
                    continue

                # Access logs safely - the Log class uses locks internally
                raw_logs = []
                try:
                    if hasattr(log_obj, "_lock"):
                        with log_obj._lock:
                            raw_logs = list(log_obj.logs)
                    elif hasattr(log_obj, "logs"):
                        raw_logs = list(log_obj.logs)
                except Exception:
                    continue

                for item in raw_logs[-max_lines:]:
                    try:
                        item_type = getattr(item, "type", "info") or "info"
                        heading = getattr(item, "heading", "") or ""
                        content = getattr(item, "content", "") or ""
                        ts = getattr(item, "timestamp", 0) or 0
                        agentno = getattr(item, "agentno", 0) or 0
                        item_kvps = getattr(item, "kvps", None)

                        type_str = str(item_type).lower()

                        # Chat-style logs (user input and agent responses)
                        if type_str in ("user", "response", "input"):
                            msg_type = "user" if type_str in ("user", "input") else "response"
                            display_content = content[:4000] if content else heading[:4000] if heading else ""
                            context_logs.append({
                                "type": msg_type,
                                "content": display_content,
                                "heading": heading[:200] if heading else "",
                                "context": ctx.id,
                                "context_name": getattr(ctx, "name", "") or ctx.id[:8],
                                "timestamp": ts,
                            })
                        else:
                            # Reclassify agent logs by hierarchy
                            cat = type_str
                            if type_str == "agent" and agentno > 0:
                                cat = "subagent"  # sub-agents get their own category
                            level = LEVEL_MAP.get(cat, "INFO")

                            # Build detailed message with agent number
                            prefix = f"A{agentno}" if agentno > 0 else "A0"
                            if heading and content:
                                msg = f"{heading}: {content[:800]}"
                            elif heading:
                                msg = heading
                            elif content:
                                msg = content[:800]
                            else:
                                msg = f"({type_str})"

                            # Build enriched detail from kvps
                            kvps_detail = _build_kvps_detail(item_kvps)

                            sys_entry = {
                                "timestamp": ts,
                                "category": cat,
                                "level": level,
                                "agent": prefix,
                                "type": type_str,
                                "message": msg + kvps_detail,
                            }
                            if not category_filter or cat == category_filter:
                                sys_logs.append(sys_entry)
                            categories[cat] = categories.get(cat, 0) + 1

                    except Exception:
                        continue

        except Exception as e:
            # If collecting from contexts fails, add error to sys_logs
            sys_logs.append({
                "timestamp": time.time(),
                "category": "error",
                "level": "ERROR",
                "agent": "SYS",
                "type": "error",
                "message": f"Error collecting agent logs: {str(e)}",
            })

        # Also collect system logs from Python's logging MemoryHandler if available
        try:
            for handler in logging.root.handlers:
                if hasattr(handler, "buffer"):
                    for record in list(handler.buffer)[-max_lines:]:
                        cat = getattr(record, "category", "system")
                        entry = {
                            "timestamp": record.created,
                            "category": cat,
                            "level": record.levelname,
                            "agent": "SYS",
                            "type": cat,
                            "message": handler.format(record) if hasattr(handler, "format") else record.getMessage(),
                        }
                        if not category_filter or cat == category_filter:
                            sys_logs.append(entry)
                        categories[cat] = categories.get(cat, 0) + 1
        except Exception:
            pass

        # Collect uvicorn access logs (HTTP requests) — always on
        try:
            uvicorn_logger = logging.getLogger("uvicorn.access")
            for handler in uvicorn_logger.handlers:
                if hasattr(handler, "buffer"):
                    for record in list(handler.buffer)[-max_lines:]:
                        entry = {
                            "timestamp": record.created,
                            "category": "http",
                            "level": record.levelname,
                            "agent": "HTTP",
                            "type": "http",
                            "message": handler.format(record) if hasattr(handler, "format") else record.getMessage(),
                        }
                        if not category_filter or "http" == category_filter:
                            sys_logs.append(entry)
                        categories["http"] = categories.get("http", 0) + 1
            # Also check if uvicorn.access records propagated to root logger
            # and collect from uvicorn's default stderr handler output
            if not any(hasattr(h, "buffer") for h in uvicorn_logger.handlers):
                # Install a memory handler on uvicorn.access for future requests
                _ensure_uvicorn_memory_handler(uvicorn_logger, max_lines)
        except Exception:
            pass

        # Sort all logs by timestamp
        sys_logs.sort(key=lambda x: x.get("timestamp", 0))
        context_logs.sort(key=lambda x: x.get("timestamp", 0))

        # Build formatted file-style logs with granular type labels
        file_log_lines: list[str] = []
        for entry in sys_logs[-max_lines:]:
            try:
                ts_val = entry.get("timestamp", 0) or 0
                if ts_val > 0:
                    ts = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(ts_val)
                    )
                else:
                    ts = "----"
                cat = str(entry.get("category", "system")).upper().ljust(10)
                lvl = str(entry.get("level", "INFO")).upper().ljust(5)
                agent = str(entry.get("agent", "SYS")).ljust(4)
                file_log_lines.append(f"[{ts}] [{cat}] [{lvl}] [{agent}] {entry.get('message', '')}")
            except Exception:
                continue

        # Detect channels from active agent contexts
        channels: dict[str, int] = {}
        try:
            for ctx in AgentContext.all():
                ctx_id = getattr(ctx, "id", "")
                ctx_name = getattr(ctx, "name", "")
                channel_name = _detect_channel(ctx_id, ctx_name)
                if channel_name:
                    channels[channel_name] = channels.get(channel_name, 0) + 1
        except Exception:
            pass

        return {
            "ok": True,
            "file_logs": "\n\n".join(file_log_lines) if file_log_lines else "",
            "context_logs": context_logs[-max_lines:],
            "handler_logs": [],
            "categories": categories,
            "channels": channels,
            "total_system_logs": len(sys_logs),
            "total_context_logs": len(context_logs),
        }


# Keys to render prominently or skip entirely
_PROMINENT_KEYS = {"thoughts", "headline", "model", "browser_model", "subordinate_model",
                   "tool_name", "step", "status", "result", "task", "url",
                   "final_url", "page_title", "answer"}
_SKIP_KEYS = {"tool_args", "text", "reasoning", "screenshot", "update_progress"}


def _build_kvps_detail(item_kvps: dict | None) -> str:
    """Build a human-readable detail block from log kvps.
    
    Renders thoughts as a bulleted narrative, surfaces key metadata,
    and skips raw data blobs that clutter the log output.
    """
    if not item_kvps:
        return ""

    parts: list[str] = []

    # 1. Thoughts — the LLM's reasoning process (most important for readability)
    thoughts = item_kvps.get("thoughts")
    if thoughts:
        if isinstance(thoughts, list):
            thought_lines = [f"    - {t}" for t in thoughts[:10]]  # cap at 10
            parts.append("  💭 Thoughts:")
            parts.extend(thought_lines)
        elif isinstance(thoughts, str) and thoughts.strip():
            parts.append(f"  💭 Thoughts: {thoughts[:500]}")

    # 2. Headline — the agent's one-line summary
    headline = item_kvps.get("headline")
    if headline and isinstance(headline, str) and headline.strip():
        parts.append(f"  📌 {headline}")

    # 3. Key metadata in clean format
    for key in ("model", "browser_model", "subordinate_model", "step",
                "tool_name", "status", "task", "result", "url", "final_url",
                "page_title", "answer"):
        val = item_kvps.get(key)
        if val is not None:
            val_str = str(val).strip()
            if val_str:
                parts.append(f"  {key}: {val_str[:300]}")

    # 4. Any remaining keys not in prominent or skip sets
    for k, v in item_kvps.items():
        if k.startswith("_") or k in _PROMINENT_KEYS or k in _SKIP_KEYS:
            continue
        val_str = str(v)[:200] if v is not None else ""
        if val_str:
            parts.append(f"  {k}: {val_str}")

    if parts:
        return "\n" + "\n".join(parts)
    return ""


def _ensure_uvicorn_memory_handler(logger: logging.Logger, capacity: int = 500):
    """Install a MemoryHandler on the uvicorn.access logger so HTTP requests
    are captured for the Logs viewer. This is a one-time setup."""
    # Check if we already installed one
    for h in logger.handlers:
        if isinstance(h, logging.handlers.MemoryHandler):
            return
    import logging.handlers as _lh  # ensure available
    mem_handler = logging.handlers.MemoryHandler(capacity=capacity, flushLevel=logging.CRITICAL + 1)
    mem_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(mem_handler)
    logger.setLevel(logging.INFO)


def _detect_channel(ctx_id: str, ctx_name: str) -> str:
    """Detect which communication channel a context belongs to from its id/name."""
    combined = (str(ctx_id) + " " + str(ctx_name)).lower()
    for ch in ["email", "discord", "telegram", "slack", "teams", "whatsapp", "webhook", "matrix"]:
        if ch in combined:
            return ch
    return ""
