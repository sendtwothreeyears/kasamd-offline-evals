# Eval Plan — Clinical Note Generation

## Overview

Head-to-head evaluation of 8 candidate models for clinical note generation (transcript → SOAP/H&P/DAP notes). Goal: find the best model that runs locally on an 8GB RAM Apple Silicon Mac without hallucinating, follows instructions, and produces well-structured notes.

## Steps

- [x] **Step 1: Define Eval Dimensions**
- [x] **Step 2: Build Test Suite** (50 transcripts, 3 templates)
- [x] **Step 3: Collect Responses** (all 8 models, SOAP template, 25 transcripts — committed in `results/responses/`)
- [ ] Step 4: Score — Heuristic (pattern matching)
- [x] **Step 5a: Score — LLM-as-Judge, Round 1** (SOAP scored, rubric issues identified — see `reflections/`)
- [ ] Step 5b: Score — LLM-as-Judge, Round 2 (re-scoring SOAP with revised rubric; then H&P and DAP)
- [ ] Step 6: Evaluate Judges (compare Claude vs Gemini scoring behavior)
- [ ] Step 7: Analyze Results (compare models, find winner)

---

## Step 1: Eval Dimensions

### Scored Dimensions (0-3, higher = better)

#### Hallucination
| 0 | 1 | 2 | 3 |
|---|---|---|---|
| Fabricated findings/diagnosis with no basis in transcript | Fabricated detail that cannot be extrapolated from transcript | Minor embellishment beyond what transcript supports | No hallucination — all content is stated or reasonably inferred from transcript |

#### Instruction Following
| 0 | 1 | 2 | 3 |
|---|---|---|---|
| Ignored key instructions (e.g., fabricated instead of "Not documented") | Ignored some instructions | Minor deviation | Perfect |

#### Completeness
| 0 | 1 | 2 | 3 |
|---|---|---|---|
| Missed key findings | Missed important detail | Minor omission | Captured everything in transcript |

#### Template Adherence
| 0 | 1 | 2 | 3 |
|---|---|---|---|
| Unstructured output | Sections missing/wrong | Minor formatting issue | Perfect structure |

#### Entity Marking
| 0 | 1 | 2 | 3 |
|---|---|---|---|
| No entity marking attempted | Incorrect syntax or marked wrong entity types (e.g., procedures instead of drugs/conditions) | Correct syntax but errors (e.g., marked repeated occurrences, missed obvious entities) | Correct syntax, first-occurrence-only, drugs and conditions only |

### Boolean Flags
- **Duplication**: 0 = no duplication, 1 = output repeated

### Metadata (recorded but not scored)
- Inference time (seconds)
- Tokens/sec
- Peak memory usage

---

## Step 2: Build Test Suite

### Methodology

Test transcripts were selected to mirror real-world primary care visit distribution using published epidemiological data:

