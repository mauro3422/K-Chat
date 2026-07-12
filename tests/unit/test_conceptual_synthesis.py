from datetime import date

import pytest

from src.memory.synthesis.conceptual import generate_conceptual_synthesis, validate_memory_candidates


@pytest.mark.anyio
async def test_conceptual_synthesis_is_separate_and_ignores_operational_shape(tmp_path):
    day = tmp_path / "memory" / "2026" / "07" / "04"
    day.mkdir(parents=True)
    (day / "daily.md").write_text(
        "# Daily Synthesis\n\n**Messages**: 12\n\n- decisión: mantener revisión humana",
        encoding="utf-8",
    )
    (day / "transversal.md").write_text("# Transversal\n\n- memoria", encoding="utf-8")

    async def llm(system, user):
        assert "Ignorá métricas internas" in system
        assert "daily.md" in user
        return '{"overview":"Se decidió conservar revisión humana.","themes":["memoria"],"decisions":["Conservar revisión humana"],"confirmed_facts":[],"open_questions":[],"next_steps":["Etiquetar candidatos"],"memory_candidates":[]}'

    result = await generate_conceptual_synthesis(date(2026, 7, 4), root=tmp_path, llm_call_fn=llm)
    text = (day / "conceptual.md").read_text(encoding="utf-8")
    assert result.endswith("conceptual.md")
    assert "Se decidió conservar revisión humana" in text
    assert "Etiquetar candidatos" in text


