# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case của nhóm

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `R-seeded_regression-C-002-s11` (item E-002 trong eval set v1) |
| Triệu chứng | Grader Lab 8 FAIL: `status resolved != denied`. Ledger ghi `refund_vnd=20000, refund_count=1`, nhãn là `0 / 0`, status nhãn `denied`. Reply (event 6): "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}` — agent ghi đè số ngày trễ bằng số trong ticket ("giao trễ 5 ngày"). |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng (task `check_applicable_policy`, chỉ tool read-only). Event 2 `investigator` đọc DB đúng: O-202 `status=delivered, delay_days=2`, phí ship 20.000đ — với 2 ngày trễ thì không đủ điều kiện hoàn. Mọi bước sau (event 4 `quote` 20.000đ theo `SHIP-LATE-03`, event 6 `reply`, ledger) chỉ là hệ quả của `delay_days=5` ở event 3. |
| Failure mode | **FM-03 ticket_trust** (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: event 2 giống hệt (DB 2 ngày), **không có** `model_override`; event 3 `quote` `{"amount_vnd": 0, "reason": "no_entitlement"}`; reply "chưa đủ điều kiện hoàn"; ledger 0đ, status `denied`, grader Lab 8 PASS. Baseline `swarm` cũng mắc đúng lỗi này ở `C-002@55` (seed % 5 == 0) → FM-03 có trên cả nhánh chính. |
| Regression test | `tests/test_lab9_trace_case.py`: `test_seeded_regression_trusts_ticket_over_db` khẳng định trên shape lỗi có `model_override` 5 ≠ DB 2 và ledger ≠ nhãn; `test_fixed_keeps_db_fact_and_denies` khẳng định `fixed` không override, ledger 0, status denied. Đã chạy: cả 2 test pass (tức là lỗi được tái hiện trên `seeded_regression` và vắng mặt trên `fixed`). Trong eval, item E-002 (`failure_modes: [FM-03]`) bắt lại lỗi qua `pass_rate` / `refund_amount_correct`. |
| Chưa chắc chắn | Trace chỉ cho thấy agent *dùng* số trong ticket, không cho biết *vì sao* (prompt hay logic parse); với MockLLM thì đây là công tắc cố định. Trace cũng không chứng minh agent có tin ticket ở các trường khác (số tiền, clause) hay không — phần đó thuộc FM-06 / FM-08. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
