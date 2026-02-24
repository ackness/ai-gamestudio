# Token Tracking, Cost Display & Auto-Compress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add token usage tracking with cost estimation, context window progress display, and an auto-compress plugin that summarizes old conversations when approaching context limits.

**Architecture:** Backend captures token usage via LiteLLM's built-in `token_counter()` and `cost_per_token()` APIs. Each LLM turn yields `token_usage` events through WebSocket. A new `auto-compress` plugin monitors context usage and triggers LLM-based summarization when threshold is exceeded. Frontend displays cumulative tokens/cost in the GamePanel header bar.

**Tech Stack:** LiteLLM (token_counter, cost_per_token, get_model_info, stream_options), FastAPI, Zustand, Tailwind CSS

---

## Task 1: Backend Token Service

Creates the core token counting and cost calculation module using LiteLLM's built-in APIs.

**Files:**
- Create: `backend/app/services/token_service.py`
- Create: `backend/tests/test_token_service.py`

**Step 1: Write failing tests for token service**

```python
# backend/tests/test_token_service.py
"""Tests for token_service — token counting, cost calculation, model info."""

import pytest
from unittest.mock import patch, MagicMock

from backend.app.services.token_service import (
    count_message_tokens,
    get_model_context_window,
    calculate_turn_cost,
    format_token_count,
    TokenUsage,
)


def test_count_message_tokens_returns_int():
    messages = [{"role": "user", "content": "Hello world"}]
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.token_counter.return_value = 15
        result = count_message_tokens("gpt-4", messages)
        assert result == 15
        mock_ll.token_counter.assert_called_once_with(model="gpt-4", messages=messages)


def test_count_message_tokens_fallback_on_error():
    messages = [{"role": "user", "content": "Hello world"}]
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.token_counter.side_effect = Exception("unknown model")
        result = count_message_tokens("unknown/model", messages)
        # Fallback: rough estimate based on character count
        assert isinstance(result, int)
        assert result > 0


def test_get_model_context_window_known_model():
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.get_model_info.return_value = {
            "max_input_tokens": 128000,
            "max_output_tokens": 4096,
            "max_tokens": 128000,
        }
        result = get_model_context_window("gpt-4")
        assert result["max_input_tokens"] == 128000
        assert result["max_output_tokens"] == 4096


def test_get_model_context_window_unknown_model():
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.get_model_info.side_effect = Exception("not found")
        result = get_model_context_window("unknown/model")
        assert result["max_input_tokens"] == 0
        assert result["max_output_tokens"] == 0


def test_calculate_turn_cost():
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.cost_per_token.return_value = (0.001, 0.002)
        cost = calculate_turn_cost("gpt-4", prompt_tokens=1000, completion_tokens=500)
        assert cost == pytest.approx(0.003)


def test_calculate_turn_cost_unknown_model():
    with patch("backend.app.services.token_service.litellm") as mock_ll:
        mock_ll.cost_per_token.side_effect = Exception("not found")
        cost = calculate_turn_cost("unknown/model", prompt_tokens=1000, completion_tokens=500)
        assert cost == 0.0


def test_format_token_count():
    assert format_token_count(500) == "500"
    assert format_token_count(1500) == "1.5k"
    assert format_token_count(1000000) == "1.0M"
    assert format_token_count(1500000000) == "1.5B"
    assert format_token_count(0) == "0"


def test_token_usage_dataclass():
    usage = TokenUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        prompt_cost=0.001,
        completion_cost=0.002,
        total_cost=0.003,
    )
    assert usage.total_tokens == 150
    assert usage.total_cost == 0.003
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_token_service.py -v`
Expected: FAIL (module not found)

**Step 3: Implement token service**

```python
# backend/app/services/token_service.py
"""Token counting, cost calculation, and model info via LiteLLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm
from loguru import logger


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0


def count_message_tokens(model: str, messages: list[dict[str, str]]) -> int:
    """Estimate token count for a message list using LiteLLM's tokenizer.

    Falls back to a rough character-based estimate if the model is unknown.
    """
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:
        logger.debug("token_counter fallback for model={}", model)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, total_chars // 4)


def get_model_context_window(model: str) -> dict[str, int]:
    """Return max_input_tokens and max_output_tokens for a model.

    Returns zeros if model is not found in LiteLLM's database.
    """
    try:
        info = litellm.get_model_info(model)
        return {
            "max_input_tokens": info.get("max_input_tokens") or info.get("max_tokens") or 0,
            "max_output_tokens": info.get("max_output_tokens") or 0,
        }
    except Exception:
        logger.debug("get_model_info fallback for model={}", model)
        return {"max_input_tokens": 0, "max_output_tokens": 0}


def calculate_turn_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate cost in USD for a single turn using LiteLLM's pricing data."""
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return prompt_cost + completion_cost
    except Exception:
        logger.debug("cost_per_token fallback for model={}", model)
        return 0.0


def get_model_pricing(model: str) -> dict[str, Any]:
    """Return pricing info for a model (input/output cost per token)."""
    try:
        info = litellm.get_model_info(model)
        return {
            "input_cost_per_token": info.get("input_cost_per_token", 0.0),
            "output_cost_per_token": info.get("output_cost_per_token", 0.0),
        }
    except Exception:
        return {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0}


def format_token_count(count: int) -> str:
    """Format a token count as human-readable string (500, 1.5k, 2.3M, etc.)."""
    if count == 0:
        return "0"
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_token_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/token_service.py backend/tests/test_token_service.py
git commit -m "feat(token): add token counting and cost calculation service via LiteLLM"
```

