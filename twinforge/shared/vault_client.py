"""
TWINFORGE Vault Client
HashiCorp Vault KV v2 wrapper for secrets management.
"""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class VaultClient:
    """Async client for reading/writing secrets from HashiCorp Vault KV v2."""

    def __init__(
        self,
        vault_url: str = "http://localhost:8200",
        token: str = "",
        mount_path: str = "secret",
    ) -> None:
        self.vault_url = vault_url.rstrip("/")
        self.token = token
        self.mount_path = mount_path
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.vault_url,
            headers={"X-Vault-Token": self.token},
            timeout=10.0,
        )
        logger.info("Vault client connected to %s", self.vault_url)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
        logger.info("Vault client disconnected")

    async def read_secret(self, path: str) -> Optional[dict[str, Any]]:
        """Read a secret from Vault KV v2."""
        if not self._client:
            logger.warning("Vault client not connected")
            return None
        try:
            url = f"/v1/{self.mount_path}/data/{path}"
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("data")
        except Exception as e:
            logger.error("Failed to read secret at %s: %s", path, e)
            return None

    async def write_secret(self, path: str, data: dict[str, Any]) -> bool:
        """Write a secret to Vault KV v2."""
        if not self._client:
            logger.warning("Vault client not connected")
            return False
        try:
            url = f"/v1/{self.mount_path}/data/{path}"
            resp = await self._client.post(url, json={"data": data})
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Failed to write secret at %s: %s", path, e)
            return False
