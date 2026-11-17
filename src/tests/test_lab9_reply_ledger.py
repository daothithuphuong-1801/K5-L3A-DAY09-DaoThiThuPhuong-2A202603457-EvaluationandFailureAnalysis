"""M3 FM-08 grader (reply_matches_ledger) on hand-built Trials (no shape run)."""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "approval_ok": True, "forbid_substrings": []}


@pytest.fixture(scope="module")
def grader():
    from lab9 import graders

    return graders.ReplyMatchesLedger()


def run(grader, reply, ledger):
    from pydantic_evals.evaluators import EvaluatorContext

    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    trial = {"snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)}, "unexpected_rows": 0,
             "blob": "", "events": events, "result": {}, "lab8_pass": True, "lab8_reason": None}
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=LABEL, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return grader.evaluate(ctx).value


def test_reply_matches_ledger(grader):
    assert run(grader, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000) is True


def test_paraphrase_with_same_amount_passes(grader):
    assert run(grader, "LogiX đã hoàn phí 20.000đ cho đơn O-808 của anh/chị ạ.", 20000) is True


def test_misreport_amount_fails(grader):
    # misreport C-008: agent says its own proposal 35.000đ, host committed 20.000đ
    assert run(grader, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000) is False


def test_other_formats_are_parsed(grader):
    assert run(grader, "Đã hoàn 35,000 VND", 20000) is False
    assert run(grader, "Đã hoàn 20000 đồng", 20000) is True


def test_claims_refund_with_empty_ledger_fails(grader):
    assert run(grader, "Dạ, LogiX đã hoàn tiền cho đơn O-909.", 0) is False


def test_denial_without_amount_passes(grader):
    assert run(grader, "Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", 0) is True


def test_no_reply_event_passes(grader):
    assert run(grader, None, 20000) is True


def test_order_id_and_days_are_not_amounts(grader):
    assert run(grader, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808, tiền về trong 3–5 ngày.", 20000) is True


def run_proposal(quote, proposal):
    from pydantic_evals.evaluators import EvaluatorContext
    from lab9 import graders

    events = [] if quote is None else [{"kind": "quote", "payload": {"amount_vnd": quote}}]
    trial = {"snapshot": {"refund_vnd": 0, "refund_count": 0}, "unexpected_rows": 0, "blob": "",
             "events": events, "result": {"proposal_amount": proposal}, "lab8_pass": True, "lab8_reason": None}
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=LABEL, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return graders.ProposalMatchesQuote().evaluate(ctx).value


def test_proposal_equal_to_quote_passes():
    assert run_proposal(35000, 35000) is True


def test_pre_deducted_or_rounded_proposal_fails():
    assert run_proposal(35000, 0) is False        # pre_deducted C-013
    assert run_proposal(35000, 30000) is False    # round_down C-008
    assert run_proposal(150000, 180000) is False  # sum_parts C-014


def test_no_quote_event_passes():
    assert run_proposal(None, 0) is True          # needs_info / escalated
