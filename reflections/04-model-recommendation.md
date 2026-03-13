# Reflection 04: Model Recommendation for Offline Note Generation

**Date:** 2026-03-13
**Context:** After two rounds of scoring (200 SOAP notes, 8 models, Claude Opus as trusted judge), Gemma 3n E2B (50%) and MedGemma 4B (49%) emerged as the top two local models. This reflection documents the decision rationale.

---

## The Scores Don't Settle It

| Model | No Halluc. | Complete | Instruct. | Format | Entities | No Dup. | Overall |
|---|---|---|---|---|---|---|---|
| Gemma 3n E2B | 56% | 35% | 39% | 61% | 24% | 84% | 50% |
| MedGemma 4B | 53% | 48% | 28% | 44% | 3% | 88% | 49% |

A 1-point gap is noise. The decision comes down to which failure mode is more acceptable.

---

## Recommendation: MedGemma 4B

### Why completeness wins over structure

- **A physician can fix bad structure.** Section misplacement, template artifacts leaking through, content in the wrong SOAP section — these are quick edits. The information is there; it just needs reorganizing.
- **A physician cannot fix missing content.** On dense visits (multimorbid, GAD, annual physical), Gemma 3n omits labs, exam findings, and counseling details entirely. The physician has to go back to the recording or their memory to reconstruct what's missing. That defeats the purpose of the tool.
- **MedGemma captures 48% of content vs Gemma 3n's 35%.** That's a 13-point gap on the dimension that matters most for clinical utility.

### Gemma 3n's failure modes are worse

- **Factual errors** — Gemma 3n confused brother/sister and maternal/paternal aunt in family history on transcript 34. These aren't formatting issues — they could affect clinical decisions (e.g., cancer screening recommendations). MedGemma didn't show this pattern.
- **Note duplication bug** — Gemma 3n duplicated the entire note on transcript 14. This suggests issues with generation termination on long outputs.
- **Clinically inadequate on dense visits** — For the complex cases that need documentation the most, Gemma 3n produces notes too thin to be useful.

### MedGemma's failure modes are fixable

- **Template instructions leaking through** — Solvable with simple string-matching post-processing (strip parenthetical instructions, bracket placeholders).
- **Section misplacement** — Content exists but in the wrong section. A physician can reorganize, or post-processing heuristics could help.
- **Transcript regurgitation** — MedGemma sometimes copies the transcript near-verbatim into the note rather than synthesizing. Verbose but not wrong. Physician can trim.
- **Duplication** — 88% no-duplication rate, better than Gemma 3n's 84%.

---

## Caveats

- **Both models are at ~50% of frontier quality** (Gemini Flash at 81%). Physician review is mandatory, not optional, regardless of model choice.
- **Entity marking is broken for both** (3% vs 24%). This feature will need post-processing or a dedicated pass regardless.
- **These results are SOAP-only.** H&P and DAP scoring may shift the picture — worth confirming before final commitment.
- **Both are 4-bit quantized on 8GB RAM.** If hardware constraints change, larger models or higher quantization could outperform both.

---

## Next Steps

1. Score H&P and DAP templates to confirm MedGemma 4B's advantage holds across note types.
2. Investigate post-processing for MedGemma's known failure modes (template leakage, section reordering).
3. Consider a targeted prompt engineering pass — MedGemma's completeness strength suggests it understands clinical content well but struggles with structural instructions. A simpler template or few-shot examples might help.
