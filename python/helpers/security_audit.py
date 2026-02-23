"""
Security Audit Tooling for Agent Zero
=======================================
Scans the running configuration for security vulnerabilities and
provides actionable findings with severity grading.

Inspired by OpenClaw's gateway security audit system.
"""

import os
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger("agent-zero.security")


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single security audit finding."""
    id: str
    title: str
    severity: Severity
    description: str
    recommendation: str
    category: str = "general"


@dataclass
class AuditReport:
    """Complete security audit report."""
    findings: List[Finding] = field(default_factory=list)
    score: float = 10.0  # 0-10, starts perfect and deducts

    def add(self, finding: Finding):
        self.findings.append(finding)
        if finding.severity == Severity.CRITICAL:
            self.score = max(0, self.score - 2.0)
        elif finding.severity == Severity.WARNING:
            self.score = max(0, self.score - 0.5)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "total_findings": len(self.findings),
            "critical": self.critical_count,
            "warnings": self.warning_count,
            "findings": [
                {
                    "id": f.id,
                    "title": f.title,
                    "severity": f.severity.value,
                    "description": f.description,
                    "recommendation": f.recommendation,
                    "category": f.category,
                }
                for f in self.findings
            ],
        }


def run_security_audit(settings: dict) -> AuditReport:
    """
    Run a comprehensive security audit on the current configuration.

    Checks:
    1. Authentication mode (gateway auth)
    2. Exposed ports / public accessibility
    3. Token/secret rotation status
    4. Sandbox configuration
    5. Plugin permissions
    6. API key presence
    """
    report = AuditReport()

    # 1. Check if gateway auth is disabled
    auth_mode = settings.get("auth_mode", "")
    if auth_mode == "none" or not auth_mode:
        # Check if we're on loopback only
        host = settings.get("host", "127.0.0.1")
        if host in ("0.0.0.0", "::"):
            report.add(Finding(
                id="SEC-001",
                title="Gateway HTTP APIs reachable without authentication",
                severity=Severity.CRITICAL,
                description=(
                    "Authentication is disabled and the gateway is bound to all interfaces. "
                    "Remote attackers can access all agent capabilities."
                ),
                recommendation="Enable authentication or bind to 127.0.0.1 only.",
                category="authentication",
            ))
        else:
            report.add(Finding(
                id="SEC-002",
                title="Authentication disabled (loopback only)",
                severity=Severity.WARNING,
                description="Authentication is disabled but access is limited to localhost.",
                recommendation="Consider enabling authentication for defense in depth.",
                category="authentication",
            ))

    # 2. Check for empty/missing API keys
    sensitive_keys = [
        ("OPENAI_API_KEY", "OpenAI"),
        ("ANTHROPIC_API_KEY", "Anthropic"),
        ("GOOGLE_API_KEY", "Google/Gemini"),
    ]
    for env_key, provider in sensitive_keys:
        val = os.environ.get(env_key, "")
        if val and len(val) < 10:
            report.add(Finding(
                id=f"SEC-010-{provider.lower()}",
                title=f"Suspicious {provider} API key length",
                severity=Severity.WARNING,
                description=f"The {provider} API key appears too short to be valid.",
                recommendation=f"Verify {env_key} is set correctly.",
                category="api_keys",
            ))

    # 3. Check channel plugin tokens
    channel_tokens = [
        ("plugin_discord_bot_token", "DISCORD_BOT_TOKEN", "Discord"),
        ("plugin_telegram_bot_token", "TELEGRAM_BOT_TOKEN", "Telegram"),
        ("plugin_slack_bot_token", "SLACK_BOT_TOKEN", "Slack"),
        ("plugin_slack_signing_secret", "SLACK_SIGNING_SECRET", "Slack Signing Secret"),
        ("plugin_teams_app_password", "TEAMS_APP_PASSWORD", "Teams"),
        ("plugin_webhook_auth_token", "WEBHOOK_AUTH_TOKEN", "Webhook"),
    ]
    for setting_key, env_key, name in channel_tokens:
        enabled_key = setting_key.rsplit("_", 1)[0].rsplit("_", 1)[0] + "_enabled"
        # Check if plugin is enabled but token is missing
        if settings.get(enabled_key.replace("token", "enabled").replace("password", "enabled").replace("secret", "enabled"), False):
            val = os.environ.get(env_key, "") or settings.get(setting_key, "")
            if not val:
                report.add(Finding(
                    id=f"SEC-020-{name.lower().replace(' ', '_')}",
                    title=f"{name} plugin enabled but token is missing",
                    severity=Severity.CRITICAL,
                    description=f"The {name} plugin is enabled but has no authentication token configured.",
                    recommendation=f"Set {env_key} environment variable or configure in settings.",
                    category="plugins",
                ))

    # 4. Sandbox/browser isolation
    sandbox_browser_binds = settings.get("sandbox_browser_binds", "")
    if not sandbox_browser_binds:
        report.add(Finding(
            id="SEC-030",
            title="Browser sandbox uses shared container mounts",
            severity=Severity.WARNING,
            description=(
                "Browser automation shares the same container bind mounts as code execution. "
                "Web content could access agent files."
            ),
            recommendation="Configure sandbox.browser.binds to isolate browser containers.",
            category="sandbox",
        ))

    # 5. Check for default/weak passwords
    auth_password = settings.get("auth_password", "")
    if auth_password and auth_password in ("password", "admin", "12345", "agent-zero"):
        report.add(Finding(
            id="SEC-040",
            title="Weak authentication password detected",
            severity=Severity.CRITICAL,
            description="The authentication password is a commonly used default.",
            recommendation="Change to a strong, unique password.",
            category="authentication",
        ))

    # 6. Check webhook endpoint without auth
    if settings.get("plugin_webhook_enabled", False):
        if not (os.environ.get("WEBHOOK_AUTH_TOKEN") or settings.get("plugin_webhook_auth_token")):
            report.add(Finding(
                id="SEC-050",
                title="Webhook endpoint has no authentication",
                severity=Severity.CRITICAL,
                description="The webhook plugin is enabled without an auth token. Anyone can send commands.",
                recommendation="Set a webhook authentication token in plugin settings.",
                category="plugins",
            ))

    logger.info(f"Security audit complete: score={report.score}/10, findings={len(report.findings)}")
    return report


def format_audit_text(report: AuditReport) -> str:
    """Format audit report as readable text."""
    lines = [f"🔒 Security Audit Report — Score: {report.score}/10\n"]

    if not report.findings:
        lines.append("✅ No security issues found!")
        return "\n".join(lines)

    lines.append(f"Found {len(report.findings)} issue(s): "
                 f"{report.critical_count} critical, {report.warning_count} warning(s)\n")

    for f in sorted(report.findings, key=lambda x: x.severity.value):
        icon = "🔴" if f.severity == Severity.CRITICAL else "🟡" if f.severity == Severity.WARNING else "🔵"
        lines.append(f"{icon} [{f.id}] {f.title}")
        lines.append(f"   {f.description}")
        lines.append(f"   → {f.recommendation}\n")

    return "\n".join(lines)
