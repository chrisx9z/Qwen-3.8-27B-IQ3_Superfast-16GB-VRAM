# Báo cáo: abliteration ảnh hưởng chất lượng suy luận thế nào

Ngày đo: 2026-09-18 · Máy: RTX 5070 Ti 16 GB + CPU (đo bằng CPU để không chiếm GPU của app)

---

## 1. Vì sao abliteration có thể làm giảm chất lượng

Abliteration **chiếu (project) bỏ** một "hướng từ chối" khỏi trọng số ở tầng residual
stream / attention / MLP. Vấn đề: hướng từ chối **không hoàn toàn tách rời** khỏi các
hướng dùng cho suy luận chung — nên khi cắt bỏ, một phần tín hiệu hữu ích bị mất theo.

Mức mất phụ thuộc:
- **Số hướng bị cắt & số tầng bị sửa**: 1 hướng (basic) → 4 (advanced) → 8 (aggressive/nuclear).
- **Số pass tinh chỉnh**: càng nhiều pass càng sạch nhưng càng dễ tổn thương năng lực.
- **Kích thước model**: model nhỏ mất nhiều hơn (ít chiều dư thừa để bù).
- **Mức "dính" của guardrail với năng lực**: đo bằng module Defense Robustness /
  Safety-Capability Entanglement của OBLITERATUS.

---

## 2. Số liệu công bố cho Qwen3.8-27B (model card OBLITERATUS)

MMLU (lm-eval-harness, 0-shot, n=5700):

| Phiên bản | MMLU | vs bản gốc |
|---|---|---|
| Qwen3.8-27B gốc | 84.5% | — |
| V1 — aggressive, 5 hướng | 81.4% | **−6.0pp** ("noticeably dumber") |
| V2 — blend hai surgery | 84.32% ±0.65 | **−0.28pp** (gần như gốc, nhưng né tránh mềm còn sót) |
| **V3 — iterative + targeted** | **82.33% ±0.48** | **−2.12pp** (cân bằng, giải phóng thật) |

Theo nhóm môn (V3 so với gốc):

| Nhóm | V3 | Gốc | Chênh |
|---|---|---|---|
| STEM | 78.5% | 81.8% | **−3.3pp** (hít nặng nhất) |
| Social Sciences | 87.4% | 89.2% | −1.8pp |
| Other | 82.3% | 84.1% | −1.8pp |
| Humanities | 83.3% | 84.3% | −1.0pp |

Một số môn **tăng** (triết học +6pp, lịch sử châu Âu +4pp) — tức là không phải mất đều.

**Kết luận từ nhà phát hành:** mức giá hợp lý để "giải phóng thật" là **khoảng −2pp MMLU**.

---

## 3. Đo trực tiếp trên máy này (2 model bạn đang có)

### 3.1 Perplexity (30 chunk × 512 token, cùng corpus, CPU, cùng tham số)

| Model | Perplexity | Ghi chú |
|---|---|---|
| `Qwen3.8-27B-UD-IQ3_S.gguf` (gốc) | **5.8121 ± 0.2316** | bản đang dùng |
| `Huihui-Qwen3.8-27B-abliterated-UD-IQ3_S.gguf` | **5.9425 ± 0.2405** | bản đã abliterate |

→ Chênh **+0.1304 ≈ +2.2%** perplexity; nằm trong khoảng ~0.4σ của sai số chuẩn nên là
**thay đổi nhỏ**. Ngưỡng "fail" mặc định của OBLITERATUS là perplexity tăng **3×** —
tức bản này còn rất xa ngưỡng đó.

*Lưu ý:* bản abliterate bạn đang có là của lab khác (huihui) và quant trộn
(IQ3_S/IQ3_XXS/Q4_K) nên chênh lệch PPL gồm cả khác biệt quantization, không thuần
abliteration. Con số nên đọc như "chỉ báo", không phải đo tuyệt đối.

### 3.2 Kiểm tra suy luận (3 prompt: toán, logic, code — CPU, cùng tham số)

