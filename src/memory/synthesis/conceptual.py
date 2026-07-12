"""LLM-generated conceptual synthesis, separate from operational reports."""

from __future__ import annotations

import json
import ast
import math
import re
from datetime import datetime
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.memory import paths as memory_paths

LLMCall = Callable[[str, str], Awaitable[str]]


def conceptual_synthesis_prompt() -> str:
    return """Sos un curador de memoria. Convertí los artefactos técnicos del día en una síntesis conceptual útil.
Jerarquía obligatoria de evidencia, de mayor a menor: (1) declaración explícita del usuario,
(2) resultado observado por una herramienta o artifact del proyecto, (3) coincidencia de varias fuentes,
(4) afirmación previa del asistente, (5) inferencia. Una afirmación del asistente NO es un hecho confirmado
por sí sola. Inferencias, análisis de mercado y lenguaje como 'probablemente', 'único' o 'nadie más' no son
memoria durable. Marcá datos históricos como históricos; no presentes versiones, cantidades, estados,
pendientes o condiciones del entorno de una fecha pasada como estado actual.
Separá hechos confirmados de hipótesis. Priorizá decisiones, cambios de estado, problemas con causa/evidencia,
preferencias durables, proyectos activos y próximos pasos explícitos. Ignorá métricas internas, scores,
IDs, rutas, palabras frecuentes, saludos, búsquedas de prueba, reintentos y ruido de herramientas. No inventes causalidad ni cierre.
No muestres razonamiento ni análisis previo. Respondé directamente JSON estricto con: overview (string), themes (lista de strings), decisions (lista),
confirmed_facts (lista), open_questions (lista), next_steps (lista), memory_candidates (lista de objetos
con key, value, evidence, confidence entre 0 y 1, evidence_type y durability).
Cada key debe usar exactamente category:kebab-case; categorías permitidas: user, bug, decision,
proyecto, patron, checkpoint. evidence_type debe ser user_statement, tool_result, project_artifact,
multi_source, assistant_statement o inference. durability debe ser durable, historical o transient.
Sólo incluyas memory_candidates con durability=durable y evidence_type distinto de assistant_statement/inference.
Si no hay actividad, indicá overview='Sin actividad conversacional'."""


_CANDIDATE_KEY = re.compile(r"^(user|bug|decision|proyecto|patron|checkpoint):[a-z0-9]+(?:-[a-z0-9]+)*$")
_TRUSTED_EVIDENCE = {"user_statement", "tool_result", "project_artifact", "multi_source"}
_TRANSIENT_PATTERNS = re.compile(
    r"\b(v\d+\.\d+|versi[oó]n|\d+\s+(tools?|herramientas|tests?|pruebas|embeddings|entradas|loc|líneas|messages)|plazo de \d+ d[ií]as|\d+[ -]day (?:deadline|timeline)|next day|al d[ií]a siguiente|antes del plazo|read[- ]only|solo lectura|probe|smoke|drill)\b",
    re.IGNORECASE,
)
_TRIVIAL_IDENTITY = re.compile(
    r"\b(aparece como|mencionad[oa] en|detectad[oa] como|es un(?:a)? usuario/persona|is (?:a )?(?:person|project) mentioned|detected as (?:a )?project)\b",
    re.IGNORECASE,
)
_OPERATIONAL_FACT = re.compile(
    r"(\b\d+ mensajes\b|\bduraci[oó]n\b|\bnuevas entidades\b|\bentidades? (?:identificadas|detectadas|extraídas)\b|\btemas extraídos\b|\bcheckpoints? de\b|\bsesiones? de tipo\b|\bprobes?\b|lan[_ -](?:field[_ -]smoke|failover[_ -]drill))",
    re.IGNORECASE,
)


def _clean_overview(text: Any) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    kept = [sentence for sentence in sentences if sentence and not _OPERATIONAL_FACT.search(sentence)]
    return " ".join(kept).strip() or "Sin hechos conceptuales durables identificados."


def validate_memory_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only durable candidates backed by primary or project evidence."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    raw_candidates = payload.get("memory_candidates")
    for raw in raw_candidates if isinstance(raw_candidates, list) else []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        value = str(raw.get("value") or "").strip()
        evidence = str(raw.get("evidence") or "").strip()
        evidence_type = str(raw.get("evidence_type") or "").strip()
        durability = str(raw.get("durability") or "").strip()
        reason = ""
        if not _CANDIDATE_KEY.fullmatch(key):
            reason = "invalid_key"
        elif not value or not evidence:
            reason = "missing_evidence"
        elif len(re.findall(r"\w+", value, flags=re.UNICODE)) < 4:
            reason = "trivial_value"
        elif evidence_type not in _TRUSTED_EVIDENCE:
            reason = "untrusted_evidence"
        elif durability != "durable":
            reason = "not_durable"
        elif _TRANSIENT_PATTERNS.search(value):
            reason = "transient_metric_or_environment"
        elif _TRIVIAL_IDENTITY.search(value):
            reason = "trivial_identity_or_entity_detection"
        if reason:
            rejected.append({"key": key, "reason": reason})
            continue
        try:
            confidence_value = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            rejected.append({"key": key, "reason": "invalid_confidence"})
            continue
        if not math.isfinite(confidence_value):
            rejected.append({"key": key, "reason": "invalid_confidence"})
            continue
        confidence = max(0.0, min(1.0, confidence_value))
        caps = {"user_statement": 0.95, "tool_result": 0.98, "project_artifact": 0.9, "multi_source": 0.95}
        accepted.append({**raw, "key": key, "value": value, "evidence": evidence, "confidence": round(min(confidence, caps[evidence_type]), 2)})
    facts = payload.get("confirmed_facts") if isinstance(payload.get("confirmed_facts"), list) else []
    clean_facts = [
        fact for fact in facts
        if isinstance(fact, str)
        and not _TRANSIENT_PATTERNS.search(fact)
        and not _TRIVIAL_IDENTITY.search(fact)
        and not _OPERATIONAL_FACT.search(fact)
    ]
    return {
        **payload,
        "overview": _clean_overview(payload.get("overview")),
        "confirmed_facts": clean_facts,
        "memory_candidates": accepted,
        "rejected_memory_candidates": rejected,
    }


