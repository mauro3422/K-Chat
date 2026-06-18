import json

import pytest

from web.services import model_catalog


@pytest.mark.anyio
async def test_format_model_label_falls_back_to_id(monkeypatch):
    monkeypatch.setattr(model_catalog, "_load_registry", lambda: {})
    assert model_catalog.format_model_label("unknown-model") == "unknown-model"


@pytest.mark.anyio
async def test_format_model_label_uses_registry(tmp_path, monkeypatch):
    registry = tmp_path / "model_registry.json"
    registry.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "sample-model",
                        "name": "Sample Model",
                        "limit": {"context": 1000000, "output": 128000},
                        "capabilities": {
                            "attachment": True,
                            "reasoning": True,
                            "toolcall": True,
                            "temperature": True,
                            "input": {"text": True, "image": True, "audio": False, "video": True, "pdf": False},
                            "output": {"text": True, "image": False, "audio": False, "video": False, "pdf": False},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KAIROS_MODEL_REGISTRY", str(registry))
    model_catalog._load_registry.cache_clear()

    label = model_catalog.format_model_label("sample-model")
    assert label == "Sample Model · ctx 1M · out 128k · img+video · razonamiento · tools"


@pytest.mark.anyio
async def test_reset_model_cache_clears_lru_cache(tmp_path, monkeypatch):
    registry = tmp_path / "model_registry.json"
    registry.write_text(json.dumps({"models": []}), encoding="utf-8")
    monkeypatch.setenv("KAIROS_MODEL_REGISTRY", str(registry))
    model_catalog._load_registry.cache_clear()
    assert model_catalog.get_model_metadata("missing") is None
    model_catalog.reset_model_cache()
    assert model_catalog.get_model_metadata("missing") is None
