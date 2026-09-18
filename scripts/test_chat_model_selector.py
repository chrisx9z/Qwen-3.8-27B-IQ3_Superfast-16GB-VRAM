from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.llm_settings import (
    get_llm_settings,
    save_llm_settings,
    get_verified_models,
    set_active_provider_and_model,
)

def test_model_selector_logic():
    print("=== TEST 1: Default state ===")
    initial = get_llm_settings()
    verified_initial = get_verified_models()
    print(f"Verified count: {len(verified_initial)}")
    assert len(verified_initial) >= 1
    assert verified_initial[0]["id"] == "local"
    assert verified_initial[0]["is_default"] is True
    assert "Qwen" in verified_initial[0]["display_name"]
    print("PASS: Qwen is default model.")

    print("\n=== TEST 2: Unverified provider with key is excluded ===")
    providers = dict(initial.get("providers") or {})
    # Simulate adding an OpenAI key without testing/verifying
    providers["openai"] = {
        "model": "gpt-4o",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": "sk-unverified-test-key",
        "verified": False,
    }
    save_llm_settings(
        provider="local",
        model="qwen38_iq3s",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        api_key="",
        providers_map=providers,
    )
    verified = get_verified_models()
    openai_in_verified = any(m["id"] == "openai" for m in verified)
    assert not openai_in_verified, "Unverified provider should NOT appear in verified models!"
    print("PASS: Unverified provider excluded.")

    print("\n=== TEST 3: Verified provider with key is included ===")
    # Now simulate successful test
    providers["openai"]["verified"] = True
    save_llm_settings(
        provider="local",
        model="qwen38_iq3s",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        api_key="",
        providers_map=providers,
    )
    verified = get_verified_models()
    openai_in_verified = any(m["id"] == "openai" for m in verified)
    assert openai_in_verified, "Verified provider MUST appear in verified models!"
    openai_item = next(m for m in verified if m["id"] == "openai")
    print(f"Found verified model: {openai_item['display_name']}")
    print("PASS: Verified provider included.")

    print("\n=== TEST 4: Switching active model ===")
    set_active_provider_and_model("openai", "gpt-4o")
    current = get_llm_settings()
    assert current["llm_provider"] == "openai"
    assert current["llm_model"] == "gpt-4o"
    print("PASS: Active model switched to openai / gpt-4o.")

    # Reset back to local
    set_active_provider_and_model("local", "qwen38_iq3s")
    # Clean up test openai key
    providers["openai"] = {
        "model": "gpt-4o",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key": "",
        "verified": False,
    }
    save_llm_settings(
        provider="local",
        model="qwen38_iq3s",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        api_key="",
        providers_map=providers,
    )
    reset = get_llm_settings()
    assert reset["llm_provider"] == "local"
    assert len(get_verified_models()) == 1
    print("PASS: Cleaned up and reset to default Local Qwen.")

    print("\n=== ALL TESTS PASSED! ===")

if __name__ == "__main__":
    test_model_selector_logic()