**Data sources:**
- [CDC NAMCS 2018 National Summary Tables](https://www.cdc.gov/nchs/data/ahcd/namcs_summary/2018-namcs-web-tables-508.pdf) — ~860M primary care visits surveyed
- [Definitive Healthcare: All-Payor Claims (2024)](https://www.definitivehc.com/blog/10-most-common-diagnoses-in-primary-care) — ICD-10 frequency by % of visits
- [PMC Systematic Review: Common Conditions in Primary Care](https://pmc.ncbi.nlm.nih.gov/articles/PMC6234945/) — 18 studies across 12 countries
- [JABFM: Frequency of Diagnoses in Family Medicine (NAMCS)](https://www.jabfm.org/content/31/1/126) — 928M estimated office visits (2012)

**Key findings that shaped the distribution:**
- Chronic disease management accounts for ~39% of primary care visits (NAMCS)
- Acute/new problems account for ~24%
- Preventive care accounts for ~23%
- Top 5 diagnoses (hypertension, wellness exams, hyperlipidemia, diabetes, respiratory infections) represent >11% of all visits
- Depression/anxiety ranks #3 in developed countries (PMC systematic review)
- Mental health, GI (GERD), dermatitis, and musculoskeletal pain all appear in the top 10 globally

**Weighting approach:** Categories were allocated proportionally to visit frequency, then individual scenarios were chosen to cover the breadth within each category. Where a single condition dominates (e.g., hypertension at 4.8%), multiple visit types (new dx, stable f/u, uncontrolled) were created to test different transcript densities.

### Test Matrix

- **50 transcripts** across primary care scenarios
- **3 templates** (SOAP, H&P, DAP) applied to every transcript
- **8 candidate models** generate a note for each transcript × template pair
- **Total: 1,200 scored outputs**

Density mix: ~15 sparse, ~20 medium, ~15 dense (assigned per transcript to test hallucination resistance on sparse inputs and completeness on dense inputs).

### Transcript List

| # | Category | Scenario | Density |
|---|----------|----------|---------|
| | **Chronic disease management (14)** | | |
| 1 | Hypertension | New diagnosis, lifestyle counseling | Sparse |
| 2 | Hypertension | Stable follow-up, refill visit | Sparse |
| 3 | Hypertension | Uncontrolled, medication adjustment | Medium |
| 4 | Diabetes T2 | Routine follow-up, A1c at goal | Medium |
| 5 | Diabetes T2 | Newly elevated A1c, adding medication | Dense |
| 6 | Hyperlipidemia | Statin initiation discussion | Medium |
| 7 | Hyperlipidemia | Lipid panel review, diet counseling | Sparse |
| 8 | Hypothyroidism | TSH adjustment visit | Sparse |
| 9 | Asthma | Adult exacerbation, inhaler review | Medium |
| 10 | COPD | Stable follow-up, spirometry review | Dense |
| 11 | Osteoarthritis | Knee pain, chronic management | Medium |
| 12 | CHF | Volume status check, med adjustment | Dense |
| 13 | CKD | Stage 3, lab review and referral | Dense |
| 14 | Multimorbid | HTN + DM + CKD combined visit | Dense |
| | **Acute / new problem (12)** | | |
| 15 | URI | Viral upper respiratory infection | Sparse |
| 16 | Influenza | Influenza-like illness, Tamiflu discussion | Medium |
| 17 | Strep pharyngitis | Sore throat, rapid strep positive | Sparse |
| 18 | Acute bronchitis | Persistent cough 2 weeks | Medium |
| 19 | UTI | Dysuria and frequency in woman | Sparse |
| 20 | Acute otitis media | Ear pain in child | Medium |
| 21 | Sinusitis | Facial pressure, purulent drainage | Medium |
| 22 | Low back pain | Acute onset, no red flags | Medium |
| 23 | Skin infection | Cellulitis of lower extremity | Sparse |
| 24 | Gastroenteritis | Acute diarrhea and vomiting | Sparse |
| 25 | Headache/Migraine | New-onset recurrent headaches | Dense |
| 26 | Gout flare | Acute monoarticular joint pain | Medium |
| | **Mental health (7)** | | |
| 27 | Depression | New diagnosis, PHQ-9 screening | Medium |
| 28 | Depression | Medication follow-up, dose adjustment | Sparse |
| 29 | Anxiety (GAD) | Initial evaluation | Dense |
| 30 | Anxiety | Panic episode, acute visit | Medium |
| 31 | Insomnia | Chronic insomnia, sleep hygiene | Sparse |
| 32 | ADHD | Adult ADHD evaluation | Dense |
| 33 | Substance use | Alcohol use, brief intervention (SBIRT) | Medium |
| | **Preventive / wellness (7)** | | |
| 34 | Annual physical | Healthy 45yo male, routine labs | Dense |
| 35 | Well-child visit | 4-year-old checkup, developmental screen | Dense |
| 36 | Medicare wellness | Annual wellness visit, cognitive screen | Dense |
| 37 | Pre-op clearance | Knee surgery clearance | Medium |
| 38 | Immunization | Travel vaccines + routine catch-up | Sparse |
| 39 | Cancer screening | Abnormal mammogram follow-up discussion | Medium |
| 40 | Contraception | IUD counseling, options discussion | Medium |
| | **GI (3)** | | |
| 41 | GERD | Heartburn, PPI initiation | Sparse |
| 42 | IBS | Chronic abdominal pain workup | Dense |
| 43 | Abnormal LFTs | Fatty liver disease, lab review | Medium |
| | **Dermatology (3)** | | |
| 44 | Eczema | Flare in adult, topical management | Sparse |
| 45 | Suspicious mole | Skin check, biopsy discussion | Medium |
| 46 | Acne | Teen, first-line treatment | Sparse |
| | **Endocrine / other (4)** | | |
| 47 | Vitamin D deficiency | Fatigue workup, low vitamin D | Sparse |
| 48 | Anemia | Fatigue, low hemoglobin, iron studies | Medium |
| 49 | Neuropathy | Diabetic neuropathy, tingling in feet | Dense |
| 50 | Polypharmacy | Elderly patient, 12+ meds, deprescribing | Dense |

---

## Step 3: Collect Responses

Run every transcript × template × model combination and store the outputs.

### Process

For each of the 3 templates (SOAP → H&P → DAP):
1. Load the transcript and template
2. Construct the prompt using the same system prompt as `server/utils/ai/generateMedicalNote.ts`
3. Run through all 8 models
4. Save the generated note + metadata

### Models

| # | Model | Runner |
|---|-------|--------|
| 1 | MedGemma 1.5 4B IT | `mlx-lm` (local) |
| 2 | MedGemma 4B IT | `mlx-lm` (local) |
| 3 | LLAMA3-3B-Medical-COT | `mlx-lm` (local) |
| 4 | Llama 3.2 3B Instruct | `mlx-lm` (local) |
| 5 | Gemma3N E2B | `mlx-lm` (local) |
| 6 | Phi-4 Mini | `mlx-lm` (local) |
| 7 | Qwen3.5 4B | `mlx-lm` (local) |
| 8 | Gemini 2.5 Flash | Google AI API (cloud) |

### Prompt construction

The eval harness is **self-contained** — all prompts, templates, and config live in `evals/`. No references to `server/` or other parts of the codebase.

Each model receives:
- **System prompt**: Defined as a constant in `evals/scripts/run-models.py` (medical documentation assistant instructions, entity marking rules, critical rules 1-12)
- **User prompt**: Template loaded from `evals/templates/{soap,hp,dap}.txt` + transcript loaded from `evals/transcripts/dictations/XX-name.txt` (YAML frontmatter stripped)

Message format:
```
System: [system prompt constant in run-models.py]
User: "TEMPLATE:\n{template text}\n---\nTRANSCRIPTION:\n{transcript text}\n\nGenerate a complete medical note..."
```

The template text includes bracket placeholders (e.g., `[Patient's primary reason for visit]`) and parenthetical instructions (e.g., `(Only include systems that were discussed)`). Models should replace brackets with content and follow but strip parenthetical instructions — this is exactly what we're testing.

### Output format

Each response is saved as a JSON file containing:
```json
{
  "transcript_id": "01-htn-new-dx",
  "template": "soap",
  "model": "medgemma-1.5-4b",
  "generated_note": "...",
  "metadata": {
    "inference_time_s": 12.3,
    "tokens_generated": 450,
    "tokens_per_sec": 36.6,
    "peak_memory_mb": 3200
  }
}
```

### Output directory structure

```
evals/results/responses/
├── soap/
│   ├── 01-htn-new-dx/
│   │   ├── medgemma-1.5-4b.json
│   │   ├── medgemma-4b.json
│   │   ├── llama3-medical-cot.json
│   │   ├── llama-3.2-3b.json
│   │   ├── gemma3n-e2b.json
│   │   ├── phi-4-mini.json
│   │   ├── qwen3.5-4b.json
│   │   └── gemini-flash.json
│   ├── 02-htn-stable-fu/
│   │   └── ...
│   └── ... (50 transcript dirs)
├── hp/
│   └── ... (same structure)
└── dap/
    └── ... (same structure)
```

Total: 50 transcripts × 3 templates × 8 models = **1,200 response files**

### Eval harness script

`evals/scripts/run-models.py` — orchestrates the full collection:
- Iterates templates → transcripts → models
- Runs local models sequentially (one at a time to avoid memory contention on 8GB)
- Runs Gemini via API in parallel where possible
- Supports resuming (skips existing output files)
- Logs progress and errors

---

## Step 4: Score — Heuristic

_TODO_

---

## Step 5: Score — LLM-as-Judge (Claude Opus)

Claude Opus is the **primary and trusted judge**. It has no conflict of interest — it is not a candidate model.

Each note is scored against the **source transcript** (the ground truth). The judge does not compare notes to each other or to a reference note — it evaluates how well each model extracted and formatted the information from the transcript.

### Judge
- **Claude Opus 4** — `claude-opus-4-6`

### Input per judgment call
Each judge receives:
1. The original transcript (ground truth)
2. The template used
3. The model's generated note
4. The scoring rubric (from Step 1)

### Output per judgment call
Structured JSON with:
- Score for each dimension (0-3)
- Brief rationale for each score
- Any specific hallucinated content flagged (with quotes)

### Results stored in:
```
evals/results/claude-opus-judge/
```

---

## Step 5b: Rubric Revision & Re-Scoring

After reviewing Round 1 scores and the judge's rationales side-by-side with generated notes, three issues were identified (full details in `reflections/01-soap-rubric-issues.md`):

1. **Double-penalization of misplaced content** — content in the wrong SOAP section was penalized on both completeness and template adherence. Fix: penalize template_adherence only.
2. **Clinical boilerplate flagged as hallucination** — standard defaults ("alert and oriented," "NKDA," "well-appearing," "in no acute distress") were scored as fabrications. Fix: exempt these from hallucination scoring.
3. **Equal dimension weighting** — entity marking (broken for all local models) carried the same weight as hallucination and completeness. Fix: weighted overall scoring (Halluc. 2x, Complete 2x, Entities 0.5x, rest 1x).

Fixes 1 and 2 are applied to the judge prompt in `score-notes.py` and `score-notes-gemini.py`. Fix 3 is applied in `analyze-scores.py`. All SOAP notes are being re-scored with the updated rubric.

---

## Step 6: Score — LLM-as-Judge (Gemini, Bias Experiment)

Run Gemini 2.5 Pro as a **second judge** using the identical rubric and inputs. This is an experiment to detect self-scoring bias, since Gemini is also a candidate model.

### Bias Detection Methodology

Run Gemini as a second judge after Claude, then compare:

1. **Score gap analysis** — If Claude-judge gives Gemini-candidate an average score of 2.7 and all local models average 1.8, that's a 0.9 gap. If Gemini-judge gives Gemini-candidate 2.95 but local models 1.5, the gap widened to 1.45. That inflation is the bias signal.
2. **Relative ranking comparison** — Look at how each judge scores Gemini-candidate *relative to* the other models. If both judges agree Gemini is best but disagree on *how much better*, Gemini-judge is likely inflating its own outputs.
3. **Per-dimension breakdown** — The bias may show up only on subjective dimensions (completeness, instruction following) but not on objective ones (entity marking syntax, duplication). That pattern would confirm it.

### Why this matters

Gemini almost certainly *is* the best candidate — it's a frontier cloud model. Claude-as-judge will show that too, since it has no reason to penalize Gemini. The point isn't whether Gemini wins (it will), it's by *how much*, because that tells us how close our best local model gets to frontier quality. That's the whole purpose of including Gemini as a candidate.

**Bottom line:** Claude is the trusted judge. Gemini-as-second-judge is an experiment to quantify bias. The real deliverable is: "our best local model scores X% of frontier quality on each dimension."

### Results stored in:
```
evals/results/gemini-pro-judge/
```

---

---

## Step 7: Analyze Results

_TODO_