---

## Task 2: LLM Gateway — Capture Streaming Token Usage

Modify the LLM gateway to return token usage data from streaming responses.

**Files:**
- Modify: `backend/app/core/llm_gateway.py`
- Modify: `backend/tests/test_llm_gateway.py` (create if not exists)

**Step 1: Write failing test for LlmResult**

```python
# backend/tests/test_llm_gateway.py
"""Tests for LLM gateway streaming with usage capture."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.core.llm_gateway import LlmResult, stream_with_usage


@pytest.mark.asyncio
async def test_llm_result_dataclass():
    result = LlmResult(content="hello", prompt_tokens=10, completion_tokens=5)
    assert result.content == "hello"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_llm_gateway.py -v`
Expected: FAIL (LlmResult not found)

**Step 3: Implement LlmResult and modify gateway**

Modify `backend/app/core/llm_gateway.py`:

1. Add `LlmResult` dataclass at the top
2. Add `stream_options={"include_usage": True}` to streaming calls
3. Capture usage from the final chunk in `_stream_chunks`
4. Add new `stream_with_usage()` function that returns `(AsyncIterator[str], Future[LlmResult])`

```python
# Add to backend/app/core/llm_gateway.py

from dataclasses import dataclass

@dataclass
class LlmResult:
    """Holds LLM response content and token usage."""
    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
```

Modify `_stream_chunks` to accept an optional `LlmResult` accumulator and add `stream_options`:

```python
async def _stream_chunks(
    call_kwargs: dict[str, Any],
    result_acc: LlmResult | None = None,
) -> AsyncIterator[str]:
    call_kwargs.setdefault("stream_options", {"include_usage": True})
    response = await litellm.acompletion(**call_kwargs)
    async for chunk in response:
        # Check for usage data in the final chunk
        if hasattr(chunk, "usage") and chunk.usage and result_acc is not None:
            result_acc.prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
            result_acc.completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
```

Add a convenience function:

```python
def create_stream_result() -> LlmResult:
    """Create a mutable LlmResult to pass into streaming calls."""
    return LlmResult()
```

Modify `completion_with_config` to accept optional `result_acc`:

```python
async def completion_with_config(
    messages: list[dict[str, str]],
    config: ResolvedLlmConfig,
    stream: bool = False,
    result_acc: LlmResult | None = None,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    # ... existing setup code ...
    try:
        if stream:
            return _stream_chunks(call_kwargs, result_acc)
        else:
            response = await litellm.acompletion(**call_kwargs)
            content = response.choices[0].message.content or ""
            if result_acc is not None and hasattr(response, "usage") and response.usage:
                result_acc.content = content
                result_acc.prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                result_acc.completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
            return content
    except Exception:
        logger.exception("LLM call failed")
        raise
```

**Step 4: Run tests**

Run: `uv run pytest backend/tests/test_llm_gateway.py -v`
Expected: PASS

**Step 5: Run existing tests to ensure no regressions**

Run: `uv run pytest backend/tests/ -v --timeout=30`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add backend/app/core/llm_gateway.py backend/tests/test_llm_gateway.py
git commit -m "feat(llm): capture streaming token usage via LlmResult accumulator"
```

---

## Task 3: Chat Service — Token Usage Events

Wire token tracking into the chat service to emit `token_usage` events per turn and accumulate session totals.

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/tests/test_chat_service.py`

**Step 1: Write failing test for token_usage event**

Add to `backend/tests/test_chat_service.py`:

```python
@pytest.mark.asyncio
async def test_process_message_yields_token_usage_event(db_session, sample_session):
    """process_message should yield a token_usage event with token counts and cost."""
    events = []
    with (
        patch("backend.app.services.chat_service.engine", new=db_session.get_bind()),
        patch("backend.app.services.chat_service.completion_with_config") as mock_llm,
        patch("backend.app.services.chat_service.get_enabled_plugins", return_value=[]),
    ):
        async def fake_stream(*a, **kw):
            # Simulate LlmResult accumulator being populated
            result_acc = kw.get("result_acc")
            if result_acc is not None:
                result_acc.prompt_tokens = 100
                result_acc.completion_tokens = 50
            yield "Hello!"

        mock_llm.side_effect = lambda *a, **kw: fake_stream(*a, **kw)

        async for event in process_message(sample_session.id, "test"):
            events.append(event)

    token_events = [e for e in events if e["type"] == "token_usage"]
    assert len(token_events) == 1
    te = token_events[0]
    assert te["data"]["prompt_tokens"] == 100
    assert te["data"]["completion_tokens"] == 50
    assert "total_cost" in te["data"]
    assert "context_usage" in te["data"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_chat_service.py -k "test_process_message_yields_token_usage_event" -v`
Expected: FAIL

**Step 3: Implement token tracking in chat_service.py**

Modify `process_message()` in `backend/app/services/chat_service.py`:

1. Import `token_service` functions and `LlmResult` / `create_stream_result`
2. Before LLM call: estimate prompt tokens with `count_message_tokens()`
3. Create `LlmResult` accumulator and pass to `completion_with_config`
4. After streaming completes: calculate cost with actual or estimated tokens
5. Update cumulative session token usage in `game_state_json`
6. Yield `token_usage` event

