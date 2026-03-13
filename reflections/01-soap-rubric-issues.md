# Reflection 01: SOAP Rubric Issues

**Date:** 2026-03-13
**Status:** Fixes applied — judge prompts updated, SOAP re-scoring in progress.
**Context:** After scoring 200 SOAP notes (25 transcripts × 8 models) with Claude Opus as judge, we reviewed the individual score rationales and generated notes side-by-side. Three systemic rubric flaws emerged that deflate scores in ways that don't reflect clinical utility.

---

## Problem 1: Double-Penalization of Misplaced Content

### What happened

When a model places clinical content in the wrong SOAP section — e.g., physical exam findings written under Subjective instead of Objective — the judge penalizes **both** completeness ("item missing from the correct section") **and** template adherence ("wrong section structure"). The same error gets counted twice.

### Why it matters

This disproportionately hurts MedGemma 4B, which captures more clinical content but frequently dumps it into Subjective rather than organizing it across SOAP sections. Its completeness scores are artificially deflated because the judge treats "present but misplaced" the same as "absent."

### Example

**Transcript 14 (multimorbid):** MedGemma captures lab values, exam findings, and dialysis counseling — but places them in the Subjective section. The judge scores:
- Template adherence: 1 (correct — wrong section)
- Completeness: 2 (but would be higher if misplaced content counted as "captured")

Meanwhile Gemma 3n E2B omits all of that content entirely and gets completeness: 1. The gap between them (2 vs 1) understates the real difference in clinical content capture.

### Fix

Added to `JUDGE_SYSTEM_PROMPT` in `score-notes.py` and `score-notes-gemini.py`:
> "If content from the transcript is present in the generated note but placed in the wrong section, penalize template_adherence only. Do NOT also penalize completeness — the information was captured. Completeness measures whether transcript content appears in the note at all, regardless of placement."

---

## Problem 2: Clinical Boilerplate Penalized as Hallucination

### What happened

The rubric defines hallucination as "content not stated or reasonably inferred from the transcript." The judge interprets this strictly and flags standard clinical defaults as fabrications:

- **"Alert and oriented"** — appears in virtually every clinical note as a baseline observation, even when not explicitly dictated
- **"No known drug allergies" (NKDA)** — standard default when allergies aren't discussed
- **"Well-appearing" / "In no acute distress"** — ubiquitous general appearance boilerplate

### Why it matters

Models that behave like real clinicians (adding expected defaults) get penalized. Models that produce sparser notes avoid the penalty. This creates a perverse incentive where omitting standard documentation is "safer" than including it — the opposite of what we want clinically.

### How widespread

Across 25 transcripts, "alert and oriented" was flagged as hallucinated for multiple models on multiple transcripts. "NKDA" was flagged for at least Gemma 3n E2B on transcript 01. These are consistent, systematic penalties that shift overall hallucination scores.

### Fix

Added to `JUDGE_SYSTEM_PROMPT` in `score-notes.py` and `score-notes-gemini.py`:
> "The following are considered standard clinical defaults and should NOT be scored as hallucinations: 'alert and oriented,' 'no known drug allergies' (when allergies were not discussed), 'well-appearing,' and 'in no acute distress.' These are ubiquitous in real clinical documentation and their inclusion reflects standard practice, not fabrication."

---

## Problem 3: Equal Dimension Weighting Obscures Clinical Utility

### What happened

The `analyze-scores.py` script computes the overall score as a simple average of all 6 dimensions (hallucination, completeness, instruction following, template adherence, entity marking, no duplication). Each dimension contributes equally.

### Why it matters

- **Entity marking is broken for all local models** (0-3% scores across the board). Including it at equal weight drags down every local model's overall score by the same amount, adding noise without differentiation. It's a feature none of them can do — it doesn't help us choose between them.
- **Hallucination and completeness are the dimensions that matter most** for clinical safety and utility, but they carry the same weight as template formatting.
- The equal weighting is why Gemma 3n E2B (49%) outranks MedGemma 4B (41%) overall — Gemma wins on structure dimensions (template adherence 63% vs 47%, instruction following 37% vs 24%) while MedGemma wins on the arguably more important completeness dimension (45% vs 36%).

### Fix

Updated `analyze-scores.py` to use weighted overall scoring via `DIMENSION_WEIGHTS`. Outputs to `results-weighted.csv`.

Weights:

| Dimension | Original Weight | New Weight | Rationale |
|---|---|---|---|
| Hallucination | 1x | 2x | Patient safety — fabricated content is the worst failure mode |
| Completeness | 1x | 2x | Core purpose — a note that misses key findings fails its job |
| Instruction Following | 1x | 1x | Important but secondary to content accuracy |
| Template Adherence | 1x | 1x | Important but secondary to content accuracy |
| Entity Marking | 1x | 0.5x | Non-differentiating — broken for all local models |
| No Duplication | 1x | 1x | Clear binary failure, keep as-is |

---

## Impact on Model Rankings

With these changes, the competitive picture between Gemma 3n E2B and MedGemma 4B shifts:

**Current picture (equal weights, double-penalization baked in):**
- Gemma 3n E2B: 49% overall (wins on structure)
- MedGemma 4B: 41% overall (wins on completeness)

**Expected shift with weighted scoring:**
- The gap narrows significantly, and MedGemma may overtake Gemma 3n depending on the weight configuration
- MedGemma's completeness advantage (45% vs 36%) gets amplified at 2x weight
- Entity marking's drag gets halved for both

**With rubric fixes (future H&P and DAP scoring):**
- MedGemma's completeness scores should rise further (misplaced content no longer double-penalized)
- Both models' hallucination scores should improve slightly (clinical boilerplate no longer flagged)
- The improvement will be larger for MedGemma since it produces more content and thus has more opportunities to be unfairly penalized
