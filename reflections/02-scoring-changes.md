# Reflection 02: Scoring Changes Applied

**Date:** 2026-03-13
**Status:** Changes applied. SOAP re-scoring in progress.
**Depends on:** [01-soap-rubric-issues.md](./01-soap-rubric-issues.md)

---

## Change 1: Weighted Overall Scores in `analyze-scores.py`

**Status:** Done.

`compute_averages()` now uses `DIMENSION_WEIGHTS` for the Overall column. Outputs to `results-weighted.csv` (original `results.csv` preserved from first scoring round).

```python
DIMENSION_WEIGHTS = {
    "hallucination": 2.0,
    "completeness": 2.0,
    "instruction_following": 1.0,
    "template_adherence": 1.0,
    "entity_marking": 0.5,
    "duplication": 1.0,
}
```

---

## Change 2: Updated Judge Prompt

**Status:** Done. Applied to both `score-notes.py` and `score-notes-gemini.py`.

Added `SCORING CLARIFICATIONS` section to `JUDGE_SYSTEM_PROMPT`:

1. **Misplaced content** — penalize template_adherence only, not completeness
2. **Clinical defaults** — "alert and oriented," "NKDA," "well-appearing," "in no acute distress" are not hallucinations

---

## Re-Scoring SOAP Notes

**Decision:** Re-score all 200 SOAP notes with both Claude and Gemini judges using the updated rubric.

The per-dimension scores from the first round have the double-penalization and clinical boilerplate issues baked in. Weighted analysis alone can't fix that — the underlying dimension scores need to reflect the corrected rubric.

### Commands

```bash
rm -rf evals/results/claude-opus-judge/soap/
rm -rf evals/results/gemini-pro-judge/soap/
python evals/scripts/score-notes.py --template soap
python evals/scripts/score-notes-gemini.py --template soap
python evals/scripts/analyze-scores.py --claude --gemini
```

### What to compare after re-scoring

- Does the Gemma 3n vs MedGemma 4B gap change?
- Do MedGemma's completeness scores rise now that misplaced content isn't double-penalized?
- Do hallucination scores improve across the board now that clinical boilerplate isn't flagged?

---

## Summary of All Changes

| Change | File | Status |
|---|---|---|
| Weighted overall scores | `analyze-scores.py` | Done |
| Misplacement clarification | `score-notes.py`, `score-notes-gemini.py` | Done |
| Clinical boilerplate carve-out | `score-notes.py`, `score-notes-gemini.py` | Done |
| Re-score SOAP (Claude + Gemini) | `results/claude-opus-judge/soap/`, `results/gemini-pro-judge/soap/` | In progress |
