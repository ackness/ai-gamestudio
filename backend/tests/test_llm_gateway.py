"""Tests for LLM Gateway — LlmResult dataclass and streaming usage capture."""

from __future__ import annotations

import pytest

from backend.app.core.llm_gateway import LlmResult, create_stream_result


class TestLlmResult:
    """Tests for the LlmResult dataclass."""

    def test_llm_result_defaults(self):
        result = LlmResult()
        assert result.content == ""
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0

    def test_llm_result_total_tokens(self):
        result = LlmResult(prompt_tokens=100, completion_tokens=50)
        assert result.total_tokens == 150

    def test_llm_result_total_tokens_with_content(self):
        result = LlmResult(content="Hello world", prompt_tokens=10, completion_tokens=5)
        assert result.total_tokens == 15
        assert result.content == "Hello world"

    def test_llm_result_mutable(self):
        result = LlmResult()
        result.prompt_tokens = 200
        result.completion_tokens = 100
        result.content = "accumulated"
        assert result.total_tokens == 300
        assert result.content == "accumulated"


class TestCreateStreamResult:
    """Tests for the create_stream_result factory function."""

    def test_create_stream_result_returns_llm_result(self):
        result = create_stream_result()
        assert isinstance(result, LlmResult)

    def test_create_stream_result_defaults(self):
        result = create_stream_result()
        assert result.content == ""
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0

    def test_create_stream_result_independent_instances(self):
        r1 = create_stream_result()
        r2 = create_stream_result()
        r1.prompt_tokens = 42
        assert r2.prompt_tokens == 0


class TestStreamUsageCapture:
    """Tests for streaming usage capture in _stream_chunks."""

    @pytest.mark.asyncio
    async def test_stream_chunks_captures_usage(self):
        """Verify that usage info from streaming chunks is captured in result_acc."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.app.core.llm_gateway import _stream_chunks

        # Build mock chunks: two content chunks + one usage-only chunk
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock(content="Hello ")
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock(content="world")
        chunk2.usage = None

        # Final chunk with usage stats (no content)
        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta = MagicMock(content=None)
        chunk3.usage = MagicMock(prompt_tokens=50, completion_tokens=25)

        async def mock_aiter():
            for c in [chunk1, chunk2, chunk3]:
                yield c

        mock_response = mock_aiter()
        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result_acc = create_stream_result()
            call_kwargs = {"model": "test-model", "messages": [], "stream": True}

            collected = []
            async for text in _stream_chunks(call_kwargs, result_acc=result_acc):
                collected.append(text)

        assert collected == ["Hello ", "world"]
        assert result_acc.prompt_tokens == 50
        assert result_acc.completion_tokens == 25
        assert result_acc.total_tokens == 75

    @pytest.mark.asyncio
    async def test_stream_chunks_without_result_acc(self):
        """Verify streaming works fine without a result_acc (backward compat)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.app.core.llm_gateway import _stream_chunks

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock(content="Hi")
        chunk1.usage = None

        async def mock_aiter():
            yield chunk1

        mock_response = mock_aiter()
        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            call_kwargs = {"model": "test-model", "messages": [], "stream": True}
            collected = []
            async for text in _stream_chunks(call_kwargs):
                collected.append(text)

        assert collected == ["Hi"]

    @pytest.mark.asyncio
    async def test_stream_options_injected(self):
        """Verify that stream_options is added to call_kwargs."""
        from unittest.mock import AsyncMock, patch

        from backend.app.core.llm_gateway import _stream_chunks

        async def mock_aiter():
            return
            yield  # make this an async generator

        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_aiter())

            call_kwargs = {"model": "test-model", "messages": [], "stream": True}
            async for _ in _stream_chunks(call_kwargs):
                pass

            # Verify stream_options was added
            actual_kwargs = mock_litellm.acompletion.call_args[1]
            assert actual_kwargs["stream_options"] == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_stream_options_not_overwritten(self):
        """Verify existing stream_options are not overwritten."""
        from unittest.mock import AsyncMock, patch

        from backend.app.core.llm_gateway import _stream_chunks

        async def mock_aiter():
            return
            yield

        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_aiter())

            custom_opts = {"include_usage": True, "custom": "value"}
            call_kwargs = {
                "model": "test-model",
                "messages": [],
                "stream": True,
                "stream_options": custom_opts,
            }
            async for _ in _stream_chunks(call_kwargs):
                pass

            actual_kwargs = mock_litellm.acompletion.call_args[1]
            assert actual_kwargs["stream_options"] == custom_opts


class TestCompletionWithConfigResultAcc:
    """Tests that completion_with_config passes result_acc through."""

    @pytest.mark.asyncio
    async def test_non_streaming_populates_result_acc(self):
        """Non-streaming completion should populate result_acc from response.usage."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.app.core.llm_gateway import completion_with_config

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage = MagicMock(prompt_tokens=30, completion_tokens=10)

        config = MagicMock()
        config.model = "test-model"
        config.api_key = None
        config.api_base = None
        config.is_empty_key.return_value = True

        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result_acc = create_stream_result()
            result = await completion_with_config(
                [{"role": "user", "content": "Hi"}],
                config,
                stream=False,
                result_acc=result_acc,
            )

        assert result == "Hello!"
        assert result_acc.prompt_tokens == 30
        assert result_acc.completion_tokens == 10
        assert result_acc.total_tokens == 40

    @pytest.mark.asyncio
    async def test_non_streaming_without_result_acc(self):
        """Non-streaming completion should work fine without result_acc."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.app.core.llm_gateway import completion_with_config

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage = MagicMock(prompt_tokens=30, completion_tokens=10)

        config = MagicMock()
        config.model = "test-model"
        config.api_key = None
        config.api_base = None
        config.is_empty_key.return_value = True

        with patch("backend.app.core.llm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            result = await completion_with_config(
                [{"role": "user", "content": "Hi"}],
                config,
                stream=False,
            )

        assert result == "Hello!"
