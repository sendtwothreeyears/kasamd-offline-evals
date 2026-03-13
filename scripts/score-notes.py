#!/usr/bin/env python3
"""
Score generated notes using Claude Opus as judge.

Sends each generated note + source transcript + template + rubric to Claude Opus,
which returns structured scores on all eval dimensions.

Usage:
    python evals/scripts/score-notes.py                          # score all unscored notes
    python evals/scripts/score-notes.py --template soap           # one template only
    python evals/scripts/score-notes.py --model medgemma-1.5-4b   # one model only
    python evals/scripts/score-notes.py --transcript 01            # one transcript only
    python evals/scripts/score-notes.py --dry-run                  # show what would be scored
    python evals/scripts/score-notes.py --max 10                   # score at most 10 notes
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

EVALS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_DIR.parent
TRANSCRIPTS_DIR = EVALS_DIR / "transcripts" / "dictations"
TEMPLATES_DIR = EVALS_DIR / "templates"
RESPONSES_DIR = EVALS_DIR / "results" / "responses"
SCORES_DIR = EVALS_DIR / "results" / "claude-opus-judge"

# ---------------------------------------------------------------------------
# Models & templates (must match run-models.py)
# ---------------------------------------------------------------------------

ALL_MODEL_KEYS = [
    "medgemma-1.5-4b", "medgemma-4b", "llama3-medical-cot",
    "llama-3.2-3b", "gemma3n-e2b", "phi-4-mini", "qwen3.5-4b",
    "gemini-flash",
]

TEMPLATES = ["soap", "hp", "dap"]

# ---------------------------------------------------------------------------
# Scoring rubric (embedded for self-contained eval)
# ---------------------------------------------------------------------------

SCORING_RUBRIC = """\
Score the generated clinical note on each dimension using a 0-3 scale.

## Dimensions

### Hallucination (0-3)
- 0: Fabricated findings/diagnosis with no basis in transcript
- 1: Fabricated detail that cannot be extrapolated from transcript
- 2: Minor embellishment beyond what transcript supports
- 3: No hallucination — all content is stated or reasonably inferred from transcript

### Instruction Following (0-3)
- 0: Ignored key instructions (e.g., fabricated instead of "Not documented")
- 1: Ignored some instructions
- 2: Minor deviation
- 3: Perfect

### Completeness (0-3)
- 0: Missed key findings
- 1: Missed important detail
- 2: Minor omission
- 3: Captured everything in transcript

### Template Adherence (0-3)
- 0: Unstructured output
- 1: Sections missing/wrong
- 2: Minor formatting issue
- 3: Perfect structure

### Entity Marking (0-3)
- 0: No entity marking attempted
- 1: Incorrect syntax or marked wrong entity types (e.g., procedures instead of drugs/conditions)
- 2: Correct syntax but errors (e.g., marked repeated occurrences, missed obvious entities)
- 3: Correct {{drug:...}} / {{condition:...}} syntax, first-occurrence-only, drugs and conditions only

### Duplication (0 or 1)
- 0: No duplication
- 1: Output repeated (any section or full note duplicated)\
"""

JUDGE_SYSTEM_PROMPT = """\
You are a clinical documentation quality evaluator. Your job is to score a generated clinical note by comparing it against the source transcript and template.

You must be precise, consistent, and objective. Score strictly based on the rubric — do not infer intent or give benefit of the doubt.

IMPORTANT:
- The transcript is the ONLY source of truth. Any information in the note that is not in the transcript is a hallucination.
- "Reasonably inferred" means standard medical shorthand or obvious implications (e.g., if the transcript says "blood pressure 140/90" and the note says "elevated blood pressure", that is reasonable inference, NOT hallucination).
- Template instructions in parentheses () or brackets [] should NOT appear in the output. If they do, that is an instruction-following failure.
- Entity marking uses {{drug:medication name}} and {{condition:condition name}} syntax. Only the FIRST occurrence of each entity should be marked.

BIAS CONTROLS — follow these strictly:
- VERBOSITY: Do NOT reward length. A concise note that captures all transcript content should score the same as a verbose one. Unnecessary filler, redundant phrasing, or padding should not improve any score.
- SYCOPHANCY: A confident tone does NOT indicate correctness. Score strictly against the transcript, not how authoritative the note sounds. Confident but wrong content is still a hallucination.
- SELF-PREFERENCE: Score every note identically regardless of which model generated it. You must not favor outputs that resemble your own style.
- POSITION: Evaluate each note independently. Do not compare it to other notes or let prior judgments influence the current score.

