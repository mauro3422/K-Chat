#!/usr/bin/env python3
"""Run repeatable, non-mutating curator quality probes across Kairos nodes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import statistics
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def export_bundle(*, limit: int, days: int) -> dict[str, Any]:
    """Freeze prompts from one corpus so every node receives identical input."""
    from src.memory.curator.curate import CURATOR_PROMPT, _get_memory_context
    from src.memory.db_path import resolve_db_path
    from src.memory.memory_db_path import resolve_memory_db_path

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with sqlite3.connect(resolve_db_path()) as conn:
        sessions = conn.execute(
            "SELECT session_id, name, created_at FROM sessions "
            "WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (cutoff, max(limit * 8, limit)),
        ).fetchall()

    cases: list[dict[str, Any]] = []
    with sqlite3.connect(resolve_memory_db_path()) as conn:
        for session_id, name, created_at in sessions:
            rows = conn.execute(
                "SELECT text FROM vec_meta WHERE source='session' "
                "AND source_key=? AND length(text)>30 "
                "ORDER BY exchange_idx DESC LIMIT 8",
                (session_id,),
            ).fetchall()
            texts = [str(row[0])[:400] for row in rows if row[0]]
            if not texts:
                continue
            prompt = (
                f"Session: {name or str(session_id)[:12]}\n\n"
                + "\n---\n".join(texts)
                + "\n\nExtract new info or NO_NEW_INFO"
            )
            cases.append(
                {
                    "case_id": _json_digest({"session_id": session_id, "prompt": prompt})[:16],
                    "session_id": str(session_id),
                    "created_at": str(created_at or ""),
                    "prompt": prompt,
                    "exchange_count": len(texts),
                }
            )
            if len(cases) >= limit:
                break

    context = _get_memory_context()
    bundle = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "current_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "curator_prompt": CURATOR_PROMPT,
        "system_prompt": f"EXISTING MEMORIES:\n{context}\n\n{CURATOR_PROMPT}",
        "cases": cases,
    }
    bundle["bundle_id"] = _json_digest(bundle)[:16]
    return bundle


def _response_content(response: Any) -> str:
    message = getattr(response, "message", None)
    if message is not None:
        return str(getattr(message, "content", "") or "")
    if isinstance(response, dict):
        return str(response.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
    return str(response or "")


def system_prompt_variant(system_prompt: str, variant: str) -> str:
    if variant == "baseline":
        return system_prompt
    if variant != "strict":
        raise ValueError(f"unknown prompt variant: {variant}")
    return (
        system_prompt
        + "\n\nSTRICT OUTPUT CONTRACT:\n"
        + "- Return at most 4 items and only facts explicitly supported by the exchanges.\n"
        + "- Never infer status, causality, completion, dates, or intent.\n"
        + "- Prefer decisions, confirmed bugs, durable user preferences, and active projects.\n"
        + "- Use one canonical lowercase kebab-case key per fact, without spaces or underscores.\n"
        + "- Emit exactly two lines per item: KEY: <category:slug> then VALUE: <timestamp | fact>.\n"
        + "- Do not add bullets, headings, commentary, Markdown fences, or explanations.\n"
        + "- If no explicit durable fact exists, return exactly NO_NEW_INFO."
    )


def _contextual_system_prompt(
    bundle: dict[str, Any],
    case: dict[str, Any],
    provisional_entries: list[dict[str, Any]],
    *,
    strict: bool,
) -> str:
    blocks = [f"CURRENT DATE: {bundle.get('current_date') or datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    relevant_context = str(case.get("relevant_context") or "").strip()
    if relevant_context:
        blocks.append(f"EXISTING MEMORIES:\n{relevant_context}")
    if provisional_entries:
        lines = ["PROVISIONAL EXTRACTIONS FROM THIS BATCH (not yet committed):"]
        lines.extend(
            f"- {entry.get('key', '')}: {entry.get('value', '')}"
            for entry in provisional_entries
        )
        blocks.append("\n".join(lines)[:2500])
    blocks.append(str(bundle.get("curator_prompt") or "You are a memory curator."))
    prompt = "\n\n".join(blocks)
    return system_prompt_variant(prompt, "strict") if strict else prompt


async def enrich_bundle_context(
    bundle: dict[str, Any],
    retriever: Any | None = None,
) -> dict[str, Any]:
    if retriever is None:
        from src.memory.curator.context_retrieval import HybridCuratorContextRetriever
        from src.memory.memory_db_path import resolve_memory_db_path
        from src.memory.operations._helpers import _get_memory_md_path

        retriever = HybridCuratorContextRetriever(
            resolve_memory_db_path(),
            _get_memory_md_path(),
        )
    enriched = {**bundle, "cases": [dict(case) for case in bundle.get("cases", [])]}
    for case in enriched["cases"]:
        case["relevant_context"] = await retriever.retrieve(
            str(case.get("prompt") or ""),
            session_id=str(case.get("session_id") or ""),
        )
    enriched.pop("bundle_id", None)
    enriched["bundle_id"] = _json_digest(enriched)[:16]
    return enriched


async def _run_call(system_prompt: str, user_prompt: str, model: str, temperature: float) -> dict[str, Any]:
    from src.llm.client import chat
    from src.memory.curator.curate import parse_resp
    from src.memory.curator.entry_filter import filter_curator_entries

    started = time.monotonic()
    try:
        response = await chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=temperature,
            max_tokens=16384,
            stream=False,
        )
        content = _response_content(response)
        no_new_info = "NO_NEW_INFO" in content
        parsed = [] if no_new_info else parse_resp(content)
        filtered, stats = filter_curator_entries(parsed)
        return {
            "ok": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "no_new_info": no_new_info,
            "malformed": bool(content.strip()) and not no_new_info and not parsed,
            "response_digest": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            "response_text": content,
            "parsed_entries": parsed,
            "kept_entries": filtered,
            "filter_stats": stats,
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
            "parsed_entries": [],
            "kept_entries": [],
            "filter_stats": {"input": 0, "kept": 0, "trivial": 0, "duplicates": 0},
        }


def summarize_results(calls: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(call["elapsed_ms"]) for call in calls if call.get("ok")]
    return {
        "calls": len(calls),
        "successful": sum(bool(call.get("ok")) for call in calls),
        "failed": sum(not bool(call.get("ok")) for call in calls),
        "no_new_info": sum(bool(call.get("no_new_info")) for call in calls),
        "malformed": sum(bool(call.get("malformed")) for call in calls),
        "parsed_entries": sum(len(call.get("parsed_entries", [])) for call in calls),
        "kept_entries": sum(len(call.get("kept_entries", [])) for call in calls),
        "trivial_removed": sum(int(call.get("filter_stats", {}).get("trivial", 0)) for call in calls),
        "duplicates_removed": sum(int(call.get("filter_stats", {}).get("duplicates", 0)) for call in calls),
        "invalid_categories_removed": sum(
            int(call.get("filter_stats", {}).get("invalid_category", 0)) for call in calls
        ),
        "latency_mean_ms": round(statistics.mean(latencies)) if latencies else 0,
        "latency_median_ms": round(statistics.median(latencies)) if latencies else 0,
        "latency_max_ms": round(max(latencies)) if latencies else 0,
    }


async def run_bundle(
    bundle: dict[str, Any],
    *,
    model: str,
    repeats: int,
    node: str,
    temperature: float = 0.3,
    prompt_variant: str = "baseline",
) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    contextual = prompt_variant in {"contextual", "contextual-strict"}
    system_prompt = ""
    if not contextual:
        system_prompt = system_prompt_variant(str(bundle["system_prompt"]), prompt_variant)
    for repeat in range(repeats):
        provisional_entries: list[dict[str, Any]] = []
        for case in bundle.get("cases", []):
            call_system_prompt = system_prompt
            if contextual:
                call_system_prompt = _contextual_system_prompt(
                    bundle,
                    case,
                    provisional_entries,
                    strict=prompt_variant == "contextual-strict",
                )
            result = await _run_call(
                call_system_prompt,
                str(case["prompt"]),
                model,
                temperature,
            )
            result.update({"case_id": case["case_id"], "repeat": repeat})
            calls.append(result)
            if contextual and result.get("kept_entries"):
                from src.memory.curator.entry_filter import filter_curator_entries

                provisional_entries, _ = filter_curator_entries(
                    [*provisional_entries, *result["kept_entries"]]
                )
    return {
        "schema_version": 1,
        "bundle_id": bundle.get("bundle_id", ""),
        "node": node,
        "model": model,
        "temperature": temperature,
        "prompt_variant": prompt_variant,
        "repeats": repeats,
        "summary": summarize_results(calls),
        "calls": calls,
    }


def _key_set(call: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("key") or "").strip().lower()
        for entry in call.get("kept_entries", [])
        if str(entry.get("key") or "").strip()
    }


def _key_tokens(entry: dict[str, Any]) -> set[str]:
    key = str(entry.get("key") or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode("ascii")
    return {token for token in "".join(char if char.isalnum() else " " for char in normalized).split() if token}


def _entry_key_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = _key_tokens(left)
    right_tokens = _key_tokens(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 1.0


def _call_key_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_entries = list(left.get("kept_entries", []))
    right_entries = list(right.get("kept_entries", []))
    if not left_entries and not right_entries:
        return 1.0
    if not left_entries or not right_entries:
        return 0.0
    left_scores = [max(_entry_key_similarity(entry, other) for other in right_entries) for entry in left_entries]
    right_scores = [max(_entry_key_similarity(entry, other) for entry in left_entries) for other in right_entries]
    return statistics.mean([*left_scores, *right_scores])


def repeat_consistency(calls: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        grouped.setdefault(str(call.get("case_id") or ""), []).append(call)
    similarities: list[float] = []
    for case_calls in grouped.values():
        ordered = sorted(case_calls, key=lambda item: int(item.get("repeat") or 0))
        for index, call in enumerate(ordered):
            for other in ordered[index + 1 :]:
                similarities.append(_call_key_similarity(call, other))
    return {
        "repeat_pairs": len(similarities),
        "key_token_similarity_mean": round(statistics.mean(similarities), 4) if similarities else 0.0,
    }


def compare_runs(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if left.get("bundle_id") != right.get("bundle_id"):
        raise ValueError("runs use different bundles")
    right_calls = {
        (call.get("case_id"), call.get("repeat")): call for call in right.get("calls", [])
    }
    similarities: list[float] = []
    token_similarities: list[float] = []
    matched = 0
    for call in left.get("calls", []):
        other = right_calls.get((call.get("case_id"), call.get("repeat")))
        if other is None:
            continue
        matched += 1
        left_keys = _key_set(call)
        right_keys = _key_set(other)
        union = left_keys | right_keys
        similarities.append(len(left_keys & right_keys) / len(union) if union else 1.0)
        token_similarities.append(_call_key_similarity(call, other))
    return {
        "bundle_id": left.get("bundle_id", ""),
        "left_node": left.get("node", ""),
        "right_node": right.get("node", ""),
        "matched_calls": matched,
        "key_jaccard_mean": round(statistics.mean(similarities), 4) if similarities else 0.0,
        "key_token_similarity_mean": round(statistics.mean(token_similarities), 4) if token_similarities else 0.0,
        "left_repeat_consistency": repeat_consistency(list(left.get("calls", []))),
        "right_repeat_consistency": repeat_consistency(list(right.get("calls", []))),
        "left_summary": left.get("summary", {}),
        "right_summary": right.get("summary", {}),
    }


def _read_json(path: str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run controlled curator quality probes without mutating memory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="Freeze recent session prompts into a bundle.")
    export.add_argument("--output", required=True)
    export.add_argument("--limit", type=int, default=3)
    export.add_argument("--days", type=int, default=90)

    enrich = subparsers.add_parser("enrich", help="Attach relevant canonical context to each frozen case.")
    enrich.add_argument("--bundle", required=True)
    enrich.add_argument("--output", required=True)

    run = subparsers.add_parser("run", help="Run a frozen bundle through one model.")
    run.add_argument("--bundle", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--node", required=True)
    run.add_argument("--model", default="deepseek-v4-flash")
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--temperature", type=float, default=0.3)
    run.add_argument(
        "--prompt-variant",
        choices=("baseline", "strict", "contextual", "contextual-strict"),
        default="baseline",
    )

    compare = subparsers.add_parser("compare", help="Compare two runs of the same bundle.")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--output", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "export":
        payload = export_bundle(limit=max(1, args.limit), days=max(1, args.days))
        _write_json(args.output, payload)
        print(json.dumps({"bundle_id": payload["bundle_id"], "cases": len(payload["cases"])}))
        return 0 if payload["cases"] else 2
    if args.command == "enrich":
        payload = asyncio.run(enrich_bundle_context(_read_json(args.bundle)))
        _write_json(args.output, payload)
        print(
            json.dumps(
                {
                    "bundle_id": payload["bundle_id"],
                    "cases": len(payload["cases"]),
                    "context_chars": sum(
                        len(str(case.get("relevant_context") or "")) for case in payload["cases"]
                    ),
                }
            )
        )
        return 0
    if args.command == "run":
        payload = asyncio.run(
            run_bundle(
                _read_json(args.bundle),
                model=args.model,
                repeats=max(1, args.repeats),
                node=args.node,
                temperature=args.temperature,
                prompt_variant=args.prompt_variant,
            )
        )
        _write_json(args.output, payload)
        print(json.dumps(payload["summary"]))
        return 0 if not payload["summary"]["failed"] else 2

    payload = compare_runs(_read_json(args.left), _read_json(args.right))
    if args.output:
        _write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