Key code changes in `process_message()`:

```python
from backend.app.core.llm_gateway import create_stream_result
from backend.app.services.token_service import (
    count_message_tokens,
    calculate_turn_cost,
    get_model_context_window,
)

# ... inside process_message(), after assemble_prompt() ...

# Estimate prompt tokens before sending
estimated_prompt_tokens = count_message_tokens(config.model, messages)
context_window = get_model_context_window(config.model)
max_input = context_window["max_input_tokens"]

# Stream with usage accumulator
result_acc = create_stream_result()
try:
    full_response = ""
    stream = await completion_with_config(messages, config, stream=True, result_acc=result_acc)
    async for chunk in stream:
        full_response += chunk
        yield {"type": "chunk", "content": chunk, "turn_id": turn_id}
except Exception as exc:
    # ... existing error handling ...

# Use actual tokens from provider if available, otherwise use estimate
prompt_tokens = result_acc.prompt_tokens or estimated_prompt_tokens
completion_tokens = result_acc.completion_tokens or max(1, len(full_response) // 4)

# Calculate cost
turn_cost = calculate_turn_cost(config.model, prompt_tokens, completion_tokens)

# Update cumulative session token usage
game_state = json.loads(ctx.session.game_state_json or "{}")
token_state = game_state.setdefault("token_usage", {
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_cost": 0.0,
})
token_state["total_prompt_tokens"] += prompt_tokens
token_state["total_completion_tokens"] += completion_tokens
token_state["total_cost"] += turn_cost

# Context usage ratio
context_usage = prompt_tokens / max_input if max_input > 0 else 0.0

# Yield token_usage event (before blocks, after chunks)
yield {
    "type": "token_usage",
    "turn_id": turn_id,
    "data": {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "turn_cost": turn_cost,
        "total_cost": token_state["total_cost"],
        "total_prompt_tokens": token_state["total_prompt_tokens"],
        "total_completion_tokens": token_state["total_completion_tokens"],
        "context_usage": round(context_usage, 4),
        "max_input_tokens": max_input,
        "model": config.model,
    },
}
```

The `game_state_json` update should happen in the same commit block where `turn_count` is incremented (step 6 of current code).

**Step 4: Run tests**

Run: `uv run pytest backend/tests/test_chat_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/chat_service.py backend/tests/test_chat_service.py
git commit -m "feat(token): emit token_usage events with cost and context usage per turn"
```

---

## Task 4: WebSocket — Forward token_usage Events

Update the chat router to forward `token_usage` events to the frontend.

**Files:**
- Modify: `backend/app/api/chat.py`

**Step 1: Modify `_stream_process_message` to forward token_usage**

In `_stream_process_message()`, the current logic puts non-chunk/non-error events into `pending_blocks`. The `token_usage` event should be sent **immediately** (like `chunk`), not deferred to after `done`.

Add a case in the event loop:

```python
# In _stream_process_message(), inside the async for loop:
elif event["type"] == "token_usage":
    # Forward immediately — don't wait for done/turn_end
    token_event = {
        "type": "token_usage",
        "data": event.get("data", {}),
        "turn_id": turn_id,
    }
    _add_log(session_id, "send", token_event)
    await sink.send_json(token_event)
```

**Step 2: Run existing tests**

