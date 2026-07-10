from __future__ import annotations

import logging
import math
import sqlite3
import json
from typing import Any

from src.memory.analysis.corpus import STOP
from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


SPANISH_STOPWORDS = {
    "para", "como", "con", "los", "las", "este", "esta", "estos", "estas", "una", "uno",
    "unos", "unas", "del", "al", "por", "que", "hacer", "sistema", "usar", "hablemos", "como"
}


# ── Spanish Stemming ─────────────────────────────────────────────────────────

def stem_spanish(word: str) -> str:
    """Lightweight Spanish stemmer — rule-based suffix stripping.

    Groups morphological variants without embeddings or KNN.
    Handles: plurals (-s/-es), gerunds (-ando/-iendo), participles (-ado/-ido),
    common verb endings, and adverbs (-mente).

    Designed to be fast (no DB, no vectors) and conservative (won't over-stem).
    """
    w = word.lower()

    # Don't stem very short words
    if len(w) <= 3:
        return w

    # Adverbs: rápidamente → rápido
    if w.endswith('mente') and len(w) > 6:
        w = w[:-5]

    # Gerunds: hablando → hablar, corriendo → correr
    if w.endswith('iendo') and len(w) > 6:
        w = w[:-5] + 'er'  # most -iendo verbs are -er/-ir
    elif w.endswith('ando') and len(w) > 6:
        w = w[:-4] + 'ar'

    # Participles: hablado → hablar, comido → comer
    if w.endswith('ado') and len(w) > 5:
        w = w[:-3] + 'ar'
    elif w.endswith('ido') and len(w) > 5:
        w = w[:-3] + 'ir'

    # Plurals: herramientas → herramienta, cosas → cosa
    if w.endswith('es') and len(w) > 4:
        w = w[:-2]
    elif w.endswith('s') and len(w) > 3:
        w = w[:-1]

    # Feminine/masculine normalization: arquitectónico → arquitectónic
    if w.endswith('ico') and len(w) > 5:
        w = w[:-3] + 'ic'
    elif w.endswith('ica') and len(w) > 5:
        w = w[:-3] + 'ic'
    elif w.endswith('ivo') and len(w) > 5:
        w = w[:-3] + 'iv'
    elif w.endswith('iva') and len(w) > 5:
        w = w[:-3] + 'iv'
    elif w.endswith('oso') and len(w) > 5:
        w = w[:-3] + 'os'
    elif w.endswith('osa') and len(w) > 5:
        w = w[:-3] + 'os'

    # Diminutives: poquito → poco
    if w.endswith('ito') and len(w) > 5:
        w = w[:-3]
    elif w.endswith('ita') and len(w) > 5:
        w = w[:-3]
    elif w.endswith('illo') and len(w) > 6:
        w = w[:-4]

    return w


# ── Canonicalization (now just stemming) ─────────────────────────────────────

def canonicalize_tokens(
    tokens: list[str],
    distance_threshold: float = 0.25,
) -> list[str]:
    """Apply Spanish stemming to tokens. (distance_threshold kept for API compat, ignored)"""
    return [stem_spanish(t) for t in tokens]


# ── PMI Calculation ──────────────────────────────────────────────────────────

