"""
DM Pairing & Access Control for Discord
========================================
Implements OpenClaw's pairing-based DM access control:

1. When a new user DMs the bot, a pairing code is generated
2. The code is sent to the configured approval channel/owner
3. An authorized user approves by responding with the code
4. The DM sender is then allowed to chat

Security properties (matching OpenClaw):
  - 8-char codes, uppercase, no ambiguous chars (0, O, 1, I)
  - Codes expire after 1 hour
  - Max 3 pending requests per channel
  - Approved senders stored in allowlist file
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import random
import string
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger("agent-zero.plugins.discord.pairing")

# Characters for pairing codes — exclude 0, O, 1, I
_SAFE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class PairingRequest:
    """A pending pairing request."""
    code: str
    sender_id: str
    sender_name: str
    channel_id: str  # Where the approval notification was sent
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 3600  # 1 hour

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def remaining_minutes(self) -> int:
        return max(0, int((self.expires_at - time.time()) / 60))


class PairingManager:
    """
    Manages DM pairing codes and access allowlists.

    Policies:
      - "open"     — anyone can DM the bot
      - "owner"    — only the specified owner_user_id
      - "pairing"  — new users must be paired via code approval
      - "disabled" — DMs are completely disabled
    """

    def __init__(
        self,
        policy: str = "owner",
        owner_user_id: Optional[str] = None,
        data_dir: str = "data",
        max_pending_per_channel: int = 3,
        code_length: int = 8,
        code_ttl_seconds: int = 3600,
    ):
        self.policy = policy
        self.owner_user_id = owner_user_id
        self._data_dir = Path(data_dir)
        self._max_pending = max_pending_per_channel
        self._code_length = code_length
        self._code_ttl = code_ttl_seconds

        # State
        self._pending: Dict[str, PairingRequest] = {}  # code -> request
        self._allowlist: Set[str] = set()  # approved user IDs
        self._blocklist: Set[str] = set()  # blocked user IDs

        # Load persisted allowlist
        self._load_allowlist()

    # ─── Authorization ───

    def is_authorized(self, user_id: str) -> bool:
        """Check if a user is authorized to DM the bot."""
        if self.policy == "open":
            return True
        if self.policy == "disabled":
            return False
        if self.policy == "owner":
            return user_id == self.owner_user_id
        if self.policy == "pairing":
            # Owner is always authorized
            if user_id == self.owner_user_id:
                return True
            # Check allowlist
            if user_id in self._allowlist:
                return True
            # Check blocklist
            if user_id in self._blocklist:
                return False
            return False
        return False

    # ─── Pairing codes ───

    def generate_code(self) -> str:
        """Generate a random pairing code."""
        return "".join(random.choices(_SAFE_CHARS, k=self._code_length))

    def create_request(
        self,
        sender_id: str,
        sender_name: str,
        channel_id: str,
    ) -> Optional[PairingRequest]:
        """
        Create a pairing request for a new DM sender.

        Returns None if:
          - User is already authorized
          - User already has a pending request
          - Channel has reached max pending requests
        """
        # Already authorized?
        if self.is_authorized(sender_id):
            return None

        # Already has pending request?
        for req in self._pending.values():
            if req.sender_id == sender_id and not req.is_expired():
                return None  # Don't send duplicate requests

        # Clean expired requests first
        self._cleanup_expired()

        # Check channel limits
        channel_pending = sum(
            1 for r in self._pending.values()
            if r.channel_id == channel_id and not r.is_expired()
        )
        if channel_pending >= self._max_pending:
            logger.warning(
                f"Max pending pairing requests ({self._max_pending}) "
                f"for channel {channel_id}"
            )
            return None

        # Generate code and create request
        code = self.generate_code()
        while code in self._pending:
            code = self.generate_code()

        request = PairingRequest(
            code=code,
            sender_id=sender_id,
            sender_name=sender_name,
            channel_id=channel_id,
        )
        self._pending[code] = request
        logger.info(f"Pairing request created for {sender_name} ({sender_id})")
        return request

    def approve_code(self, code: str) -> Optional[PairingRequest]:
        """
        Approve a pairing code. Returns the request if valid.

        Side effects:
          - Adds sender to allowlist
          - Removes the pending request
          - Saves allowlist to disk
        """
        code = code.upper().strip()
        request = self._pending.get(code)
        if request is None:
            return None
        if request.is_expired():
            del self._pending[code]
            return None

        # Approve!
        self._allowlist.add(request.sender_id)
        del self._pending[code]
        self._save_allowlist()
        logger.info(
            f"Pairing approved: {request.sender_name} ({request.sender_id})"
        )
        return request

    def deny_code(self, code: str) -> Optional[PairingRequest]:
        """Deny a pairing code and optionally block the sender."""
        code = code.upper().strip()
        request = self._pending.pop(code, None)
        if request:
            logger.info(
                f"Pairing denied: {request.sender_name} ({request.sender_id})"
            )
        return request

    def revoke(self, user_id: str) -> bool:
        """Remove a user from the allowlist."""
        if user_id in self._allowlist:
            self._allowlist.discard(user_id)
            self._save_allowlist()
            logger.info(f"Access revoked for user {user_id}")
            return True
        return False

    def block(self, user_id: str):
        """Block a user from pairing."""
        self._blocklist.add(user_id)
        self.revoke(user_id)  # Also remove from allowlist
        logger.info(f"User {user_id} blocked")

    # ─── Query ───

    def list_pending(self) -> List[PairingRequest]:
        """List non-expired pending requests."""
        self._cleanup_expired()
        return [r for r in self._pending.values() if not r.is_expired()]

    def list_allowed(self) -> Set[str]:
        """List all allowed user IDs."""
        return set(self._allowlist)

    def list_blocked(self) -> Set[str]:
        """List all blocked user IDs."""
        return set(self._blocklist)

    # ─── Persistence ───

    def _allowlist_path(self) -> Path:
        return self._data_dir / "discord-allowFrom.json"

    def _load_allowlist(self):
        """Load allowlist from disk."""
        path = self._allowlist_path()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._allowlist = set(data.get("allowed", []))
                self._blocklist = set(data.get("blocked", []))
                logger.info(
                    f"Loaded {len(self._allowlist)} allowed, "
                    f"{len(self._blocklist)} blocked users"
                )
            except Exception as e:
                logger.error(f"Failed to load allowlist: {e}")

    def _save_allowlist(self):
        """Save allowlist to disk."""
        path = self._allowlist_path()
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "allowed": sorted(self._allowlist),
                "blocked": sorted(self._blocklist),
            }
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save allowlist: {e}")

    def _cleanup_expired(self):
        """Remove expired pending requests."""
        expired = [
            code for code, req in self._pending.items() if req.is_expired()
        ]
        for code in expired:
            del self._pending[code]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired pairing requests")

    # ─── Summary ───

    def summary(self) -> str:
        """Human-readable summary."""
        pending = self.list_pending()
        return (
            f"**DM Policy:** `{self.policy}`\n"
            f"**Allowed users:** {len(self._allowlist)}\n"
            f"**Blocked users:** {len(self._blocklist)}\n"
            f"**Pending requests:** {len(pending)}"
        )
