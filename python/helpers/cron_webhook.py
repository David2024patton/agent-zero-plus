"""
Cron Webhook Delivery for Agent Zero
======================================
Allows scheduled task results to be delivered via webhooks.
Supports per-job webhook URLs with authentication tokens.

Inspired by OpenClaw's cron webhook delivery system.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent-zero.cron_webhook")

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@dataclass
class CronWebhookConfig:
    """Configuration for a cron job's webhook delivery."""
    job_id: str
    webhook_url: str
    auth_token: str = ""
    delivery_mode: str = "webhook"  # "webhook" | "announce" | "both"
    retry_count: int = 3
    retry_delay: float = 5.0
    timeout: float = 30.0
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class CronResult:
    """Result from a cron job execution."""
    job_id: str
    status: str  # "success" | "error" | "timeout"
    output: str = ""
    error: str = ""
    duration_ms: float = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }


class CronWebhookDelivery:
    """
    Delivers cron job results via HTTP webhooks.

    Usage:
        delivery = CronWebhookDelivery()
        delivery.register(CronWebhookConfig(
            job_id="daily_backup",
            webhook_url="https://n8n.example.com/webhook/backup",
            auth_token="secret123",
        ))
        await delivery.deliver(CronResult(
            job_id="daily_backup", status="success", output="Backed up 42 files"
        ))
    """

    def __init__(self):
        self._configs: Dict[str, CronWebhookConfig] = {}
        self._delivery_log: List[Dict[str, Any]] = []

    def register(self, config: CronWebhookConfig):
        """Register a webhook config for a cron job."""
        if not config.webhook_url.startswith(("http://", "https://")):
            logger.error(f"Invalid webhook URL for {config.job_id}: must be HTTP(S)")
            return
        self._configs[config.job_id] = config
        logger.info(f"Registered webhook for cron job: {config.job_id}")

    def unregister(self, job_id: str):
        """Remove webhook config for a cron job."""
        self._configs.pop(job_id, None)

    async def deliver(self, result: CronResult) -> bool:
        """Deliver a cron result via webhook."""
        config = self._configs.get(result.job_id)
        if not config:
            logger.debug(f"No webhook registered for job: {result.job_id}")
            return False

        if not HAS_HTTPX:
            logger.error("httpx not installed. Run: pip install httpx")
            return False

        payload = result.to_dict()
        headers = {"Content-Type": "application/json"}
        headers.update(config.headers)

        if config.auth_token:
            headers["Authorization"] = f"Bearer {config.auth_token}"

        for attempt in range(config.retry_count):
            try:
                async with httpx.AsyncClient(timeout=config.timeout) as client:
                    response = await client.post(
                        config.webhook_url,
                        json=payload,
                        headers=headers,
                    )

                log_entry = {
                    "job_id": result.job_id,
                    "attempt": attempt + 1,
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }
                self._delivery_log.append(log_entry)

                if response.status_code < 300:
                    logger.info(f"Webhook delivered for {result.job_id}: {response.status_code}")
                    return True
                else:
                    logger.warning(f"Webhook delivery got {response.status_code} for {result.job_id}")

            except httpx.TimeoutException:
                logger.warning(f"Webhook timeout for {result.job_id} (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"Webhook delivery error for {result.job_id}: {e}")

            if attempt < config.retry_count - 1:
                await asyncio.sleep(config.retry_delay * (attempt + 1))

        logger.error(f"Webhook delivery failed after {config.retry_count} attempts for {result.job_id}")
        return False

    def get_delivery_log(self, job_id: Optional[str] = None) -> List[Dict]:
        """Get delivery log, optionally filtered by job ID."""
        if job_id:
            return [e for e in self._delivery_log if e.get("job_id") == job_id]
        return list(self._delivery_log)

    def list_configs(self) -> Dict[str, dict]:
        """List all registered webhook configs (without tokens)."""
        return {
            job_id: {
                "webhook_url": cfg.webhook_url,
                "delivery_mode": cfg.delivery_mode,
                "has_auth": bool(cfg.auth_token),
            }
            for job_id, cfg in self._configs.items()
        }