def calculate_pmi_for_session(
    messages: list[str],
    window_size: int = 5,
    min_cooccurrences: int = 1,
    pmi_threshold: float = 0.5,
    word_idf: dict[str, float] | None = None,
    max_idf: float = 2.0,
    stem_map: dict[str, str] | None = None,
    # Legacy params — kept for API compat, ignored
    global_df: dict[str, int] | None = None,
    total_sessions: int = 1,
    term_entropy: dict[str, float] | None = None,
    entropy_hard_threshold: float = 0.95,
    entropy_soft_start: float = 0.55,
    canonical_map: dict[str, str] | None = None,
) -> tuple[list[tuple[str, str, float]], set[tuple[str, str]]]:
    """Calculate PMI for terms in a session using IDF weighting + stemming.

    Returns:
        (filtered_relations, candidate_pairs)
        - filtered_relations: list of (stem_a, stem_b, weight) that pass PMI threshold
        - candidate_pairs: set of all (stem_a, stem_b) pairs found (for edge-IDF computation)

    Weight formula:
        weight = raw_pmi_weight × min(idf_a, idf_b) / max_idf

    IDF naturally penalizes words that appear in many sessions (stopwords)
    while preserving domain-specific concepts that may also be frequent.

    The stemming groups morphological variants (plural, gerund, etc.)
    so IDF is computed on stems, not raw forms.
    """
    # Use stem_map if provided, otherwise fall back to canonical_map for compat
    effective_map = stem_map or canonical_map

    session_windows: list[set[str]] = []
    word_counts: dict[str, int] = {}
    cooc_counts: dict[tuple[str, str], int] = {}

    for msg in messages:
        clean_msg = (
            msg.replace(",", " ")
            .replace(".", " ")
            .replace("?", " ")
            .replace(":", " ")
            .replace('"', " ")
            .replace("'", " ")
        )
        tokens = []
        for word in clean_msg.split():
            t = word.strip().lower()
            if t not in STOP and t not in SPANISH_STOPWORDS and len(t) > 2 and t.isalpha():
                # Map to stem (or canonical form for compat)
                if effective_map is not None:
                    stem = effective_map.get(t, t)
                else:
                    stem = stem_spanish(t)
                tokens.append(stem)

        if tokens:
            for i in range(max(1, len(tokens) - window_size + 1)):
                window = set(tokens[i : i + window_size])
                session_windows.append(window)
                for w in window:
                    word_counts[w] = word_counts.get(w, 0) + 1

                window_list = list(window)
                for j in range(len(window_list)):
                    for k in range(j + 1, len(window_list)):
                        a, b = sorted([window_list[j], window_list[k]])
                        cooc_counts[(a, b)] = cooc_counts.get((a, b), 0) + 1

    total_windows = len(session_windows)
    if total_windows == 0:
        return [], set()

    # Pre-compute IDF multipliers for all seen words
    idf_mult_cache: dict[str, float] = {}
    if word_idf is not None and max_idf > 0:
        for w in set(word_counts.keys()):
            idf_val = word_idf.get(w, 1.0)
            idf_mult_cache[w] = max(0.3, idf_val / max_idf)
    else:
        for w in set(word_counts.keys()):
            idf_mult_cache[w] = 1.0

    proposed_relations = []
    candidate_pairs: set[tuple[str, str]] = set()
    for (a, b), cooc in cooc_counts.items():
        if cooc < min_cooccurrences:
            continue

        # Track all candidate pairs (for edge-IDF computation)
        candidate_pairs.add((a, b))

        p_a = word_counts[a] / total_windows
        p_b = word_counts[b] / total_windows
        p_ab = cooc / total_windows

        pmi = math.log2(p_ab / (p_a * p_b))

        if pmi >= pmi_threshold:
            raw_weight = max(0.5, min(2.0, pmi / 2.0))

            # IDF multiplier: use the LOWER of the two IDF values
            # (the more common word determines the noise penalty)
            idf_mult = min(idf_mult_cache.get(a, 1.0), idf_mult_cache.get(b, 1.0))
            weight = raw_weight * idf_mult

            proposed_relations.append((a, b, weight))

    # Debug log
    with open("/tmp/pmi_debug.log", "a") as f:
        f.write(
            f"Tokens: {sum(len(w) for w in session_windows)}, "
            f"Windows: {total_windows}, Relations: {len(proposed_relations)}\n"
        )

    return proposed_relations, candidate_pairs


# ── Persistence ──────────────────────────────────────────────────────────────

def persist_pmi_relations(db_path: str, relations: list[tuple[str, str, float]]) -> int:
    """Save proposed PMI relations into entity_relations and entities tables.

    Returns the number of relations written or updated.
    """
    if not relations:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    written = 0

    try:
        import datetime
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for a, b, weight in relations:
            # 1. Ensure entities exist in entities table
            cursor.execute("SELECT id FROM entities WHERE name = ?", (a,))
            row_a = cursor.fetchone()
            if not row_a:
                id_a = f"pmi_{a}"
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO entities (id, name, entity_type, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (id_a, a, "concept", now_str, now_str)
                )
            else:
                id_a = row_a[0]

            cursor.execute("SELECT id FROM entities WHERE name = ?", (b,))
            row_b = cursor.fetchone()
            if not row_b:
                id_b = f"pmi_{b}"
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO entities (id, name, entity_type, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (id_b, b, "concept", now_str, now_str)
                )
            else:
                id_b = row_b[0]

            # 2. Insert or update relation (undirected, so sort IDs to avoid duplicates)
            src_id, tgt_id = sorted([id_a, id_b])
            relation_type = "co_occurrence"
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute(
                """
                SELECT weight FROM entity_relations
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
                """,
                (src_id, tgt_id, relation_type),
            )
            row_rel = cursor.fetchone()
            if row_rel:
                # Update relation: blend old weight with new PMI weight
                new_weight = (row_rel[0] * 0.7) + (weight * 0.3)
                cursor.execute(
                    """
                    UPDATE entity_relations SET weight = ?, last_seen = ?
                    WHERE source_id = ? AND target_id = ? AND relation_type = ?
                    """,
                    (new_weight, now_str, src_id, tgt_id, relation_type),
                )
            else:
                # Insert new relation
                cursor.execute(
                    """
                    INSERT INTO entity_relations (source_id, target_id, relation_type, weight, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (src_id, tgt_id, relation_type, weight, now_str, now_str),
                )
            written += 1
        conn.commit()
    except Exception as exc:
        logger.error("Failed to persist PMI relations: %s", exc)
        conn.rollback()
    finally:
        conn.close()

    return written