Run: `uv run pytest backend/tests/ -v --timeout=30`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/app/api/chat.py
git commit -m "feat(ws): forward token_usage events immediately to frontend"
```

---

## Task 5: Model Info API Endpoint

Add a REST endpoint for the frontend to query model pricing and context window info.

**Files:**
- Create: `backend/app/api/model_info.py`
- Modify: `backend/app/main.py` (register router)

**Step 1: Create model info router**

```python
# backend/app/api/model_info.py
"""API endpoint for model pricing and context window information."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.token_service import (
    get_model_context_window,
    get_model_pricing,
    format_token_count,
)

router = APIRouter()


@router.get("/api/model-info")
async def model_info(model: str = Query(..., description="Model name (e.g. deepseek/deepseek-chat)")):
    """Return pricing and context window info for a model."""
    ctx_window = get_model_context_window(model)
    pricing = get_model_pricing(model)
    return {
        "model": model,
        "max_input_tokens": ctx_window["max_input_tokens"],
        "max_output_tokens": ctx_window["max_output_tokens"],
        "max_input_tokens_display": format_token_count(ctx_window["max_input_tokens"]),
        "input_cost_per_token": pricing["input_cost_per_token"],
        "output_cost_per_token": pricing["output_cost_per_token"],
        "known": ctx_window["max_input_tokens"] > 0,
    }
```

**Step 2: Register router in main.py**

Add to `backend/app/main.py`:

```python
from backend.app.api.model_info import router as model_info_router
app.include_router(model_info_router)
```

**Step 3: Run tests**

Run: `uv run pytest backend/tests/ -v --timeout=30`
Expected: All PASS

**Step 4: Commit**

```bash
git add backend/app/api/model_info.py backend/app/main.py
git commit -m "feat(api): add GET /api/model-info endpoint for pricing and context window"
```

---

## Task 6: Frontend — Token Store

Create a Zustand store to track token usage per session.

**Files:**
- Create: `frontend/src/stores/tokenStore.ts`

**Step 1: Create token store**

```typescript
// frontend/src/stores/tokenStore.ts
import { create } from 'zustand'

export interface TokenUsageData {
  promptTokens: number
  completionTokens: number
  totalTokens: number
  turnCost: number
  totalCost: number
  totalPromptTokens: number
  totalCompletionTokens: number
  contextUsage: number   // 0.0 - 1.0
  maxInputTokens: number
  model: string
}

export interface ModelInfo {
  model: string
  maxInputTokens: number
  maxOutputTokens: number
  maxInputTokensDisplay: string
  inputCostPerToken: number
  outputCostPerToken: number
  known: boolean
}

interface TokenStore {
  usage: TokenUsageData | null
  modelInfo: ModelInfo | null
  customPricing: Record<string, { inputCost: number; outputCost: number }> // per model

  updateUsage: (data: TokenUsageData) => void
  setModelInfo: (info: ModelInfo) => void
  setCustomPricing: (model: string, inputCost: number, outputCost: number) => void
  reset: () => void
}

export const useTokenStore = create<TokenStore>((set) => ({
  usage: null,
  modelInfo: null,
  customPricing: JSON.parse(localStorage.getItem('customPricing') || '{}'),

  updateUsage: (data) => set({ usage: data }),

  setModelInfo: (info) => set({ modelInfo: info }),

  setCustomPricing: (model, inputCost, outputCost) =>
    set((state) => {
      const next = { ...state.customPricing, [model]: { inputCost, outputCost } }
      localStorage.setItem('customPricing', JSON.stringify(next))
      return { customPricing: next }
    }),

  reset: () => set({ usage: null }),
}))
```

**Step 2: Commit**

```bash
git add frontend/src/stores/tokenStore.ts
git commit -m "feat(frontend): add tokenStore for session token usage tracking"
```

---

## Task 7: Frontend — WebSocket Token Event Handler

Handle `token_usage` events from WebSocket and update the store.

**Files:**
- Modify: `frontend/src/services/websocket.ts`
- Modify: `frontend/src/hooks/useGameWebSocket.ts`

**Step 1: Add token_usage callback to GameWebSocket**

In `frontend/src/services/websocket.ts`:

1. Add callback type:
```typescript
type TokenUsageCallback = (data: Record<string, unknown>) => void
```

2. Add callback property:
```typescript
onTokenUsage: TokenUsageCallback = () => {}
```

3. Add case in `handleServerEvent`:
```typescript
case 'token_usage':
  this.onTokenUsage((data.data as Record<string, unknown>) || {})
  break
```

**Step 2: Wire into useGameWebSocket hook**

In `frontend/src/hooks/useGameWebSocket.ts`, add:

```typescript
import { useTokenStore } from '../stores/tokenStore'

// Inside the effect where ws callbacks are set:
ws.onTokenUsage = (data) => {
  useTokenStore.getState().updateUsage({
    promptTokens: Number(data.prompt_tokens || 0),
    completionTokens: Number(data.completion_tokens || 0),
    totalTokens: Number(data.total_tokens || 0),
    turnCost: Number(data.turn_cost || 0),
    totalCost: Number(data.total_cost || 0),
    totalPromptTokens: Number(data.total_prompt_tokens || 0),
    totalCompletionTokens: Number(data.total_completion_tokens || 0),
    contextUsage: Number(data.context_usage || 0),
    maxInputTokens: Number(data.max_input_tokens || 0),
    model: String(data.model || ''),
  })
}
```

**Step 3: Reset token store on session switch**

In `frontend/src/stores/sessionStore.ts`, in `switchSession` and `createSession` and `deleteSession`, add:

```typescript
import { useTokenStore } from './tokenStore'
// Inside those functions:
useTokenStore.getState().reset()
```

**Step 4: Commit**

```bash
git add frontend/src/services/websocket.ts frontend/src/hooks/useGameWebSocket.ts frontend/src/stores/sessionStore.ts
git commit -m "feat(frontend): handle token_usage WebSocket events and reset on session switch"
```

---

## Task 8: Frontend — Fetch Model Info on Session Start

Fetch model info from the API when a session starts to display context window size.

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/hooks/useGameWebSocket.ts` or `frontend/src/components/game/GamePanel.tsx`

**Step 1: Add API function**

In `frontend/src/services/api.ts`:

```typescript
export async function getModelInfo(model: string): Promise<{
  model: string
  max_input_tokens: number
  max_output_tokens: number
  max_input_tokens_display: string
  input_cost_per_token: number
  output_cost_per_token: number
  known: boolean
}> {
  const res = await fetch(`${API_BASE}/model-info?model=${encodeURIComponent(model)}`)
  if (!res.ok) throw new Error(`Failed to fetch model info: ${res.status}`)
  return res.json()
}
```

**Step 2: Fetch model info in GamePanel**

In `frontend/src/components/game/GamePanel.tsx`, add an effect that fetches model info when `llmInfo` changes:

```typescript
import { useTokenStore } from '../../stores/tokenStore'
import * as api from '../../services/api'

// Inside GamePanel:
const { modelInfo, setModelInfo } = useTokenStore()

useEffect(() => {
  if (!effectiveModel) return
  api.getModelInfo(effectiveModel).then((info) => {
    setModelInfo({
      model: info.model,
      maxInputTokens: info.max_input_tokens,
      maxOutputTokens: info.max_output_tokens,
      maxInputTokensDisplay: info.max_input_tokens_display,
      inputCostPerToken: info.input_cost_per_token,
      outputCostPerToken: info.output_cost_per_token,
      known: info.known,
    })
  }).catch(() => {
    // Silently ignore — model info is optional
  })
}, [effectiveModel, setModelInfo])
```

**Step 3: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/game/GamePanel.tsx
git commit -m "feat(frontend): fetch model info on session start for context window display"
```

---

## Task 9: Frontend — Token Usage Display UI

Add token count, cost, and context progress bar to the GamePanel header.

**Files:**
- Create: `frontend/src/components/game/TokenUsageBar.tsx`
- Modify: `frontend/src/components/game/GamePanel.tsx`

**Step 1: Create TokenUsageBar component**

```tsx
// frontend/src/components/game/TokenUsageBar.tsx
import { useTokenStore } from '../../stores/tokenStore'
import { useUiStore } from '../../stores/uiStore'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const text: Record<string, Record<string, string>> = {
  zh: {
    tokens: '令牌',
    cost: '费用',
    context: '上下文',
    input: '输入',
    output: '输出',
    total: '合计',
    unknown: '未知模型定价',
  },
  en: {
    tokens: 'Tokens',
    cost: 'Cost',
    context: 'Context',
    input: 'Input',
    output: 'Output',
    total: 'Total',
    unknown: 'Unknown model pricing',
  },
}

function formatTokens(n: number): string {
  if (n === 0) return '0'
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0'
  if (cost < 0.001) return `$${cost.toFixed(6)}`
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  if (cost < 1) return `$${cost.toFixed(3)}`
  return `$${cost.toFixed(2)}`
}

export function TokenUsageBar() {
  const usage = useTokenStore((s) => s.usage)
  const modelInfo = useTokenStore((s) => s.modelInfo)
  const language = useUiStore((s) => s.language)
  const t = text[language] ?? text.en

  if (!usage && !modelInfo) return null

  const totalTokens = usage?.totalPromptTokens ?? 0
  const totalCompletionTokens = usage?.totalCompletionTokens ?? 0
  const totalCost = usage?.totalCost ?? 0
  const contextUsage = usage?.contextUsage ?? 0
  const maxInput = usage?.maxInputTokens || modelInfo?.maxInputTokens || 0
  const maxInputDisplay = modelInfo?.maxInputTokensDisplay || formatTokens(maxInput)

  const pct = Math.min(contextUsage * 100, 100)
  const barColor =
    pct >= 80 ? 'bg-red-500' :
    pct >= 50 ? 'bg-yellow-500' :
    'bg-green-500'

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground cursor-default select-none">
          <span>{formatTokens(totalTokens + totalCompletionTokens)}</span>
          {maxInput > 0 && (
            <>
              <span className="text-muted-foreground/50">/</span>
              <span>{maxInputDisplay}</span>
              <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </>
          )}
          {totalCost > 0 && (
            <span className="text-muted-foreground/70">{formatCost(totalCost)}</span>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-xs">
        <div className="space-y-1">
          <div>{t.input}: {formatTokens(totalTokens)}</div>
          <div>{t.output}: {formatTokens(totalCompletionTokens)}</div>
          <div>{t.total}: {formatTokens(totalTokens + totalCompletionTokens)}</div>
          {totalCost > 0 && <div>{t.cost}: {formatCost(totalCost)}</div>}
          {maxInput > 0 && <div>{t.context}: {pct.toFixed(1)}% ({formatTokens(totalTokens)}/{maxInputDisplay})</div>}
          {modelInfo && !modelInfo.known && <div className="text-yellow-500">{t.unknown}</div>}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}
```

**Step 2: Add TokenUsageBar to GamePanel header**

In `frontend/src/components/game/GamePanel.tsx`, add `<TokenUsageBar />` after the model badge:

```tsx
import { TokenUsageBar } from './TokenUsageBar'

// In the header div, after {modelBadge}:
{modelBadge}
<TokenUsageBar />
```

Add this in **both** the no-session header and the active-session header.

**Step 3: Commit**

```bash
git add frontend/src/components/game/TokenUsageBar.tsx frontend/src/components/game/GamePanel.tsx
git commit -m "feat(ui): add token usage bar with cost and context progress to GamePanel header"
```

---

## Task 10: Auto-Compress Plugin — Backend

Create the auto-compress plugin that summarizes old conversations when context approaches the limit.

**Files:**
- Create: `plugins/auto-compress/manifest.json`
- Create: `plugins/auto-compress/PLUGIN.md`
- Create: `plugins/auto-compress/prompts/compression-context.md`

**Step 1: Create plugin manifest**

```json
{
  "schema_version": "2.0",
  "name": "auto-compress",
  "version": "1.0.0",
  "type": "global",
  "required": false,
  "default_enabled": true,
  "description": "Automatically compresses old conversation history into narrative summaries when context window usage approaches the limit. Works alongside the memory plugin — memory stores specific events, auto-compress stores background narratives.",
  "dependencies": [
    "database",
    "memory"
  ],
  "prompt": {
    "position": "memory",
    "priority": 5,
    "template": "prompts/compression-context.md"
  },
  "capabilities": {},
  "blocks": {},
  "events": {
    "emit": [],
    "listen": []
  },
  "storage": {
    "keys": [
      "compression-summary",
      "compression-state"
    ]
  },
  "permissions": {},
  "extensions": {
    "runtime_settings": {
      "settings": [
        {
          "key": "compression_threshold",
          "type": "number",
          "label": "Compression Threshold",
          "description": "Trigger compression when context usage exceeds this ratio (0.0 - 1.0)",
          "default": 0.7,
          "min": 0.3,
          "max": 0.95,
          "step": 0.05,
          "scope": "project",
          "affects": ["memory"],
          "i18n": {
            "zh": {
              "label": "压缩触发阈值",
              "description": "当上下文使用量超过此比例时触发自动压缩 (0.0 - 1.0)"
            }
          }
        },
        {
          "key": "keep_recent_messages",
          "type": "integer",
          "label": "Keep Recent Messages",
          "description": "Number of recent messages to keep after compression",
          "default": 6,
          "min": 2,
          "max": 20,
          "scope": "project",
          "affects": ["memory"],
          "i18n": {
            "zh": {
              "label": "保留近期消息数",
              "description": "压缩后保留的最近消息数量"
            }
          }
        }
      ]
    }
  },
  "i18n": {
    "en": {
      "name": "Auto Compress",
      "description": "Automatically compresses old conversation history into narrative summaries when approaching context limits."
    },
    "zh": {
      "name": "自动压缩",
      "description": "当对话接近上下文窗口上限时，自动将旧对话压缩为叙事摘要。"
    }
  }
}
```

**Step 2: Create PLUGIN.md**

```markdown
---
name: auto-compress
version: 1.0.0
type: global
---

# Auto Compress Plugin

This plugin automatically compresses old conversation history into concise narrative summaries when the context window usage approaches its limit.

## How It Works

- Monitors the ratio of current prompt tokens to the model's max_input_tokens
- When the ratio exceeds the configured threshold (default: 0.7), triggers compression
- Uses the LLM to summarize old conversations into two parts:
  - **Background narrative**: Story background, world state changes, NPC relationships
  - **Key events**: Important events pushed to the memory plugin's long-term-memory
- After compression, old messages are excluded from the chat history

## Relationship with Memory Plugin

- **Memory plugin**: Records specific events (who did what, when) — factual details
- **Auto-compress**: Records background narratives, historical context — macro-level story context
- They work together: memory keeps the details, auto-compress keeps the big picture
```

**Step 3: Create prompt template**

```markdown
{# plugins/auto-compress/prompts/compression-context.md #}
{% set summary = compression_summary %}
{% if summary %}
## Story Background (Compressed History)

The following is a compressed summary of earlier conversation history. Treat it as authoritative background context:

{{ summary }}

---
{% endif %}
```

**Step 4: Commit**

```bash
git add plugins/auto-compress/
git commit -m "feat(plugin): add auto-compress plugin manifest, docs, and prompt template"
```

---

## Task 11: Auto-Compress Service — Backend Logic

Implement the compression logic that summarizes old conversations.

**Files:**
- Create: `backend/app/services/compress_service.py`
- Create: `backend/tests/test_compress_service.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_compress_service.py
"""Tests for auto-compress service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.app.services.compress_service import (
    should_compress,
    build_compression_prompt,
    compress_history,
)


