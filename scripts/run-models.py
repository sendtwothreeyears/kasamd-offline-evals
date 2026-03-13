#!/usr/bin/env python3
"""
Eval harness — Run all candidate models against test transcripts and templates.

Self-contained: all prompts and config live here.

Usage:
    python evals/scripts/run-models.py                          # run everything
    python evals/scripts/run-models.py --template soap           # SOAP only
    python evals/scripts/run-models.py --model gemma3n-e2b       # one model only
    python evals/scripts/run-models.py --transcript 01           # one transcript only
    python evals/scripts/run-models.py --dry-run                 # show what would run
"""

import argparse
import gc
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
MODELS_DIR = EVALS_DIR / "models"
RESULTS_DIR = EVALS_DIR / "results" / "responses"

# ---------------------------------------------------------------------------
# System prompt (self-contained — frozen for eval consistency)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a medical documentation assistant. Your task is to generate a structured clinical note based on a patient encounter transcription.

CRITICAL OUTPUT FORMAT:
- Use markdown headings for section headers (# for top-level sections, ## for sub-sections, ### for sub-sub-sections)
- Use regular paragraphs for content
- Use - for bullet points when listing items

CLINICAL ENTITY MARKING:
When mentioning medications or medical conditions, wrap them using double curly braces:
- Medications: {{drug:medication name}}
- Conditions/Diagnoses: {{condition:condition name}}

Rules for entity marking:
- Only mark the FIRST occurrence of each unique drug or condition
- Use the name as it appears naturally in the note (generic or brand as appropriate)
- Do not mark symptoms, procedures, or lab values—only confirmed diagnoses and medications
- Maintain natural sentence flow; the curly braces should wrap the term seamlessly

Examples:
- "Patient has {{condition:type 2 diabetes}} managed with {{drug:metformin}} 500mg twice daily. We discussed increasing metformin to 1000mg." (note: second "metformin" is NOT marked)
- "History of {{condition:hypertension}}, currently on {{drug:lisinopril}} 10mg."

CRITICAL RULES - FOLLOW EXACTLY:
1. Use ONLY information explicitly stated in the transcription
2. Follow the template structure EXACTLY as provided
3. If a section was discussed (even if findings are "none", "negative", or "no issues"), document what was stated - do NOT write "Not documented"
4. Only write "Not documented" if the topic was truly never mentioned in the transcription
5. ANY TEXT IN PARENTHESES () OR SQUARE BRACKETS [] IN THE TEMPLATE IS AN INSTRUCTION FOR YOU - DO NOT INCLUDE IT IN YOUR OUTPUT
6. For Review of Systems: If the template contains instructions like "(Only include systems that were discussed)", follow that instruction but DO NOT output that text
7. For Physical Examination: Keep findings organized by body system or subsection as shown in the template. Do not combine multiple systems under a single heading
8. Preserve exact template formatting for structured data (like vital signs on separate lines)
9. Do NOT invent, assume, or extrapolate any clinical information beyond what is stated
10. Maintain professional medical terminology and abbreviations as used in the transcription
11. Return ONLY the completed note - no preamble, explanations, or additional commentary
12. STRIP OUT all parenthetical instructions, bracketed instructions, or any text that says "[INSTRUCTION:", "(Only include", etc.\
"""

USER_PROMPT_TEMPLATE = """\
TEMPLATE:
{template_text}

---

TRANSCRIPTION:
{transcript_text}

Generate a complete medical note by filling in the template above with information from the transcription. Use markdown headings (# ## ###) for section headers and regular text for content. Remember: any text in parentheses () or square brackets [] in the template are instructions for you - follow them but DO NOT include them in your output.\
"""

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

LOCAL_MODELS = {
    "medgemma-1.5-4b": {
        "path": "medgemma-1.5-4b-it-4bit",
        "display": "MedGemma 1.5 4B IT",
    },
    "medgemma-4b": {
        "path": "medgemma-4b-it-4bit",
        "display": "MedGemma 4B IT",
    },
    "llama3-medical-cot": {
        "path": "llama3-3b-medical-cot-4bit",
        "display": "LLAMA3-3B-Medical-COT",
    },
    "llama-3.2-3b": {
        "path": "llama-3.2-3b-instruct-4bit",
        "display": "Llama 3.2 3B Instruct",
    },
    "gemma3n-e2b": {
        "path": "gemma-3n-e2b-4bit",
        "display": "Gemma3N E2B",
    },
    "phi-4-mini": {
        "path": "phi-4-mini-instruct-4bit",
        "display": "Phi-4 Mini",
    },
    "qwen3.5-4b": {
        "path": "qwen3.5-4b-4bit",
        "display": "Qwen3.5 4B",
    },
}

CLOUD_MODELS = {
    "gemini-flash": {
        "display": "Gemini 2.5 Flash",
        "model_id": "gemini-2.5-flash",
    },
}

ALL_MODEL_KEYS = list(LOCAL_MODELS.keys()) + list(CLOUD_MODELS.keys())

TEMPLATES = ["soap", "hp", "dap"]

# ---------------------------------------------------------------------------
# Transcript & template loading
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def load_transcript(path: Path) -> str:
    """Load a transcript file, stripping YAML frontmatter."""
    text = path.read_text()
    return FRONTMATTER_RE.sub("", text).strip()


def load_template(name: str) -> str:
    """Load a template file by name (soap, hp, dap)."""
    path = TEMPLATES_DIR / f"{name}.txt"
    return path.read_text().strip()


def get_transcript_id(path: Path) -> str:
    """Extract transcript ID from filename, e.g., '01-htn-new-dx'."""
    return path.stem


def build_messages(template_text: str, transcript_text: str) -> list[dict]:
    """Build the chat messages for a model call."""
    user_content = USER_PROMPT_TEMPLATE.format(
        template_text=template_text,
        transcript_text=transcript_text,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Local model runner (mlx-lm)
# ---------------------------------------------------------------------------

class LocalModelRunner:
    """Loads an MLX model once and runs it on multiple inputs."""

    def __init__(self, model_key: str):
        from mlx_lm import load
        from mlx_lm.sample_utils import make_sampler

        self.model_key = model_key
        model_info = LOCAL_MODELS[model_key]
        model_path = str(MODELS_DIR / model_info["path"])

        print(f"  Loading {model_info['display']} from {model_path}...")
        self.model, self.tokenizer = load(model_path)
        self.sampler = make_sampler(temp=0.1)
        print(f"  Model loaded.")

    def generate(self, template_text: str, transcript_text: str) -> dict:
        """Generate a note and return result with metadata."""
        from mlx_lm.generate import stream_generate

        messages = build_messages(template_text, transcript_text)

        # Apply chat template to get the raw prompt string
        if hasattr(self.tokenizer, "apply_chat_template"):
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            # Fallback for models without chat template
            user_content = messages[1]["content"]
            prompt = f"System: {SYSTEM_PROMPT}\n\nUser: {user_content}\n\nAssistant:"

        # Stream generate to capture full metadata from last response chunk
        text = ""
        last_response = None
        for response in stream_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=16384,
            sampler=self.sampler,
        ):
            text += response.text
            last_response = response

        metadata = {}
        if last_response:
            metadata = {
                "inference_time_s": round(
                    last_response.generation_tokens / last_response.generation_tps, 2
                ) if last_response.generation_tps > 0 else 0,
                "prompt_tokens": last_response.prompt_tokens,
                "tokens_generated": last_response.generation_tokens,
                "prompt_tps": round(last_response.prompt_tps, 1),
                "tokens_per_sec": round(last_response.generation_tps, 1),
                "peak_memory_gb": round(last_response.peak_memory, 2),
            }

        return {
            "generated_note": text,
            "metadata": metadata,
        }

    def unload(self):
        """Release model from memory."""
        del self.model
        del self.tokenizer
        del self.sampler
        gc.collect()


# ---------------------------------------------------------------------------
# Cloud model runner (Gemini)
# ---------------------------------------------------------------------------

def run_gemini(template_text: str, transcript_text: str) -> dict:
    """Run Gemini 2.5 Flash via Google AI API."""
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set. Add it to .env or environment.")

    client = genai.Client(api_key=api_key)
    model_id = CLOUD_MODELS["gemini-flash"]["model_id"]

    user_content = USER_PROMPT_TEMPLATE.format(
        template_text=template_text,
        transcript_text=transcript_text,
    )

    start = time.perf_counter()
    response = client.models.generate_content(
        model=model_id,
        contents=[
            {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_content}"}]},
        ],
        config={
            "temperature": 0.1,
            "max_output_tokens": 16384,
        },
    )
    elapsed = time.perf_counter() - start

    text = response.text
    usage = getattr(response, "usage_metadata", None)
    tokens_generated = usage.candidates_token_count if usage else len(text.split())
    prompt_tokens = usage.prompt_token_count if usage else 0

    return {
        "generated_note": text,
        "metadata": {
            "inference_time_s": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "tokens_generated": tokens_generated,
            "tokens_per_sec": round(tokens_generated / elapsed, 1) if elapsed > 0 else 0,
        },
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def save_result(
    model_key: str, template_name: str, transcript_path: Path, result: dict
) -> Path:
    """Save a result to disk."""
    transcript_id = get_transcript_id(transcript_path)
    out_dir = RESULTS_DIR / template_name / transcript_id
    out_file = out_dir / f"{model_key}.json"

    output = {
        "transcript_id": transcript_id,
        "template": template_name,
        "model": model_key,
        **result,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output, indent=2))
    return out_file


def result_exists(model_key: str, template_name: str, transcript_path: Path) -> bool:
    """Check if a result file already exists (for resume support)."""
    transcript_id = get_transcript_id(transcript_path)
    out_file = RESULTS_DIR / template_name / transcript_id / f"{model_key}.json"
    return out_file.exists()


def main():
    parser = argparse.ArgumentParser(description="Run eval models on test transcripts")
    parser.add_argument("--template", choices=TEMPLATES, help="Run only this template")
    parser.add_argument("--model", choices=ALL_MODEL_KEYS, help="Run only this model")
    parser.add_argument("--transcript", help="Run only transcripts matching this prefix (e.g., '01')")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run, don't execute")
    args = parser.parse_args()

    # Gather inputs
    templates = [args.template] if args.template else TEMPLATES
    models = [args.model] if args.model else ALL_MODEL_KEYS

    transcripts = sorted(TRANSCRIPTS_DIR.glob("*.txt"))
    if args.transcript:
        transcripts = [t for t in transcripts if t.name.startswith(args.transcript)]

    if not transcripts:
        print("No transcripts found.", file=sys.stderr)
        sys.exit(1)

    # Build run plan — group by model so we load each model once
    # Order: for each model, run all template × transcript combos
    runs = []
    for model_key in models:
        for template_name in templates:
            for transcript_path in transcripts:
                already_done = result_exists(model_key, template_name, transcript_path)
                runs.append((model_key, template_name, transcript_path, already_done))

    total = len(runs)
    skipped = sum(1 for _, _, _, done in runs if done)
    to_run = total - skipped

    print(f"Eval plan: {total} total ({skipped} done, {to_run} remaining)")
    print(f"  Templates: {templates}")
    print(f"  Models: {models}")
    print(f"  Transcripts: {len(transcripts)}")
    print()

    if args.dry_run:
        for model_key, template_name, transcript_path, done in runs:
            status = "SKIP" if done else "RUN"
            print(f"  [{status}] {model_key} / {template_name} / {transcript_path.stem}")
        return

    # Execute — load each local model once, run all its tasks, then unload
    completed = 0
    errors = 0
    current_model_key = None
    runner = None

    # Pre-load templates (small, no need to re-read each time)
    template_cache = {name: load_template(name) for name in templates}

    for model_key, template_name, transcript_path, already_done in runs:
        if already_done:
            continue

        # Load model if changed
        if model_key != current_model_key:
            # Unload previous model
            if runner is not None:
                runner.unload()
                runner = None

            current_model_key = model_key
            display = (
                LOCAL_MODELS.get(model_key, CLOUD_MODELS.get(model_key, {}))
                .get("display", model_key)
            )
            print(f"\n{'='*60}")
            print(f"Model: {display}")
            print(f"{'='*60}")

            if model_key in LOCAL_MODELS:
                runner = LocalModelRunner(model_key)

        transcript_id = get_transcript_id(transcript_path)
        label = f"{template_name}/{transcript_id}"

        try:
            print(f"  {label}...", end=" ", flush=True)

            template_text = template_cache[template_name]
            transcript_text = load_transcript(transcript_path)

            if model_key in LOCAL_MODELS:
                result = runner.generate(template_text, transcript_text)
            else:
                result = run_gemini(template_text, transcript_text)

            save_result(model_key, template_name, transcript_path, result)

            tps = result["metadata"].get("tokens_per_sec", 0)
            tokens = result["metadata"].get("tokens_generated", 0)
            print(f"{tokens} tokens, {tps} tok/s")
            completed += 1

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    # Cleanup
    if runner is not None:
        runner.unload()

    print(f"\n{'='*60}")
    print(f"Complete: {completed} runs, {errors} errors, {skipped} skipped")
    print(f"Results in: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
