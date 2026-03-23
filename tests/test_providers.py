"""Regression tests for provider payload construction.

These tests verify that providers correctly handle edge-cases in the
OpenAI messages format (content=None, multimodal arrays) without sending
invalid payloads to upstream APIs.
"""

# ruff: noqa: E402

import sys
import types

import pytest

# Mock httpx before importing provider code
_httpx = types.ModuleType("httpx")


class _Timeout:
    def __init__(self, *a, **kw):
        pass


class _Limits:
    def __init__(self, *a, **kw):
        pass


class _AsyncClient:
    def __init__(self, *a, **kw):
        pass

    async def aclose(self):
        pass


_httpx.Timeout = _Timeout
_httpx.Limits = _Limits
_httpx.AsyncClient = _AsyncClient
_httpx.TimeoutException = Exception
_httpx.ConnectError = Exception
sys.modules["httpx"] = _httpx

from faigate.providers import ProviderBackend  # noqa: E402


def _make_google_backend() -> ProviderBackend:
    cfg = {
        "backend": "google-genai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key": "fake-key",
        "model": "gemini-2.5-flash-lite",
        "max_tokens": 256,
    }
    return ProviderBackend("gemini-test", cfg)


def _install_fake_post(backend: ProviderBackend) -> dict:
    """Replace _client.post with an async stub that captures the JSON body."""
    captured: dict = {}

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "ok"}], "role": "model"},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 6,
                },
            }

    async def _fake_post(url, json=None, **kw):
        captured.update(json or {})
        return _FakeResp()

    backend._client.post = _fake_post  # type: ignore[attr-defined]
    return captured


def _install_fake_get(backend: ProviderBackend, status_code: int = 200, text: str = "") -> dict:
    """Replace _client.get with an async stub that captures the probe request."""
    captured: dict = {}

    class _FakeResp:
        def __init__(self):
            self.status_code = status_code
            self.text = text

        def json(self):
            return {"object": "list", "data": []}

    async def _fake_get(url, headers=None, timeout=None, **kw):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["timeout"] = timeout
        return _FakeResp()

    backend._client.get = _fake_get  # type: ignore[attr-defined]
    return captured


# ── Google GenAI payload construction ────────────────────────────────────────


class TestGooglePayloadConstruction:
    """Verify _complete_google builds a valid payload even for edge-case inputs."""

    @pytest.mark.asyncio
    async def test_none_content_does_not_produce_null_text_part(self):
        """content=None must not produce {"text": None} in Gemini parts (→ HTTP 400)."""
        backend = _make_google_backend()
        captured = _install_fake_post(backend)
        await backend._complete_google(
            messages=[
                {"role": "system", "content": None},
                {"role": "user", "content": "hello"},
            ],
            model="gemini-2.5-flash-lite",
            stream=False,
            temperature=None,
            max_tokens=64,
        )
        # Every part in every content must have a str (not None) text value
        for item in captured.get("contents", []):
            for part in item.get("parts", []):
                assert isinstance(part.get("text"), str), f"Non-string text in part: {part}"


class TestProviderHealthProbes:
    @pytest.mark.asyncio
    async def test_local_probe_uses_models_endpoint(self):
        backend = ProviderBackend(
            "local-worker",
            {
                "backend": "openai-compat",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "local",
                "model": "llama3",
            },
        )
        captured = _install_fake_get(backend)

        ok = await backend.probe_health(timeout_seconds=3.0)

        assert ok is True
        assert captured["url"] == "http://127.0.0.1:11434/v1/models"
        assert captured["headers"]["Authorization"] == "Bearer local"
        assert captured["timeout"] == 3.0
        assert backend.health.healthy is True

    @pytest.mark.asyncio
    async def test_local_probe_marks_provider_unhealthy_on_http_error(self):
        backend = ProviderBackend(
            "local-worker",
            {
                "backend": "openai-compat",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "local",
                "model": "llama3",
            },
        )
        _install_fake_get(backend, status_code=503, text="unavailable")

        await backend.probe_health()
        await backend.probe_health()
        ok = await backend.probe_health()

        assert ok is False
        assert backend.health.healthy is False
        assert "Probe HTTP 503" in backend.health.last_error

    @pytest.mark.asyncio
    async def test_provider_request_readiness_flags_unresolved_key(self):
        backend = ProviderBackend(
            "cloud-default",
            {
                "backend": "openai-compat",
                "base_url": "https://api.example.com/v1",
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o",
            },
        )

        readiness = backend.request_readiness()

        assert readiness["ready"] is False
        assert readiness["status"] == "unresolved-key"
        assert readiness["profile"] == "openai-compatible"

    @pytest.mark.asyncio
    async def test_aggregator_request_readiness_reports_compatibility_profile(self):
        backend = ProviderBackend(
            "kilocode",
            {
                "backend": "openai-compat",
                "base_url": "https://api.kilo.example/v1",
                "api_key": "secret",
                "model": "glm-5-free",
                "transport": {
                    "profile": "kilo-openai-compat",
                    "compatibility": "aggregator",
                    "probe_confidence": "medium",
                    "auth_mode": "bearer",
                    "probe_strategy": "models",
                    "models_path": "/models",
                    "chat_path": "/chat/completions",
                    "image_generation_path": "/images/generations",
                    "image_edit_path": "/images/edits",
                    "requires_api_key": True,
                    "supports_models_probe": True,
                    "notes": ["aggregator route uses compatibility assumptions"],
                },
            },
        )

        readiness = backend.request_readiness()

        assert readiness["ready"] is True
        assert readiness["status"] == "ready-compat"
        assert readiness["compatibility"] == "aggregator"
        assert readiness["probe_confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_assistant_none_content_converted_to_empty_string(self):
        """assistant message with content=None (tool-call turn) must produce text=''."""
        backend = _make_google_backend()
        captured = _install_fake_post(backend)
        await backend._complete_google(
            messages=[
                {"role": "user", "content": "use the tool"},
                {"role": "assistant", "content": None},
                {"role": "user", "content": "ok continue"},
            ],
            model="gemini-2.5-flash-lite",
            stream=False,
            temperature=None,
            max_tokens=64,
        )
        for item in captured.get("contents", []):
            for part in item.get("parts", []):
                assert isinstance(part.get("text"), str), f"Non-string text in part: {part}"

    @pytest.mark.asyncio
    async def test_multimodal_content_array_flattened(self):
        """Multimodal content list must be flattened to a plain string for Gemini."""
        backend = _make_google_backend()
        captured = _install_fake_post(backend)
        await backend._complete_google(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ],
            model="gemini-2.5-flash-lite",
            stream=False,
            temperature=None,
            max_tokens=64,
        )
        for item in captured.get("contents", []):
            for part in item.get("parts", []):
                assert isinstance(part.get("text"), str), f"Non-string text in part: {part}"


