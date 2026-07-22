from __future__ import annotations

import json
import threading
from collections import defaultdict

from src.memory.entity import extractor


def test_learn_from_text_persists_tenth_entity_without_deadlock(tmp_path, monkeypatch):
    learned_path = tmp_path / "learned_entities.json"
    monkeypatch.setattr(extractor, "_LEARNED_ENTITIES", defaultdict(set))
    monkeypatch.setattr(extractor, "_CANDIDATE_FREQ", {})
    monkeypatch.setattr(extractor, "_LEARNED_COUNT_SINCE_SAVE", 0)
    persist_snapshot = extractor._persist_learned_entities
    monkeypatch.setattr(
        extractor,
        "_persist_learned_entities",
        lambda data, filepath=None: persist_snapshot(data, str(learned_path)),
    )

    finished = threading.Event()
    errors: list[BaseException] = []

    def learn_ten_entities() -> None:
        try:
            for index in range(10):
                entity = f"NovelEntity{index}"
                extractor.learn_from_text(f"{entity} {entity} {entity}")
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=learn_ten_entities, daemon=True)
    worker.start()

    assert finished.wait(timeout=2), "learning the tenth entity deadlocked"
    worker.join(timeout=0)
    assert not worker.is_alive()
    assert errors == []

    persisted = json.loads(learned_path.read_text(encoding="utf-8"))
    assert set(persisted["learned"]["tecnologia"]) == {
        f"NovelEntity{index}" for index in range(10)
    }
    assert persisted["freq"] == {
        f"novelentity{index}": 3 for index in range(10)
    }


def test_learn_from_text_batches_persistence_after_tenth_entity(monkeypatch):
    monkeypatch.setattr(extractor, "_LEARNED_ENTITIES", defaultdict(set))
    monkeypatch.setattr(extractor, "_CANDIDATE_FREQ", {})
    monkeypatch.setattr(extractor, "_LEARNED_COUNT_SINCE_SAVE", 0)
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(
        extractor,
        "_persist_learned_entities",
        lambda data, filepath=None: persisted.append(data),
    )

    for index in range(11):
        entity = f"BatchEntity{index}"
        extractor.learn_from_text(f"{entity} {entity} {entity}")

    assert len(persisted) == 1
