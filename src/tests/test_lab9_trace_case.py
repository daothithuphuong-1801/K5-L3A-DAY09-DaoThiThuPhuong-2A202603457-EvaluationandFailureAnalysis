"""Regression test for docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step = event 3 `model_override {"delay_days": 5}` while the DB (event 2) says 2 days.
The test fails on any shape that lets the ticket override the DB on this claim, and passes on `fixed`.
"""
import pytest

pytestmark = pytest.mark.student

CLAIM, SEED = "C-002", 11


def db_delay(events):
    inv = next(e for e in events if e.get("kind") == "investigator")
    return inv["payload"]["lookup_order"]["order"]["delay_days"]


def overrides(events):
    return [e["payload"] for e in events if e.get("kind") == "model_override"]


def test_seeded_regression_trusts_ticket_over_db():
    from lab9.trace_case import investigate

    case = investigate("seeded_regression", CLAIM, SEED)
    t, label = case["trial"], case["label"]
    events = t["events"]
    assert db_delay(events) == 2
    assert overrides(events) == [{"delay_days": 5}], "first wrong step: ticket overrides DB delay"
    assert t["snapshot"]["refund_vnd"] != label["refund_vnd"]          # 20000 vs 0
    assert t["result"]["status"] == "resolved" and label["status"] == "denied"
    assert not t["lab8_pass"]


def test_fixed_keeps_db_fact_and_denies():
    from lab9.trace_case import investigate

    case = investigate("fixed", CLAIM, SEED)
    t, label = case["trial"], case["label"]
    assert overrides(t["events"]) == []
    assert t["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
    assert t["result"]["status"] == "denied"
    assert t["lab8_pass"]
