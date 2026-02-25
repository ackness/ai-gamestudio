"""Test that LLM call data flows into message metadata."""
import json
from backend.app.services.chat_service import _merge_blocks_into_metadata


def test_merge_blocks_with_llm_calls():
    llm_calls = {
        "narrative": {
            "messages": [{"role": "system", "content": "test"}],
            "response": "hello",
            "model": "test-model",
            "tokens": {"prompt": 100, "completion": 50},
        },
    }
    result = _merge_blocks_into_metadata(None, "msg-1", [], llm_calls=llm_calls)
    parsed = json.loads(result)
    assert "llm_calls" in parsed
    assert parsed["llm_calls"]["narrative"]["model"] == "test-model"
    assert parsed["llm_calls"]["narrative"]["response"] == "hello"


def test_merge_blocks_without_llm_calls():
    result = _merge_blocks_into_metadata(None, "msg-1", [{"type": "test"}])
    parsed = json.loads(result)
    assert "blocks" in parsed
    assert "llm_calls" not in parsed


def test_merge_preserves_existing_metadata():
    existing = json.dumps({"custom": "data"})
    result = _merge_blocks_into_metadata(existing, "msg-1", [], llm_calls={"narrative": {}})
    parsed = json.loads(result)
    assert parsed["custom"] == "data"
    assert "llm_calls" in parsed
