"""Provider backends – unified async interface to LLM APIs."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("foundrygate.providers")


@dataclass
class ProviderHealth:
    """Tracks health state for a single provider."""

    name: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_check: float = 0.0
    last_error: str = ""
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def record_success(self, latency_ms: float) -> None:
        self.healthy = True
        self.consecutive_failures = 0
        self.last_check = time.time()
        self.last_error = ""
        self._latencies.append(latency_ms)
        if len(self._latencies) > 20:
            self._latencies = self._latencies[-20:]
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self, error: str, max_failures: int = 3) -> None:
        self.consecutive_failures += 1
        self.last_check = time.time()
        self.last_error = error
        if self.consecutive_failures >= max_failures:
            self.healthy = False
            logger.warning(
                "Provider %s marked unhealthy after %d failures: %s",
                self.name,
                self.consecutive_failures,
                error,
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "consecutive_failures": self.consecutive_failures,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "last_error": self.last_error,
        }


class ProviderBackend:
    """Calls an OpenAI-compatible or Google GenAI endpoint."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.contract = cfg.get("contract", "generic")
        self.backend_type = cfg.get("backend", "openai-compat")
        self.base_url = cfg["base_url"].rstrip("/")
        self.api_key = cfg.get("api_key", "")
        self.model = cfg["model"]
        self.max_tokens = cfg.get("max_tokens", 8000)
        self.tier = cfg.get("tier", "default")
        self.capabilities = dict(cfg.get("capabilities", {}))
        self.context_window = cfg.get("context_window")
        self.limits = dict(cfg.get("limits", {}))
        self.cache = dict(cfg.get("cache", {}))
        self.health = ProviderHealth(name=name)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=20),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def probe_health(self, timeout_seconds: float = 10.0) -> bool:
        """Probe a provider without sending a completion request.

        For OpenAI-compatible providers this uses GET /models. For Google GenAI,
        which does not expose a compatible models listing here, probing is skipped.
        """
        if self.backend_type == "google-genai":
            return self.health.healthy

        url = f"{self.base_url}/models"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        t0 = time.time()
        try:
            resp = await self._client.get(url, headers=headers, timeout=timeout_seconds)
            latency = (time.time() - t0) * 1000
            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"Probe HTTP {resp.status_code}: {error_text}")
                return False

            self.health.record_success(latency)
            return True
        except httpx.TimeoutException as e:
            self.health.record_failure(f"Probe timeout: {e}")
            return False
        except httpx.ConnectError as e:
            self.health.record_failure(f"Probe connection error: {e}")
            return False

    async def generate_image(
        self,
        prompt: str,
        *,
        model_override: str | None = None,
        n: int = 1,
        size: str | None = None,
        quality: str | None = None,
        response_format: str | None = None,
        style: str | None = None,
        background: str | None = None,
        user: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict:
        """Send an OpenAI-compatible image generation request."""
        if self.backend_type != "openai-compat":
            raise ProviderError(
                self.name,
                0,
                f"Image generation is not implemented for backend '{self.backend_type}'",
            )

        model = model_override or self.model
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
        }
        if size:
            body["size"] = size
        if quality:
            body["quality"] = quality
        if response_format:
            body["response_format"] = response_format
        if style:
            body["style"] = style
        if background:
            body["background"] = background
        if user:
            body["user"] = user
        if extra_body:
            body.update(extra_body)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://foundrygate.local"
            headers["X-Title"] = "FoundryGate"

        url = f"{self.base_url}/images/generations"
        t0 = time.time()

        try:
            resp = await self._client.post(url, json=body, headers=headers)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            data = resp.json()
            data["_foundrygate"] = {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "modality": "image_generation",
            }
            return data

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e
        except httpx.ConnectError as e:
            self.health.record_failure(f"Connection error: {e}")
            raise ProviderError(self.name, 0, f"Connection error: {e}") from e

    # ── OpenAI-compatible completion ───────────────────────────

    async def complete(
        self,
        messages: list[dict],
        *,
        model_override: str | None = None,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        extra_body: dict | None = None,
    ) -> dict | AsyncIterator[bytes]:
        """Send a chat completion request. Returns the full JSON response."""

        model = model_override or self.model
        t0 = time.time()

        if self.backend_type == "google-genai":
            return await self._complete_google(
                messages,
                model=model,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # OpenAI-compatible path (DeepSeek, OpenRouter, etc.)
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = tools
        if stream:
            body["stream"] = True
        if extra_body:
            body.update(extra_body)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter wants extra headers
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://foundrygate.local"
            headers["X-Title"] = "FoundryGate"

        url = f"{self.base_url}/chat/completions"

        try:
            if stream:
                return self._stream_response(url, headers, body, t0)

            resp = await self._client.post(url, json=body, headers=headers)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            data = resp.json()

            # Extract cache metrics from DeepSeek/OpenAI responses
            usage = data.get("usage", {})
            cache_hit = usage.get("prompt_cache_hit_tokens", 0)
            cache_miss = usage.get("prompt_cache_miss_tokens", 0)

            # Tag the response with routing metadata
            data["_foundrygate"] = {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "cache_hit_tokens": cache_hit,
                "cache_miss_tokens": cache_miss,
            }
            return data

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e
        except httpx.ConnectError as e:
            self.health.record_failure(f"Connection error: {e}")
            raise ProviderError(self.name, 0, f"Connection error: {e}") from e

    async def _stream_response(
        self, url: str, headers: dict, body: dict, t0: float
    ) -> AsyncIterator[bytes]:
        """Yield SSE chunks for streaming responses."""
        async with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                error_text = await resp.aread()
                self.health.record_failure(f"HTTP {resp.status_code}")
                raise ProviderError(self.name, resp.status_code, error_text.decode()[:500])

            first_chunk = True
            async for line in resp.aiter_lines():
                if first_chunk:
                    self.health.record_success((time.time() - t0) * 1000)
                    first_chunk = False
                yield (line + "\n").encode()

    # ── Google GenAI path ──────────────────────────────────────

    async def _complete_google(
        self,
        messages: list[dict],
        model: str,
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict:
        """Convert OpenAI format → Google GenAI format → back."""

        # Convert messages to Google format.
        # Google rejects payloads where parts[*].text is null/None, so we
        # coerce content=None (valid in OpenAI tool/assistant messages) → "".
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content") or ""  # coerce None → ""
            if isinstance(text, list):
                # Multimodal content array → flatten to plain text for Gemini
                text = " ".join(part.get("text") or "" for part in text if isinstance(part, dict))
            if role == "system":
                system_instruction = text
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": text}]})
            else:
                contents.append({"role": "user", "parts": [{"text": text}]})

        body: dict[str, Any] = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        gen_config: dict[str, Any] = {}
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens
        if temperature is not None:
            gen_config["temperature"] = temperature
        if gen_config:
            body["generationConfig"] = gen_config

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        t0 = time.time()

        try:
            resp = await self._client.post(url, json=body)
            latency = (time.time() - t0) * 1000

            if resp.status_code >= 400:
                error_text = resp.text[:500]
                self.health.record_failure(f"HTTP {resp.status_code}: {error_text}")
                raise ProviderError(self.name, resp.status_code, error_text)

            self.health.record_success(latency)
            google_data = resp.json()

            # Convert Google response → OpenAI format
            return self._google_to_openai(google_data, model, latency)

        except httpx.TimeoutException as e:
            self.health.record_failure(f"Timeout: {e}")
            raise ProviderError(self.name, 0, f"Timeout: {e}") from e

    def _google_to_openai(self, data: dict, model: str, latency: float) -> dict:
        """Convert Google GenAI response to OpenAI chat completion format."""
        candidates = data.get("candidates", [{}])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})
        cached = usage_meta.get("cachedContentTokenCount", 0)

        return {
            "id": f"foundrygate-google-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            },
            "_foundrygate": {
                "provider": self.name,
                "model": model,
                "latency_ms": round(latency, 1),
                "cache_hit_tokens": cached,
                "cache_miss_tokens": max(0, usage_meta.get("promptTokenCount", 0) - cached),
            },
        }


class ProviderError(Exception):
    """Raised when a provider returns an error."""

    def __init__(self, provider: str, status: int, detail: str):
        self.provider = provider
        self.status = status
        self.detail = detail
        super().__init__(f"[{provider}] HTTP {status}: {detail}")
