# Clinical Note Generation — Model Evals

Evaluation of 8 candidate models for offline clinical note generation (transcript → SOAP notes) on Apple Silicon Macs with 8GB RAM.

## Results

All generated notes and scores are pre-committed — browse them directly:

| What | Location |
|------|----------|
| Generated notes (8 models × 25 transcripts) | `results/responses/soap/` |
| Claude Opus judge scores | `results/claude-opus-judge/soap/` |
| Scoring rubric & methodology | [plan.md](plan.md) |
| Rubric revisions & rationale | [reflections/](reflections/) |
| Final presentation | [presentation/](presentation/) |

To produce summary tables (CSVs saved to each judge's folder):
```bash
python evals/scripts/analyze-scores.py                  # Claude Opus → results/claude-opus-judge/results-weighted.csv
python evals/scripts/analyze-scores.py --gemini         # Gemini Pro → results/gemini-pro-judge/results-weighted.csv
python evals/scripts/analyze-scores.py --claude --gemini # both
```

Overall scores use clinical utility weights (Hallucination 2x, Completeness 2x, Entity Marking 0.5x, rest 1x). See [reflections/01-soap-rubric-issues.md](reflections/01-soap-rubric-issues.md) for rationale.

## Candidate Models

| # | Model | Type | Params |
|---|-------|------|--------|
| 1 | MedGemma 1.5 4B IT | Medical-specialist | 4B |
| 2 | MedGemma 4B IT | Medical-specialist | 4B |
| 3 | LLAMA3-3B-Medical-COT | Medical-specialist | 3B |
| 4 | Llama 3.2 3B Instruct | General-purpose | 3B |
| 5 | Gemma3N E2B (baseline) | General-purpose | ~4B |
| 6 | Phi-4 Mini | General-purpose | 3.8B |
| 7 | Qwen3.5 4B | General-purpose | 4B |
| 8 | Gemini 2.5 Flash (cloud) | Frontier benchmark | — |

Gemini is included for **benchmarking only** — it establishes a quality ceiling to measure how close local models get to frontier performance.

## Running from Scratch

If you want to regenerate everything yourself:

### 1. Prerequisites

- Apple Silicon Mac (M1+)
- Python 3.11+ with `mlx-lm`, `huggingface-hub`, `google-genai`, and `anthropic`
  ```bash
  cd sidecar && uv sync
  uv add google-genai anthropic
  ```

### 2. API Keys

```bash
cp .env.example .env
# Edit .env and add your keys:
#   ANTHROPIC_API_KEY  — for Claude Opus judge
#   GOOGLE_API_KEY     — for Gemini candidate model and Gemini Pro judge
```

### 3. Download Models

```bash
./evals/download-models.sh          # download all 7 local models (~15-20GB)
```

MedGemma 1.5 4B IT is gated — accept terms at [huggingface.co/google/medgemma-1.5-4b-it](https://huggingface.co/google/medgemma-1.5-4b-it) and run `huggingface-cli login` first.

### 4. Generate Notes

```bash
./evals/run-evals.sh                # run all models × all templates
./evals/run-evals.sh --template soap --model gemma3n-e2b  # filter by template/model
./evals/run-evals.sh --dry-run      # preview without running
```

### 5. Score Notes

```bash
python evals/scripts/score-notes.py                     # Claude Opus judge
python evals/scripts/score-notes-gemini.py               # Gemini Pro judge (optional)
```

Both scripts are resumable — safe to stop and restart.

## Project Structure

```
evals/
├── README.md
├── plan.md                  # eval methodology, rubric, transcript selection
├── presentation/            # final presentation
├── reflections/             # rubric revisions and scoring change rationale
├── scripts/
│   ├── run-models.py            # eval harness (called by run-evals.sh)
│   ├── score-notes.py           # Claude Opus judge
│   ├── score-notes-gemini.py    # Gemini Pro judge
│   ├── analyze-scores.py        # aggregate scores into tables
│   └── convert-to-dictations.py # convert conversations to dictations
├── templates/               # note templates (SOAP, H&P, DAP)
├── transcripts/
│   ├── dictations/              # 25 doctor dictation transcripts (eval inputs)
│   └── patient-doctor-conversations/  # 50 source conversations (future testing)
├── models/                  # model weights (gitignored, ~15-20GB)
├── download-models.sh
├── run-evals.sh
└── results/
    ├── responses/           # generated notes from all 8 models
    ├── claude-opus-judge/   # Claude Opus scores
    └── gemini-pro-judge/    # Gemini Pro scores (gitignored)
```

## Disclaimer

These evaluations are for **development purposes only**. The outputs of these models are **not validated for clinical use** and should not be used to inform diagnosis, treatment, or any patient care decisions. All generated notes require clinician review and editing before use in a clinical setting.