@pytest.mark.anyio
async def test_conceptual_synthesis_skips_llm_when_day_has_no_activity(tmp_path):
    day = tmp_path / "memory" / "2026" / "07" / "10"
    day.mkdir(parents=True)
    (day / "daily.md").write_text("**Messages**: 0", encoding="utf-8")
    (day / "transversal.md").write_text("Sessions: 0", encoding="utf-8")

    async def llm(_system, _user):
        raise AssertionError("LLM should not run for an empty day")

    await generate_conceptual_synthesis(date(2026, 7, 10), root=tmp_path, llm_call_fn=llm)
    assert "Sin actividad conversacional" in (day / "conceptual.md").read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_conceptual_synthesis_defaults_target_date_when_none(tmp_path, monkeypatch):
    day = tmp_path / "memory" / "2026" / "07" / "08"
    day.mkdir(parents=True)
    (day / "daily.md").write_text("**Messages**: 1", encoding="utf-8")
    (day / "transversal.md").write_text("Sessions: 1", encoding="utf-8")

    monkeypatch.setattr(
        "src.memory.synthesis.conceptual.memory_paths._default_target_date",
        lambda: date(2026, 7, 8),
    )

    async def llm(_system, _user):
        return '{"overview":"Síntesis conceptual por defecto.","themes":[],"decisions":[],"confirmed_facts":[],"open_questions":[],"next_steps":[],"memory_candidates":[]}'

    result = await generate_conceptual_synthesis(None, root=tmp_path, llm_call_fn=llm)

    assert result == str(day / "conceptual.md")
    assert "Síntesis conceptual por defecto." in (day / "conceptual.md").read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_conceptual_failure_preserves_previous_and_writes_status(tmp_path):
    day = tmp_path / "memory" / "2026" / "07" / "04"
    day.mkdir(parents=True)
    (day / "daily.md").write_text("**Messages**: 2", encoding="utf-8")
    (day / "transversal.md").write_text("Sessions: 1", encoding="utf-8")
    (day / "conceptual.md").write_text("previous", encoding="utf-8")

    async def invalid(_system, _user):
        return ""

    with pytest.raises(ValueError, match="no valid conceptual JSON"):
        await generate_conceptual_synthesis(date(2026, 7, 4), root=tmp_path, llm_call_fn=invalid)
    assert (day / "conceptual.md").read_text(encoding="utf-8") == "previous"
    status = __import__("json").loads((day / "conceptual.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "generation_failed"
    assert status["preserved_previous"] is True


def test_candidate_validation_rejects_assistant_inference_transient_metrics_and_bad_keys():
    payload = {
        "memory_candidates": [
            {"key": "bug:duplicacion-mensajes", "value": "Se observaron POST duplicados.", "evidence": "Log del servidor", "confidence": 1, "evidence_type": "tool_result", "durability": "durable"},
            {"key": "market_position", "value": "Kairos es único en el mercado.", "evidence": "Lo dijo el asistente", "confidence": 1, "evidence_type": "assistant_statement", "durability": "durable"},
            {"key": "checkpoint:version", "value": "K-Chat v0.0.57 tiene 26 herramientas y 240 tests.", "evidence": "Reporte antiguo", "confidence": 1, "evidence_type": "project_artifact", "durability": "durable"},
            {"key": "patron:interes-linux", "value": "Mauro tiene interés en Linux.", "evidence": "Inferido de una búsqueda de prueba", "confidence": 0.6, "evidence_type": "inference", "durability": "durable"},
            {"key": "user:mauro-persona", "value": "Mauro aparece como persona mencionada en la sesión.", "evidence": "Detector de entidades", "confidence": 0.9, "evidence_type": "project_artifact", "durability": "durable"},
            {"key": "checkpoint:lan-smoke", "value": "Probe smoke LAN ejecutado el día indicado.", "evidence": "Log", "confidence": 0.9, "evidence_type": "tool_result", "durability": "durable"},
            {"key": "user:language", "value": "es", "evidence": "Saludo hola", "confidence": 0.9, "evidence_type": "user_statement", "durability": "durable"},
        ]
    }
    result = validate_memory_candidates(payload)
    assert [item["key"] for item in result["memory_candidates"]] == ["bug:duplicacion-mensajes"]
    assert result["memory_candidates"][0]["confidence"] == 0.98
    assert {item["reason"] for item in result["rejected_memory_candidates"]} == {
        "invalid_key", "transient_metric_or_environment", "untrusted_evidence", "trivial_identity_or_entity_detection", "trivial_value"
    }


def test_candidate_validation_requires_durable_primary_evidence():
    result = validate_memory_candidates({"memory_candidates": [
        {"key": "decision:timer-curador", "value": "Se discutió crear un timer.", "evidence": "Sesión histórica", "confidence": 0.9, "evidence_type": "user_statement", "durability": "historical"},
        {"key": "user:accountability-tps", "value": "Mauro pidió ayuda activa con sus TPs.", "evidence": "Declaración explícita de Mauro", "confidence": 1, "evidence_type": "user_statement", "durability": "durable"},
    ]})
    assert [item["key"] for item in result["memory_candidates"]] == ["user:accountability-tps"]
    assert result["memory_candidates"][0]["confidence"] == 0.95


def test_candidate_validation_removes_operational_facts():
    result = validate_memory_candidates({
        "confirmed_facts": [
            "La sesión tuvo 115 mensajes y duración de 19 minutos.",
            "Se detectaron nuevas entidades: Mauro y K-Chat.",
            "Mauro decidió formalizar la entrada temporal de recuerdos.",
        ],
        "memory_candidates": [],
    })
    assert result["confirmed_facts"] == ["Mauro decidió formalizar la entrada temporal de recuerdos."]


def test_candidate_validation_rejects_expired_deadlines_and_cleans_overview():
    result = validate_memory_candidates({
        "overview": "Se discutió memoria. Se ejecutaron probes LAN field smoke.",
        "confirmed_facts": [],
        "memory_candidates": [{
            "key": "user:timeline-10-days", "value": "El usuario estableció un plazo de 10 días.",
            "evidence": "Declaración del usuario", "confidence": 0.95,
            "evidence_type": "user_statement", "durability": "durable",
        }],
    })
    assert result["overview"] == "Se discutió memoria."
    assert result["memory_candidates"] == []
