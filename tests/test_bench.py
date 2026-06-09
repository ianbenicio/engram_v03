from engram.bench import run_bench, seed_bench_vault, BENCH_DATASET
from engram.core.embeddings import EmbeddingUnavailable


def _force_offline(monkeypatch):
    def boom(t, c):
        raise EmbeddingUnavailable("offline")
    monkeypatch.setattr("engram.core.embeddings.get_embedding", boom)


def test_seed_creates_four_notes(db, config, vault, monkeypatch):
    _force_offline(monkeypatch)
    seed_bench_vault(config, db)
    n = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert n == 4


def test_dataset_nonempty():
    assert len(BENCH_DATASET) >= 4
    for query, expect_id, route in BENCH_DATASET:
        assert route in ("lightweight", "heavy")


def test_bench_path_a_and_router_perfect_offline(db, config, vault, monkeypatch):
    _force_offline(monkeypatch)
    res = run_bench(config, db)
    assert res["total_queries"] == len(BENCH_DATASET)
    assert res["path_a_recall_at_5"] == 1.0
    assert res["router_accuracy"] == 1.0


def test_bench_path_b_skipped_when_offline(db, config, vault, monkeypatch):
    _force_offline(monkeypatch)
    res = run_bench(config, db)
    assert res["path_b_recall_at_5"] is None
    assert "skipped" in res["path_b_status"]