| Prompt | Bản gốc | Bản abliterate |
|---|---|---|
| Toán: 3 thùng × 24 hộp, bán 17 | ✅ đúng (55) | ✅ đúng (55) |
| Logic: ∀A⊂B, B∩C=∅ ⇒ ? | ✅ suy luận đúng | ✅ đúng, trả lời gọn 2 câu đúng yêu cầu |
| Code: hàm kiểm tra số nguyên tố | ✅ (bị cắt do giới hạn token) | ✅ `n>1 and all(n%i for i in range(2,int(n**.5)+1))` |

Tốc độ sinh trên CPU tương đương nhau (~2.6–3.1 token/s) — **không thấy chậm đi**.

Mẫu chỉ 3 prompt nên không kết luận thay cho benchmark, nhưng cùng với PPL và MMLU
công bố, bức tranh nhất quán: **giảm nhẹ, có đo được, không sụp đổ năng lực**.

---

## 4. OBLITERATUS tự kiểm tra gì (giai đoạn VERIFY)

Mỗi run ghi vào `abliteration_metadata.json`:

| Chỉ số | Ý nghĩa | Ngưỡng mặc định |
|---|---|---|
| `perplexity` / `perplexity_increase` | Độ trôi chảy so với gốc | fail nếu > **3.0×** |
| `coherence_retention` | Giữ mạch lạc so với gốc | fail nếu < **0.5** |
| `degenerate_fraction` | Tỉ lệ câu lặp/trống | fail nếu > **0.2** |
| `refusal_rate` | Tỉ lệ còn từ chối (30 prompt) | càng thấp càng tốt |
| `capability_results` | 6 phép thử: CoT, code, instruction, JSON, tool-call, mô tả ảnh | — |
| `kl_divergence` | Lệch phân phối so với gốc | ngân sách mặc định 0.5 |

**Cảnh báo:** các ngưỡng này khá "dễ" (3× perplexity là rất rộng) — vượt qua ngưỡng
**không** đồng nghĩa chất lượng không đổi; nó chỉ chặn hỏng nặng.

Ví dụ từ run demo trên máy bạn (Qwen3-0.6B, method `basic`):
PPL 5.898 → 5.837 (không tăng), coherence_retention 0.8, degenerate 10%,
capability 4/6 (trượt `chain_of_thought` và `code_function` — model 0.6B vốn yếu,
và method `basic` là bản thô nhất), refusal_rate 0.0, KL 0.072, spectral GREEN.

---

## 5. Cách giảm thiểu rủi ro

1. **Chọn method theo nhu cầu**: `advanced` (mặc định, "minimal capability loss"),
   `optimized` (Bayesian tự dò + CoT-aware + KL co-optimized — chất lượng tốt nhất).
   Tránh `aggressive`/`nuclear` trừ khi thật cần: chúng là bản gây −6pp MMLU.
2. **Giữ cả hai model** để A/B (bạn đang có cả gốc và abliterate) — so sánh trước khi
   dùng thường xuyên.
3. **Nhiệt độ thấp** (temperature 0) cho output đầy đủ, ổn định hơn (khuyến nghị từ
   model card).
4. **System prompt nặng có thể làm từ chối quay lại** — model card khuyên để trống/ngắn.
5. **Muốn con số chắc chắn hơn**: chạy `capability-check` (MMLU so với gốc — cần trọng
   số HF), hoặc đo PPL/spot-check như mục 3 (có thể chạy lại bất cứ lúc nào bằng
   llama.cpp trên máy).

---

## 6. Tóm tắt một câu

Với Qwen3.8-27B, abliteration "tử tế" (V3/advanced) mất khoảng **−2pp MMLU**, nặng nhất
ở **STEM (−3.3pp)**, nhẹ ở humanities (−1.0pp); đo trên máy bạn cho **+2.2% perplexity**
và các phép thử suy luận ngắn vẫn đúng — tức **giảm nhẹ, không phải hỏng**. Muốn ít mất
nhất thì dùng method `optimized`/`advanced`, nhiệt độ 0, và giữ bản gốc để đối chiếu.
