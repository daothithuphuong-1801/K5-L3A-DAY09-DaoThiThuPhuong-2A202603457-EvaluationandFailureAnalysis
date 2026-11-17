# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

```bash
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0, PASS floors
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 30   # exit 1, FAIL floors
```

Lớp dương (positive) = `FAIL`: việc của judge là **tìm** reply lỗi. Specificity = tn / (tn + fp).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (cả 3) | **dùng** (chỉ cho tone, không blocking tiền/approval) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ < 0.6, R < 0.7) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (`tp/fp/fn/tn`):
- tone_ok: `24 / 4 / 6 / 66` — specificity 66/70 = 0.943. Tỉ lệ FAIL quan sát 0.28 → Rogan-Gladen hiệu chỉnh **0.30** (đúng bằng tỉ lệ FAIL theo người: 30/100).
- helpful: `9 / 0 / 21 / 70` — specificity 1.0. Tỉ lệ FAIL quan sát 0.09 → hiệu chỉnh **0.30**: judge báo thấp hơn thực tế hơn 3 lần.

## ≥5 case audit thủ công

### tone_ok (10 bất đồng: 6 fn, 4 fp)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" / "anh/chị"; "em/bạn/nha/nhé" ⇒ FAIL*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Gộp vào quy tắc xưng hô ở #1, kèm 2 ví dụ few-shot FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi từ lịch sự ở đầu câu. Rubric: *chấm cả câu; mệnh lệnh cấm khách liên hệ ("không cần nhắn thêm") ⇒ FAIL dù có "Dạ"*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: *xin lỗi không bắt buộc; ngắn mà đủ ý và lễ phép ⇒ PASS*. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric: *thêm whitelist thuật ngữ được phép (refund, ship, COD)*. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống — thực chất là lỗi nội dung/cam kết, không chỉ tone. Rubric tone thêm *"không hứa hành động mà hệ thống chưa ghi"*; về lâu dài nên bắt bằng code (so reply với ledger, như FM-08). |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. Rubric: *emoji ⇒ FAIL trong kênh CS khiếu nại*. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn… ạ." | FAIL | PASS | **Judge** (nhãn người sai) | Ghi chú CSV: người đọc nhầm ticket. Hành động: **sửa nhãn người** trong tập hiệu chuẩn rồi chấm lại; không sửa rubric. Cho thấy nhãn người cũng cần review thứ hai. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người | Lặp "Dạ" do gõ nhầm, không thô lỗ. Rubric: *lỗi gõ nhỏ không ảnh hưởng thái độ ⇒ không FAIL tone*. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric: *tiếng Việt không dấu ⇒ FAIL*. |

### helpful (21 bất đồng, tất cả là judge PASS / người FAIL)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL (sai tiền) | Người | Ledger ghi 40.000đ. Judge chỉ đọc reply, **không thấy ledger** nên không thể biết số sai. |
| 12 | HL-016 / HL-028 / HL-072 / HL-096 / HL-098 (xin lỗi dài + số tiền) | PASS | FAIL (sai tiền) | Người | Reply dài, nhiều lời xin lỗi → judge chấm "helpful", trong khi số tiền khác ledger (vd HL-016 nói 55.000đ, ledger 35.000đ). Judge thiên vị độ dài/lịch sự. |
| 13 | HL-043 "…LogiX đã hoàn 35.000đ cho đơn O-202…" | PASS | FAIL (sai tiền) | Người | Ledger 20.000đ — đúng kiểu lỗi FM-08 của agent (`misreport` C-008: nói 35k, ledger 20k). |
| 14 | HL-047 / HL-091 / HL-097 "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL (sai xưng hô) | Người | Không nêu kết quả cụ thể, xưng hô suồng sã. Đây là lỗi tone → để `tone_ok` bắt (judge tone đã qua floors). |

Tổng hợp 30 FAIL theo người của helpful: **sai tiền 18/18 bị judge bỏ sót**, sai xưng hô 3/3 bị bỏ sót; judge chỉ bắt được các lỗi lộ ngay trên câu chữ (giọng cụt 4/4, không hỏi lại mã đơn 3/3, lạc đề 2/2).

## Kết luận
- **tone_ok: dùng được.** κ=0.757, P=0.857, R=0.8 đều vượt floors. Chỉ dùng cho tiêu chí giọng điệu, không bao giờ cho tiền/approval. Áp dụng các sửa rubric ở #1–#10 (quy tắc xưng hô, emoji, không dấu, whitelist "refund", không bắt buộc xin lỗi) và sửa nhãn H-081, rồi hiệu chuẩn lại trên tập **mới**.
- **helpful: loại, không được dùng làm gate.** Recall 0.30 (ma trận `tp=9, fn=21`) nghĩa là judge bỏ sót 70% reply hỏng; κ=0.375 < 0.6. Precision 1.0 không cứu được: judge gần như không bao giờ nói FAIL nên ít khi sai khi nói FAIL. Nếu dùng làm gate, tỉ lệ lỗi báo cáo là 9% trong khi thực tế (Rogan-Gladen) là 30% — gate sẽ cho qua bản tệ.
- **Nguyên nhân gốc:** 18/21 lỗi bỏ sót là **sai tiền**, mà judge chỉ thấy reply chứ không thấy ledger. Đây là việc của code, không phải judge: tách "đúng số tiền" ra thành grader code so reply với ledger (metric FM-08 ở M3); phần còn lại của "helpful" (hỏi lại mã đơn, đúng trọng tâm) có thể viết lại rubric hẹp hơn và hiệu chuẩn lại.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng/tiêu chí), nên các con số có thể lạc quan; sửa rubric dựa trên chính tập này rồi đo lại trên nó sẽ overfit. Cần nhãn người mới (held-out thật, có 2 người gán nhãn để đo đồng thuận người–người) trước khi tin judge tone ở quy mô lớn.
