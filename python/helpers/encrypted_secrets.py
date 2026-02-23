"""
Encrypted Secrets Helper for Agent Zero
=========================================
Provides AES-256-GCM encryption for API keys at rest.
Secrets are decrypted only at runtime via a master key.

Usage:
    from python.helpers.encrypted_secrets import EncryptedSecretStore

    store = EncryptedSecretStore(master_key="my-secret-key")
    store.set("OPENAI_API_KEY", "sk-...")
    value = store.get("OPENAI_API_KEY")
"""

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("agent-zero.encrypted_secrets")

# Try to import cryptography for AES-256-GCM
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class EncryptedSecretStore:
    """
    AES-256-GCM encrypted secret storage.

    Secrets are stored in a JSON file with encrypted values.
    Each value gets a unique nonce for GCM mode.
    """

    def __init__(
        self,
        master_key: str = "",
        store_path: str = "",
    ):
        """
        Initialize the encrypted store.

        Args:
            master_key: Master key for encryption. Falls back to
                        AGENT_ZERO_MASTER_KEY env var.
            store_path: Path to the encrypted store file.
        """
        self._master_key = master_key or os.environ.get("AGENT_ZERO_MASTER_KEY", "")
        self._store_path = store_path or os.path.join(
            os.environ.get("A0_DATA_DIR", "usr"),
            ".encrypted_secrets.json",
        )
        self._cache: Dict[str, str] = {}

    def _derive_key(self) -> bytes:
        """Derive a 32-byte AES key from the master key using SHA-256."""
        if not self._master_key:
            raise ValueError("Master key not configured. Set AGENT_ZERO_MASTER_KEY env var.")
        return hashlib.sha256(self._master_key.encode()).digest()

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string value, returns base64-encoded nonce+ciphertext."""
        if not HAS_CRYPTO:
            logger.warning("cryptography not installed, storing plaintext")
            return plaintext

        key = self._derive_key()
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        # Store as base64: nonce (12 bytes) + ciphertext
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode()

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt a base64-encoded nonce+ciphertext string."""
        if not HAS_CRYPTO:
            return encrypted

        key = self._derive_key()
        combined = base64.b64decode(encrypted)
        nonce = combined[:12]
        ciphertext = combined[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    def _load_store(self) -> Dict[str, str]:
        """Load the encrypted store from disk."""
        try:
            if os.path.exists(self._store_path):
                with open(self._store_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load encrypted store: {e}")
        return {}

    def _save_store(self, store: Dict[str, str]):
        """Save the encrypted store to disk."""
        try:
            Path(self._store_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._store_path, "w") as f:
                json.dump(store, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save encrypted store: {e}")

    def set(self, key: str, value: str):
        """Encrypt and store a secret."""
        store = self._load_store()
        store[key] = self._encrypt(value)
        self._save_store(store)
        self._cache[key] = value

    def get(self, key: str) -> Optional[str]:
        """Retrieve and decrypt a secret."""
        # Check cache first
        if key in self._cache:
            return self._cache[key]

        store = self._load_store()
        encrypted = store.get(key)
        if encrypted is None:
            return None

        try:
            value = self._decrypt(encrypted)
            self._cache[key] = value
            return value
        except Exception as e:
            logger.error(f"Failed to decrypt secret '{key}': {e}")
            return None

    def delete(self, key: str):
        """Remove a secret from the store."""
        store = self._load_store()
        store.pop(key, None)
        self._save_store(store)
        self._cache.pop(key, None)

    def list_keys(self) -> list:
        """List all stored secret keys (not values)."""
        return list(self._load_store().keys())

    def has(self, key: str) -> bool:
        """Check if a secret exists."""
        return key in self._load_store()