class TestImageGeneration:
    @pytest.mark.asyncio
    async def test_openai_completion_honors_custom_transport_chat_path(self):
        backend = ProviderBackend(
            "cloud-default",
            {
                "backend": "openai-compat",
                "base_url": "https://api.example.com/v1",
                "api_key": "secret",
                "model": "gpt-4o",
                "transport": {"chat_path": "/responses/chat"},
            },
        )
        captured: dict = {}

        class _FakeResp:
            status_code = 200

            def json(self):
                return {
                    "id": "chatcmpl-test",
                    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        async def _fake_post(url, json=None, headers=None, **_kw):
            captured["url"] = url
            captured["json"] = json or {}
            captured["headers"] = headers or {}
            return _FakeResp()

        backend._client.post = _fake_post  # type: ignore[attr-defined]

        await backend.complete([{"role": "user", "content": "hello"}])

        assert captured["url"] == "https://api.example.com/v1/responses/chat"

    @pytest.mark.asyncio
    async def test_openai_image_generation_posts_to_images_endpoint(self):
        backend = ProviderBackend(
            "image-cloud",
            {
                "contract": "image-provider",
                "backend": "openai-compat",
                "base_url": "https://api.example.com/v1",
                "api_key": "secret",
                "model": "gpt-image-1",
            },
        )
        captured: dict = {}

        class _FakeResp:
            status_code = 200

            def json(self):
                return {"created": 1, "data": [{"b64_json": "abc"}]}

        async def _fake_post(url, json=None, headers=None, **kw):
            captured["url"] = url
            captured["json"] = json or {}
            captured["headers"] = headers or {}
            return _FakeResp()

        backend._client.post = _fake_post  # type: ignore[attr-defined]

        result = await backend.generate_image(
            "draw a lighthouse",
            size="1024x1024",
            response_format="b64_json",
            user="tester",
        )

        assert captured["url"] == "https://api.example.com/v1/images/generations"
        assert captured["json"]["model"] == "gpt-image-1"
        assert captured["json"]["prompt"] == "draw a lighthouse"
        assert captured["json"]["size"] == "1024x1024"
        assert captured["json"]["response_format"] == "b64_json"
        assert captured["json"]["user"] == "tester"
        assert result["_faigate"]["provider"] == "image-cloud"
        assert result["_faigate"]["modality"] == "image_generation"

    @pytest.mark.asyncio
    async def test_openai_image_editing_posts_to_edits_endpoint(self):
        backend = ProviderBackend(
            "image-cloud",
            {
                "contract": "image-provider",
                "backend": "openai-compat",
                "base_url": "https://api.example.com/v1",
                "api_key": "secret",
                "model": "gpt-image-1",
                "capabilities": {"image_editing": True},
            },
        )
        captured: dict = {}

        class _FakeResp:
            status_code = 200

            def json(self):
                return {"created": 1, "data": [{"b64_json": "edited"}]}

        async def _fake_post(url, data=None, files=None, headers=None, **kw):
            captured["url"] = url
            captured["data"] = data or {}
            captured["files"] = files or []
            captured["headers"] = headers or {}
            return _FakeResp()

        backend._client.post = _fake_post  # type: ignore[attr-defined]

        result = await backend.edit_image(
            "remove the background",
            image={
                "filename": "input.png",
                "content": b"image-bytes",
                "content_type": "image/png",
            },
            mask={
                "filename": "mask.png",
                "content": b"mask-bytes",
                "content_type": "image/png",
            },
            n=2,
            size="1024x1024",
            response_format="b64_json",
            user="tester",
        )

        assert captured["url"] == "https://api.example.com/v1/images/edits"
        assert captured["data"]["model"] == "gpt-image-1"
        assert captured["data"]["prompt"] == "remove the background"
        assert captured["data"]["n"] == "2"
        assert captured["data"]["size"] == "1024x1024"
        assert captured["data"]["response_format"] == "b64_json"
        assert captured["data"]["user"] == "tester"
        assert captured["files"][0][0] == "image"
        assert captured["files"][0][1][0] == "input.png"
        assert captured["files"][1][0] == "mask"
        assert captured["files"][1][1][0] == "mask.png"
        assert result["_faigate"]["provider"] == "image-cloud"
        assert result["_faigate"]["modality"] == "image_editing"