SCORING CLARIFICATIONS:
1. MISPLACED CONTENT: If content from the transcript is present in the generated note but placed in the wrong section, penalize template_adherence only. Do NOT also penalize completeness — the information was captured. Completeness measures whether transcript content appears in the note at all, regardless of placement.
2. CLINICAL DEFAULTS: The following are considered standard clinical defaults and should NOT be scored as hallucinations: "alert and oriented," "no known drug allergies" (when allergies were not discussed), "well-appearing," and "in no acute distress." These are ubiquitous in real clinical documentation and their inclusion reflects standard practice, not fabrication. However, any clinical detail beyond these standard defaults (e.g., specific exam findings, specific diagnoses, specific medications) that is not in the transcript IS still a hallucination.\
"""

JUDGE_USER_PROMPT = """\
## Scoring Rubric

{rubric}

---

## Source Transcript (Ground Truth)

{transcript}

---

## Template Used

{template}

---

## Generated Note (To Score)

{note}

---

## Instructions

Score the generated note above against the source transcript using the rubric.

Return ONLY a JSON object with this exact structure (no markdown fencing, no explanation outside the JSON):

{{
  "hallucination": {{
    "score": <0-3>,
    "rationale": "<1-2 sentences>",
    "flagged_content": ["<quoted text from note that is hallucinated, if any>"]
  }},
  "instruction_following": {{
    "score": <0-3>,
    "rationale": "<1-2 sentences>"
  }},
  "completeness": {{
    "score": <0-3>,
    "rationale": "<1-2 sentences>",
    "missed_items": ["<key items from transcript missing in note, if any>"]
  }},
  "template_adherence": {{
    "score": <0-3>,
    "rationale": "<1-2 sentences>"
  }},
  "entity_marking": {{
    "score": <0-3>,
    "rationale": "<1-2 sentences>"
  }},
  "duplication": {{
    "score": <0 or 1>,
    "rationale": "<1 sentence>"
  }}
}}\
"""

# ---------------------------------------------------------------------------
# Transcript & template loading
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def load_transcript(path: Path) -> str:
    text = path.read_text()
    return FRONTMATTER_RE.sub("", text).strip()


def load_template(name: str) -> str:
    path = TEMPLATES_DIR / f"{name}.txt"
    return path.read_text().strip()


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def get_anthropic_client():
    """Create Anthropic client, loading API key from env or .env file."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env or environment.",
              file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic",
              file=sys.stderr)
        sys.exit(1)

    return anthropic.Anthropic(api_key=api_key)


