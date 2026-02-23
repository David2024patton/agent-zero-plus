"""Fetch available models from a provider's API endpoint."""

import json
import urllib.request
import urllib.error

from python.helpers.api import ApiHandler, Request, Response


# Known default API base URLs per provider
_PROVIDER_ENDPOINTS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "groq": "https://api.groq.com/openai/v1",
    "lmstudio": "http://localhost:1234/v1",
    "mistral": "https://api.mistral.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class ModelsList(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        provider = str(input.get("provider", "")).strip().lower()
        api_key = str(input.get("api_key", "")).strip()
        api_base = str(input.get("api_base", "")).strip()

        # Use default endpoint if not provided
        if not api_base:
            api_base = _PROVIDER_ENDPOINTS.get(provider, "")

        if not api_base:
            return {
                "ok": False,
                "error": f"No API endpoint known for provider '{provider}'. Please enter an API base URL.",
                "models": [],
            }

        # Normalize URL
        api_base = api_base.rstrip("/")

        # Ollama-specific: ensure /v1 suffix for OpenAI-compatible endpoint
        if provider == "ollama" and not api_base.endswith("/v1"):
            api_base = api_base + "/v1"

        # LM Studio-specific: ensure /v1 suffix
        if provider in ("lm_studio", "lmstudio") and not api_base.endswith("/v1"):
            api_base = api_base + "/v1"

        # Special handling for Google/Gemini API format
        if provider in ("google", "gemini"):
            return self._fetch_google_models(api_base, api_key, provider)

        # Standard OpenAI-compatible /models endpoint
        return self._fetch_openai_models(api_base, api_key, provider)

    def _fetch_google_models(
        self, api_base: str, api_key: str, provider: str
    ) -> dict:
        models_url = (
            f"{api_base}/models?key={api_key}" if api_key else f"{api_base}/models"
        )
        try:
            req = urllib.request.Request(
                models_url, headers={"User-Agent": "AgentZero/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            models = []
            for m in data.get("models", []):
                model_name = m.get("name", "")
                display_name = m.get("displayName", model_name)
                model_id = (
                    model_name.split("/")[-1] if "/" in model_name else model_name
                )
                if model_id and "generateContent" in str(
                    m.get("supportedGenerationMethods", [])
                ):
                    models.append({"id": model_id, "name": display_name})

            return {
                "ok": True,
                "models": sorted(models, key=lambda x: x["name"]),
                "provider": provider,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to fetch models from Google: {e}",
                "models": [],
            }

    def _fetch_openai_models(
        self, api_base: str, api_key: str, provider: str
    ) -> dict:
        models_url = f"{api_base}/models"
        try:
            headers: dict[str, str] = {"User-Agent": "AgentZero/1.0"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(models_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            models = []
            raw_models = (
                data.get("data", [])
                if isinstance(data.get("data"), list)
                else []
            )
            if not raw_models and isinstance(data.get("models"), list):
                raw_models = data["models"]

            for m in raw_models:
                if isinstance(m, dict):
                    mid = m.get("id", "")
                    mname = m.get("name") or m.get("id", "")
                    if mid:
                        models.append({"id": mid, "name": mname})
                elif isinstance(m, str):
                    models.append({"id": m, "name": m})

            return {
                "ok": True,
                "models": sorted(models, key=lambda x: x["name"]),
                "provider": provider,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to fetch models: {e}",
                "models": [],
            }
