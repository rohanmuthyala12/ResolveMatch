from backend import config, ops, service
from backend.seed import seed
from backend.store import db


def test_run_stats_reads_usage_latency_and_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ops.sqlite3")
    seed()
    events = [
        {"id": "a", "type": "turn.created", "created_at": "2026-01-01T00:00:00.000Z"},
        {
            "id": "b",
            "type": "model.message",
            "created_at": "2026-01-01T00:00:02.000Z",
            "usage": {"input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 40},
            "tool_calls": [{"id": "c1", "function": {"name": "rank_engineers"}, "tool_info": {"name": "rank_engineers"}}],
        },
        {"id": "c", "type": "tool.response", "tool_call_id": "c1", "created_at": "2026-01-01T00:00:03.000Z"},
        {"id": "d", "type": "turn.done", "created_at": "2026-01-01T00:00:05.000Z"},
    ]
    s = ops.run_stats(events)
    assert s["duration"] == 5 and s["model_calls"] == 1
    assert s["tokens"]["input"] == 100 and s["tokens"]["cached"] == 40
    assert s["tools"] == [("rank_engineers", 1.0)]
    assert ops.overview()["runs"]["started"] == 0
