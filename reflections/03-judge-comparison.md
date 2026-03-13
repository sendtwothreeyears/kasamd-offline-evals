# Reflection 03: Claude vs Gemini as Judges

**Date:** 2026-03-13
**Context:** Both Claude Opus and Gemini 2.5 Pro scored all 200 SOAP notes using the updated rubric (v2, with misplacement and clinical boilerplate fixes). This reflection compares how the two judges behave.

---

## Score Comparison

| Model | Claude Judge | Gemini Judge | Delta |
|---|---|---|---|
| Gemini 2.5 Flash | 81% | 84% | +3 |
| Qwen 3.5 4B | 7% | 73% | +66 |
| MedGemma 1.5 4B | 29% | 34% | +5 |
| Llama3 Medical COT | 9% | 8% | -1 |
| Gemma 3n E2B | 50% | 46% | -4 |
| MedGemma 4B | 49% | 44% | -5 |
| Llama 3.2 3B | 37% | 29% | -8 |
| Phi-4 Mini | 41% | 29% | -12 |

---

## Initial Hypothesis: Self-Preference Bias

We expected Gemini-as-judge to inflate Gemini-as-candidate scores relative to Claude-as-judge (self-preference bias). The +3 delta on Gemini Flash (84% vs 81%) is within noise — **no meaningful self-preference bias detected.**

---

## Actual Finding: The Judges Disagree on What Constitutes Failure

Gemini is not uniformly more generous — it scores half the models *lower* than Claude. The divergence is selective, and the pattern is explained by a single difference: **how strictly each judge penalizes unusable output formatting.**

### The Qwen Case Study

Qwen 3.5 4B outputs 60K+ characters of thinking/self-correction loops with a clinical note buried inside. The judges handle this differently:

**Claude's approach** — scores the output as a product:
- Hallucination: 3 (no fabricated clinical content, because no note was produced)
- Instruction following: 0 (output is thinking dump, not a note)
- Completeness: 0 (no clinical note generated)
- Template adherence: 0 (no structure)
- Entity marking: 0 (not attempted)
- Duplication: 1 (massive repetitive self-correction)

**Gemini's approach** — scores the clinical content within the output:
- Hallucination: 3 (content is accurate)
- Instruction following: 2 (minor formatting deviations)
- Completeness: 2 (most content captured)
- Template adherence: 2 (minor issues)
- Entity marking: 2 (correct syntax)
- Duplication: 0 (no duplication in the note portion)

Gemini reads through the thinking dump, finds the clinical note, and scores that. Claude correctly identifies the entire output as non-functional.

### Which Judge Is Right?

For our use case — an offline clinical note generator where output goes directly to a physician — **Claude's interpretation is correct.** The output must be usable as-is. A 60K thinking dump with a note buried inside is not a clinical note, regardless of whether the buried content is accurate.

However, Gemini's approach would be valid if you were evaluating the model's clinical reasoning ability rather than its output quality. The distinction matters for how you frame the eval.

### Broader Pattern

This same philosophical difference likely explains the other deltas:
- Gemini is harsher on Phi-4 Mini (-12) and Llama 3.2 (-8) — possibly because it's stricter on clinical accuracy even when structure is acceptable
- Gemini is more generous to MedGemma 1.5 (+5) — possibly finding value in its clinical content despite its structural failures

The judges don't disagree on *which model is better* (both rank Gemini Flash first, both put Qwen and Llama3 Medical COT at the bottom). They disagree on *how much to penalize structural failures when clinical content exists.*

---

## Implications

1. **Claude Opus is the trusted judge** for our eval, since we're evaluating output quality, not reasoning ability.
2. **The Gemini bias experiment (plan.md Step 6) delivered value**, but the finding was different from expected — it's not self-preference bias, it's a philosophical disagreement about scoring criteria.
3. **Gemini's Qwen scores should be treated as invalid** for our purposes. Scoring a 60K thinking dump as a functional clinical note is wrong for our use case.
4. **Excluding Qwen, the judges roughly agree on rankings** — both put Gemini Flash on top and the local model tier in the 29-50% range. The rank order within the local tier differs slightly but the story is the same: Gemma 3n and MedGemma 4B are the top local contenders.

---

## Run 1 vs Run 2: Rubric Fix Impact (Claude Judge Only)

| Model | Run 1 (old rubric, equal weights) | Run 2 (fixed rubric, weighted) | Delta |
|---|---|---|---|
| Gemini 2.5 Flash | 78% | 81% | +3 |
| Gemma 3n E2B | 49% | 50% | +1 |
| MedGemma 4B | 41% | 49% | +8 |
| Phi-4 Mini | 34% | 41% | +7 |
| Llama 3.2 3B | 31% | 37% | +6 |
| MedGemma 1.5 4B | 21% | 29% | +8 |
| Llama3 Medical COT | 7% | 9% | +2 |
| Qwen 3.5 4B | 7% | 7% | 0 |

### What the rubric fix changed

- **MedGemma 4B was the biggest beneficiary (+8 points).** The double-penalization fix on misplaced content and the clinical boilerplate exemption helped it the most — exactly as predicted in reflection 01. Its completeness rose from 45% to 48% and hallucination from 43% to 53%.
- **The Gemma 3n vs MedGemma 4B gap collapsed from 8 points to 1 point** (50% vs 49%). The original rubric was unfairly penalizing MedGemma's content-heavy-but-messy approach by double-counting misplacement errors.
- **Gemma 3n barely moved (+1)** because its strength was always structure, which wasn't affected by the rubric changes.
- **Everyone improved** because the clinical boilerplate exemption boosted hallucination scores across the board.
- **Qwen didn't move (7%)** because its failures are fundamental (empty or thinking-dump outputs), not rubric-sensitive.