async def _default_llm_call(system: str, user: str) -> str:
    from src.llm.client import chat
    response = await chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=16384,
        stream=False,
    )
    message = getattr(response, "message", None)
    if message is not None:
        return str(
            getattr(message, "content", None)
            or getattr(message, "reasoning_content", None)
            or ""
        )
    if hasattr(response, "content"):
        return str(response.content or getattr(response, "reasoning", None) or "")
    if isinstance(response, dict):
        return str(response.get("choices", [{}])[0].get("message", {}).get("content", ""))
    return str(response or "")


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    if not text.startswith("{") and "{" in text and "}" in text:
        text = text[text.find("{") : text.rfind("}") + 1]
    # Some reasoning providers serialize the final JSON block with literal
    # newline escapes outside strings instead of returning the block itself.
    if text.startswith("{\\n"):
        text = text.replace("\\n", "\n")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = ast.literal_eval(text)
    if not isinstance(payload, dict):
        raise ValueError("conceptual synthesis must be a JSON object")
    return payload


def render_conceptual_synthesis(payload: dict[str, Any], target: date) -> str:
    lines = [f"# Síntesis conceptual — {target.isoformat()}", "", "## Panorama", "", str(payload.get("overview") or "Sin síntesis conceptual."), ""]
    sections = (("Temas", "themes"), ("Decisiones registradas ese día", "decisions"), ("Hechos confirmados para esa fecha", "confirmed_facts"), ("Preguntas abiertas de esa fecha", "open_questions"), ("Próximos pasos registrados ese día", "next_steps"))
    for title, key in sections:
        lines.extend([f"## {title}", ""])
        values = payload.get(key) if isinstance(payload.get(key), list) else []
        lines.extend([f"- {value}" for value in values] or ["- Ninguno identificado."])
        lines.append("")
    lines.extend(["## Candidatos de memoria", ""])
    candidates = payload.get("memory_candidates") if isinstance(payload.get("memory_candidates"), list) else []
    for item in candidates:
        if isinstance(item, dict):
            lines.append(f"- `{item.get('key', '')}`: {item.get('value', '')} (confianza: {item.get('confidence', 0)})")
            lines.append(f"  - Fuente: {item.get('evidence_type', '')}; durabilidad: {item.get('durability', '')}")
            if item.get("evidence"):
                lines.append(f"  - Evidencia: {item['evidence']}")
    if not candidates:
        lines.append("- Ninguno identificado.")
    return "\n".join(lines).rstrip() + "\n"


async def generate_conceptual_synthesis(
    target_date: date | None = None,
    root: str | Path | None = None,
    llm_call_fn: LLMCall | None = None,
) -> str:
    project_root = Path(root) if root is not None else memory_paths._project_root()
    target = target_date or memory_paths._default_target_date()
    daily = memory_paths.daily_path(target, project_root)
    transversal = memory_paths.transversal_path(target, project_root)
    inputs = []
    for path in (daily, transversal):
        if path.exists():
            inputs.append(f"## {path.name}\n{path.read_text(encoding='utf-8', errors='replace')}")
    user = "\n\n".join(inputs).strip()
    if not user or "**Messages**: 0" in user and "Sessions: 0" in user:
        attempts = 0
        payload = {"overview": "Sin actividad conversacional", "themes": [], "decisions": [], "confirmed_facts": [], "open_questions": [], "next_steps": [], "memory_candidates": []}
    else:
        caller = llm_call_fn or _default_llm_call
        last_error: Exception | None = None
        attempts = 0
        for _attempt in range(2):
            attempts = _attempt + 1
            try:
                raw = await caller(conceptual_synthesis_prompt(), user[:24000])
                payload = validate_memory_candidates(_parse_json(raw))
                break
            except Exception as exc:
                last_error = exc
        else:
            status_path = memory_paths.conceptual_status_path(target, project_root)
            status_path.write_text(json.dumps({
                "date": target.isoformat(), "status": "generation_failed",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "error": type(last_error).__name__ if last_error else "unknown",
                "attempts": attempts,
                "preserved_previous": memory_paths.conceptual_path(target, project_root).exists(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            raise ValueError("LLM returned no valid conceptual JSON after 2 attempts") from last_error
    path = memory_paths.conceptual_path(target, project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_conceptual_synthesis(payload, target), encoding="utf-8")
    memory_paths.conceptual_json_path(target, project_root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    memory_paths.conceptual_status_path(target, project_root).write_text(
        json.dumps({"date": target.isoformat(), "status": "current", "updated_at": datetime.now().isoformat(timespec="seconds"), "error": "", "attempts": attempts, "preserved_previous": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)