def test_should_compress_below_threshold():
    assert should_compress(context_usage=0.3, threshold=0.7) is False


def test_should_compress_above_threshold():
    assert should_compress(context_usage=0.75, threshold=0.7) is True


def test_should_compress_zero_context():
    assert should_compress(context_usage=0.0, threshold=0.7) is False


def test_build_compression_prompt():
    messages = [
        MagicMock(role="user", content="I enter the dark forest"),
        MagicMock(role="assistant", content="The trees loom overhead..."),
        MagicMock(role="user", content="I draw my sword"),
        MagicMock(role="assistant", content="Your blade gleams..."),
    ]
    prompt = build_compression_prompt(messages, existing_summary="")
    assert "dark forest" in prompt[1]["content"]
    assert "draw my sword" in prompt[1]["content"]


def test_build_compression_prompt_with_existing_summary():
    messages = [MagicMock(role="user", content="test")]
    prompt = build_compression_prompt(messages, existing_summary="Previously: hero entered village")
    assert "Previously: hero entered village" in prompt[1]["content"]


@pytest.mark.asyncio
async def test_compress_history_returns_summary():
    with patch("backend.app.services.compress_service.completion") as mock_llm:
        mock_llm.return_value = "## Background\nThe hero ventured into the forest.\n\n## Key Events\n- Hero found a magic sword"
        result = await compress_history(
            messages_to_compress=[
                MagicMock(role="user", content="I explore"),
                MagicMock(role="assistant", content="You find treasure"),
            ],
            existing_summary="",
            model="deepseek/deepseek-chat",
        )
        assert "forest" in result["summary"] or "treasure" in result["summary"] or "hero" in result["summary"].lower()
        assert isinstance(result["summary"], str)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_compress_service.py -v`
Expected: FAIL

**Step 3: Implement compress service**

```python
# backend/app/services/compress_service.py
"""Auto-compress service — summarizes old conversation history."""