def score_note(client, transcript_text: str, template_text: str, note_text: str) -> dict:
    """Send a note to Claude Opus for scoring. Returns parsed score dict."""
    user_prompt = JUDGE_USER_PROMPT.format(
        rubric=SCORING_RUBRIC,
        transcript=transcript_text,
        template=template_text,
        note=note_text,
    )

    start = time.perf_counter()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
        system=JUDGE_SYSTEM_PROMPT,
        temperature=0.0,
    )
    elapsed = time.perf_counter() - start

    raw_text = response.content[0].text.strip()

    # Parse JSON — strip markdown fencing if present
    json_text = raw_text
    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\s*\n?", "", json_text)
        json_text = re.sub(r"\n?```\s*$", "", json_text)

    try:
        scores = json.loads(json_text)
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON parse error: {e}",
            "raw_response": raw_text,
            "judge_time_s": round(elapsed, 2),
        }

    scores["_meta"] = {
        "judge_model": "claude-opus-4-6",
        "judge_time_s": round(elapsed, 2),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return scores


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def score_exists(template_name: str, transcript_id: str, model_key: str) -> bool:
    out_file = SCORES_DIR / template_name / transcript_id / f"{model_key}.json"
    return out_file.exists()


def save_score(template_name: str, transcript_id: str, model_key: str,
               scores: dict, response_data: dict) -> Path:
    out_dir = SCORES_DIR / template_name / transcript_id
    out_file = out_dir / f"{model_key}.json"

    output = {
        "transcript_id": transcript_id,
        "template": template_name,
        "model": model_key,
        "scores": scores,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output, indent=2))
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Score generated notes with Claude Opus")
    parser.add_argument("--template", choices=TEMPLATES, help="Score only this template")
    parser.add_argument("--model", choices=ALL_MODEL_KEYS, help="Score only this model")
    parser.add_argument("--transcript", help="Score only transcripts matching this prefix")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scored")
    parser.add_argument("--max", type=int, default=0, help="Max notes to score (0 = all)")
    args = parser.parse_args()

    templates = [args.template] if args.template else TEMPLATES
    models = [args.model] if args.model else ALL_MODEL_KEYS

    # Build scoring plan from existing response files
    runs = []
    for template_name in templates:
        template_dir = RESPONSES_DIR / template_name
        if not template_dir.exists():
            continue
        for transcript_dir in sorted(template_dir.iterdir()):
            if not transcript_dir.is_dir():
                continue
            transcript_id = transcript_dir.name
            if args.transcript and not transcript_id.startswith(args.transcript):
                continue
            for model_key in models:
                response_file = transcript_dir / f"{model_key}.json"
                if not response_file.exists():
                    continue  # response not generated yet
                already_scored = score_exists(template_name, transcript_id, model_key)
                runs.append((template_name, transcript_id, model_key, response_file, already_scored))

    total = len(runs)
    skipped = sum(1 for *_, done in runs if done)
    to_score = total - skipped

    if args.max > 0:
        to_score = min(to_score, args.max)

    print(f"Scoring plan: {total} responses found ({skipped} already scored, {to_score} to score)")
    print(f"  Templates: {templates}")
    print(f"  Models: {models}")
    print(f"  Judge: Claude Opus 4 (claude-opus-4-6)")
    print()

    if args.dry_run:
        for template_name, transcript_id, model_key, _, done in runs:
            status = "SKIP" if done else "SCORE"
            print(f"  [{status}] {template_name}/{transcript_id}/{model_key}")
        return

    if to_score == 0:
        print("Nothing to score.")
        return

    # Load API client
    client = get_anthropic_client()

    # Pre-load templates
    template_cache = {name: load_template(name) for name in templates}

    # Pre-load transcripts
    transcript_cache = {}

    completed = 0
    errors = 0

    for template_name, transcript_id, model_key, response_file, already_scored in runs:
        if already_scored:
            continue

        if args.max > 0 and completed >= args.max:
            break

        # Load transcript (cached)
        if transcript_id not in transcript_cache:
            transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.txt"
            if not transcript_path.exists():
                print(f"  WARNING: transcript {transcript_id}.txt not found, skipping")
                continue
            transcript_cache[transcript_id] = load_transcript(transcript_path)

        # Load response
        response_data = json.loads(response_file.read_text())
        note_text = response_data.get("generated_note", "")

        if not note_text.strip():
            print(f"  SKIP (empty note): {template_name}/{transcript_id}/{model_key}")
            continue

        label = f"{template_name}/{transcript_id}/{model_key}"
        print(f"  {label}...", end=" ", flush=True)

        try:
            scores = score_note(
                client,
                transcript_cache[transcript_id],
                template_cache[template_name],
                note_text,
            )

            if "error" in scores:
                # Judge couldn't parse — treat as all-zero failure
                scores = {
                    "hallucination": {"score": 0, "rationale": "Judge could not score: " + scores["error"], "flagged_content": []},
                    "instruction_following": {"score": 0, "rationale": "Judge could not score"},
                    "completeness": {"score": 0, "rationale": "Judge could not score", "missed_items": []},
                    "template_adherence": {"score": 0, "rationale": "Judge could not score"},
                    "entity_marking": {"score": 0, "rationale": "Judge could not score"},
                    "duplication": {"score": 0, "rationale": "Judge could not score"},
                    "_meta": {"judge_model": "claude-opus-4-6", "judge_time_s": scores.get("judge_time_s", 0), "input_tokens": 0, "output_tokens": 0, "unscorable": True},
                }
                save_score(template_name, transcript_id, model_key, scores, response_data)
                print(f"UNSCORABLE (all zeros): {scores['hallucination']['rationale']}")
                errors += 1
            else:
                save_score(template_name, transcript_id, model_key, scores, response_data)
                # Print compact score summary
                h = scores.get("hallucination", {}).get("score", "?")
                i = scores.get("instruction_following", {}).get("score", "?")
                c = scores.get("completeness", {}).get("score", "?")
                t = scores.get("template_adherence", {}).get("score", "?")
                e = scores.get("entity_marking", {}).get("score", "?")
                d = scores.get("duplication", {}).get("score", "?")
                judge_time = scores.get("_meta", {}).get("judge_time_s", "?")
                print(f"H:{h} I:{i} C:{c} T:{t} E:{e} D:{d}  ({judge_time}s)")
                completed += 1

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"Complete: {completed} scored, {errors} errors, {skipped} previously scored")
    print(f"Scores in: {SCORES_DIR}")


if __name__ == "__main__":
    main()
