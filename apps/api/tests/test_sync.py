"""Unit tests for the pure event-sync logic (envelope, echo guard, drift)."""
from app.skilled_pro import events


def test_make_event_shape_and_defaults():
    ev = events.make_event("credential", "abc", "credential.verified", {"x": 1})
    assert ev["aggregate_type"] == "credential"
    assert ev["aggregate_id"] == "abc"
    assert ev["event_type"] == "credential.verified"
    assert ev["payload"] == {"x": 1}
    assert ev["source"] == events.THIS_SOURCE
    assert len(ev["event_id"]) == 32           # uuid4 hex


def test_event_ids_are_unique():
    ids = {events.new_event_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_canonical_json_is_stable_and_sorted():
    a = events.make_event("c", "1", "t", {"b": 2, "a": 1}, event_id="fixed")
    b = events.make_event("c", "1", "t", {"a": 1, "b": 2}, event_id="fixed")
    assert events.canonical_json(a) == events.canonical_json(b)
    assert events.canonical_json(a).index('"a"') < events.canonical_json(a).index('"b"')


def test_round_trip_parse():
    ev = events.make_event("c", "1", "t", {"k": "v"}, event_id="x")
    assert events.parse_event(events.canonical_json(ev)) == ev
    assert events.parse_event(ev) == ev          # passthrough for dicts


def test_echo_guard_skips_own_events():
    own = events.make_event("c", None, "t", source=events.THIS_SOURCE)
    foreign = events.make_event("c", None, "t", source=events.PEER_SOURCE)
    assert events.should_consume(own) is False
    assert events.should_consume(foreign) is True
    assert events.should_consume({"event_type": "t"}) is True   # missing source = foreign


def test_compute_drift():
    d = events.compute_drift(["a", "b", "c"], ["b", "c", "z"])
    assert d["missing_in_inbox"] == ["a"]        # published, not applied
    assert d["extra_in_inbox"] == ["z"]          # applied, foreign origin


def test_compute_drift_in_sync():
    d = events.compute_drift(["a", "b"], ["a", "b"])
    assert d["missing_in_inbox"] == []
    assert d["extra_in_inbox"] == []