from __future__ import annotations

from typing import Any

from loguru import logger

from backend.app.core.llm_gateway import completion
from backend.app.core.llm_config import resolve_llm_config


def should_compress(context_usage: float, threshold: float = 0.7) -> bool:
    """Check if compression should be triggered based on context usage ratio."""
    return context_usage >= threshold and context_usage > 0


def build_compression_prompt(
    messages: list[Any],
    existing_summary: str = "",
) -> list[dict[str, str]]:
    """Build the prompt for the compression LLM call."""
    conversation_text = ""
    for msg in messages:
        role = getattr(msg, "role", "unknown")
        content = getattr(msg, "content", "")
        conversation_text += f"[{role}]: {content}\n\n"

    existing_part = ""
    if existing_summary:
        existing_part = (
            f"The following is the existing compressed summary from previous compressions. "
            f"Incorporate and update it with the new conversation:\n\n{existing_summary}\n\n---\n\n"
        )

    system_msg = (
        "You are a narrative summarizer for an RPG game. Your job is to compress "
        "conversation history into a concise but comprehensive summary that preserves "
        "all important story context.\n\n"
        "Output format:\n"
        "1. A narrative summary covering: story background, world state changes, "
        "NPC relationships, character development, location changes, and any ongoing plotlines.\n"
        "2. Keep the summary concise but complete — the original messages will be discarded.\n"
        "3. Write in the same language as the conversation.\n"
        "4. Focus on WHAT HAPPENED, not how it was said.\n"
        "5. Preserve character names, location names, item names, and key numbers/stats."
    )

    user_msg = (
        f"{existing_part}"
        f"Please compress the following conversation into a narrative summary:\n\n"
        f"{conversation_text}"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


async def compress_history(
    messages_to_compress: list[Any],
    existing_summary: str,
    model: str,
    llm_overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Compress messages into a narrative summary using LLM.

    Returns dict with "summary" key.
    """
    if not messages_to_compress:
        return {"summary": existing_summary}

    prompt = build_compression_prompt(messages_to_compress, existing_summary)

    try:
        config = resolve_llm_config(overrides=llm_overrides)
        from backend.app.core.llm_gateway import completion_with_config
        summary = await completion_with_config(prompt, config, stream=False)
        return {"summary": summary.strip() if isinstance(summary, str) else str(summary).strip()}
    except Exception:
        logger.exception("Compression LLM call failed")
        # Fallback: just keep the existing summary
        return {"summary": existing_summary}
```

**Step 4: Run tests**

Run: `uv run pytest backend/tests/test_compress_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/compress_service.py backend/tests/test_compress_service.py
git commit -m "feat(compress): add compress_service with LLM-based history summarization"
```

---

## Task 12: Auto-Compress Integration — Wire into Chat Flow

Integrate auto-compress into the chat service turn flow and the turn context.

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/services/turn_context.py`
- Modify: `backend/app/services/prompt_assembly.py` (minor: pass compression_summary to context)

**Step 1: Load compression summary in turn_context.py**

Add to `TurnContext` dataclass:

```python
compression_summary: str = ""
```

Add a `_load_compression_summary` function similar to `_load_memories`:

```python
async def _load_compression_summary(
    db: SQLModelAsyncSession, project_id: str, enabled_names: list[str],
) -> str:
    if "auto-compress" not in enabled_names:
        return ""
    try:
        data = await storage_get(db, project_id, "auto-compress", "compression-summary")
        if isinstance(data, dict):
            return str(data.get("summary", ""))
        if isinstance(data, str):
            return data
        return ""
    except Exception:
        logger.exception("Failed to load compression summary")
        return ""
```

Call it in `build_turn_context()` and add to the TurnContext constructor.

**Step 2: Pass compression_summary to plugin context**

In `prompt_assembly.py`, inside `_inject_plugins()`, add to the `context` dict:

```python
"compression_summary": ctx.compression_summary,
```

**Step 3: Add auto-compress trigger in chat_service.py**

After the `token_usage` yield (and after the commit), add compression check:

```python
# 9. Auto compress check
if (
    "auto-compress" in ctx.enabled_names
    and context_usage > 0
):
    from backend.app.services.compress_service import should_compress, compress_history
    ac_settings = ctx.runtime_settings_by_plugin.get("auto-compress", {})
    threshold = float(ac_settings.get("compression_threshold", 0.7))
    keep_recent = int(ac_settings.get("keep_recent_messages", 6))

    if should_compress(context_usage, threshold):
        try:
            # Get all messages, compress older ones
            all_messages = await state_mgr.get_messages(session_id, limit=100)
            if len(all_messages) > keep_recent:
                messages_to_compress = all_messages[:-keep_recent]
                existing_summary = ctx.compression_summary

                result = await compress_history(
                    messages_to_compress,
                    existing_summary,
                    model=config.model,
                    llm_overrides=llm_overrides,
                )

                # Store the new summary
                await storage_set(
                    db, ctx.project.id, "auto-compress",
                    "compression-summary",
                    {"summary": result["summary"]},
                    autocommit=True,
                )

                # Store compression state
                await storage_set(
                    db, ctx.project.id, "auto-compress",
                    "compression-state",
                    {
                        "last_compressed_message_count": len(messages_to_compress),
                        "total_compressions": (
                            (await storage_get(db, ctx.project.id, "auto-compress", "compression-state") or {})
                            .get("total_compressions", 0) + 1
                        ),
                    },
                    autocommit=True,
                )

                yield {
                    "type": "notification",
                    "data": {
                        "level": "info",
                        "title": "上下文已压缩" if language_hint == "zh" else "Context Compressed",
                        "content": f"已将 {len(messages_to_compress)} 条旧消息压缩为摘要",
                    },
                    "turn_id": turn_id,
                }
                logger.info("Auto-compressed {} messages for session {}", len(messages_to_compress), session_id)

        except Exception:
            logger.exception("Auto-compress failed for session {}", session_id)
```

Note: Need to import `storage_set` at the top of `chat_service.py`:

```python
from backend.app.services.plugin_service import storage_set
```

**Step 4: Adjust history_limit in turn_context based on compression state**

In `build_turn_context()`, when auto-compress is enabled and has a summary, use a shorter history limit:

```python
# Adjust history limit if auto-compress has compressed data
compression_summary = await _load_compression_summary(db, project.id, enabled_names)
if compression_summary:
    # If we have a compression summary, we can use fewer messages
    ac_settings = runtime_settings_by_plugin.get("auto-compress", {})
    keep_recent = int(ac_settings.get("keep_recent_messages", 6))
    history_limit = min(history_limit, keep_recent + 4)  # Small buffer
```

**Step 5: Run all tests**

Run: `uv run pytest backend/tests/ -v --timeout=30`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/services/chat_service.py backend/app/services/turn_context.py backend/app/services/prompt_assembly.py
git commit -m "feat(compress): integrate auto-compress into chat flow with context-aware history limits"
```

---

## Task 13: Frontend — Custom Pricing Configuration

Allow users to set custom pricing for unknown models via the UI.

**Files:**
- Create: `frontend/src/components/game/CustomPricingModal.tsx`
- Modify: `frontend/src/components/game/TokenUsageBar.tsx` (add edit button for unknown models)

**Step 1: Create CustomPricingModal**

```tsx
// frontend/src/components/game/CustomPricingModal.tsx
import { useState } from 'react'
import { useTokenStore } from '../../stores/tokenStore'
import { useUiStore } from '../../stores/uiStore'
import { Button } from '@/components/ui/button'

const text: Record<string, Record<string, string>> = {
  zh: {
    title: '自定义模型价格',
    inputCost: '输入价格 (USD/1K tokens)',
    outputCost: '输出价格 (USD/1K tokens)',
    save: '保存',
    cancel: '取消',
    hint: '当前模型不在价格数据库中，可手动设定价格以估算费用。',
  },
  en: {
    title: 'Custom Model Pricing',
    inputCost: 'Input Cost (USD/1K tokens)',
    outputCost: 'Output Cost (USD/1K tokens)',
    save: 'Save',
    cancel: 'Cancel',
    hint: 'This model is not in the pricing database. Set custom pricing to estimate costs.',
  },
}

interface Props {
  model: string
  onClose: () => void
}

export function CustomPricingModal({ model, onClose }: Props) {
  const language = useUiStore((s) => s.language)
  const t = text[language] ?? text.en
  const { customPricing, setCustomPricing } = useTokenStore()
  const existing = customPricing[model]
  const [inputCost, setInputCost] = useState(String(existing?.inputCost ?? '0'))
  const [outputCost, setOutputCost] = useState(String(existing?.outputCost ?? '0'))

  const handleSave = () => {
    setCustomPricing(model, parseFloat(inputCost) || 0, parseFloat(outputCost) || 0)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-background border rounded-lg p-6 w-80 space-y-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold">{t.title}</h3>
        <p className="text-xs text-muted-foreground">{t.hint}</p>
        <p className="text-xs font-mono text-muted-foreground">{model}</p>
        <div className="space-y-2">
          <label className="text-xs">{t.inputCost}</label>
          <input
            type="number"
            step="0.0001"
            value={inputCost}
            onChange={(e) => setInputCost(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs">{t.outputCost}</label>
          <input
            type="number"
            step="0.0001"
            value={outputCost}
            onChange={(e) => setOutputCost(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>{t.cancel}</Button>
          <Button size="sm" onClick={handleSave}>{t.save}</Button>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Add edit trigger in TokenUsageBar**

In `TokenUsageBar.tsx`, add a small edit icon button that opens the modal when the model is unknown:

```tsx
import { useState } from 'react'
import { Settings2 } from 'lucide-react'
import { CustomPricingModal } from './CustomPricingModal'

// Inside TokenUsageBar:
const [showPricing, setShowPricing] = useState(false)

// After the tooltip, conditionally render:
{modelInfo && !modelInfo.known && (
  <button
    onClick={() => setShowPricing(true)}
    className="text-yellow-500 hover:text-yellow-400"
    title={t.unknown}
  >
    <Settings2 className="w-3 h-3" />
  </button>
)}
{showPricing && usage?.model && (
  <CustomPricingModal model={usage.model} onClose={() => setShowPricing(false)} />
)}
```

**Step 3: Commit**

```bash
git add frontend/src/components/game/CustomPricingModal.tsx frontend/src/components/game/TokenUsageBar.tsx
git commit -m "feat(ui): add custom pricing modal for unknown models"
```

---

## Task 14: Integration Testing & Polish

End-to-end validation and cleanup.

**Step 1: Run all backend tests**

Run: `uv run pytest backend/tests/ -v --timeout=30`
Expected: All PASS

**Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

**Step 3: Run lint**

Run: `uv run ruff check backend/`
Expected: No errors (fix any that appear)

**Step 4: Manual integration test**

1. Start dev servers: `mise run dev`
2. Create a new session
3. Send a message → verify TokenUsageBar appears in header with token count
4. Send more messages → verify cumulative token count increases
5. Verify cost displays correctly
6. Verify context progress bar shows and changes color
7. Check that auto-compress plugin is enabled by default
8. In runtime settings, verify compression_threshold and keep_recent_messages appear
9. If using an unknown model, verify the custom pricing edit icon appears

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: integration testing and polish for token tracking feature"
```
