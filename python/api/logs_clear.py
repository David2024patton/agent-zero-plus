"""Clear system and chat log history."""

import logging

from agent import AgentContext
from python.helpers.api import ApiHandler, Request, Response


class LogsClear(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        clear_system = input.get("system", True)
        clear_context = input.get("context", True)

        cleared = {"system": 0, "context": 0}

        if clear_system:
            # Clear MemoryHandler buffers if present
            for handler in logging.root.handlers:
                if hasattr(handler, "buffer"):
                    cleared["system"] += len(handler.buffer)
                    handler.buffer.clear()

        if clear_context:
            for ctx in AgentContext.all():
                # Clear chat history
                if hasattr(ctx, "chat_history"):
                    cleared["context"] += len(ctx.chat_history)
                    ctx.chat_history.clear()
                # Clear log entries
                log = getattr(ctx, "log", None)
                if log and hasattr(log, "logs"):
                    cleared["system"] += len(log.logs)
                    log.logs.clear()

        return {"ok": True, "cleared": cleared}
