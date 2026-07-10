import sqlite3
from contextlib import closing

from src.api.memory import memory_graph_snapshot


class FakeGraph:
    def __init__(self, _db_path):
        self._names = {"pmi_alpha": "alpha", "cur_beta": "beta"}
        self._degree_centrality = {"alpha": 0.8, "beta": 0.6}

    def refresh(self):
        return None

    def pagerank(self, name):
        return {"alpha": 0.9, "beta": 0.7}[name]

    def degree_centrality(self, name):
        return self._degree_centrality[name]

    def hub_score(self, name):
        return 0.5

    def authority_score(self, name):
        return 0.4

    def entity_community(self, name):
        return 1


def test_memory_graph_snapshot_filters_layers_and_loads_edges(tmp_path):
    db_path = tmp_path / "memory.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE entity_relations (source_id TEXT, target_id TEXT, weight REAL)"
        )
        conn.execute("INSERT INTO entity_relations VALUES ('pmi_alpha', 'cur_beta', 0.75)")
        conn.commit()

    unified = memory_graph_snapshot(db_path=str(db_path), graph_factory=FakeGraph)
    curated = memory_graph_snapshot(
        layer="curated",
        db_path=str(db_path),
        graph_factory=FakeGraph,
    )

    assert [node["id"] for node in unified["nodes"]] == ["alpha", "beta"]
    assert unified["edges"] == [{"source": "alpha", "target": "beta", "weight": 0.75}]
    assert [node["id"] for node in curated["nodes"]] == ["beta"]
    assert curated["edges"] == []
