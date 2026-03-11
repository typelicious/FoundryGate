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

from foundrygate.providers import ProviderBackend  # noqa: E402


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
