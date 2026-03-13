#!/usr/bin/env python3
"""
Analyze scored eval results and produce a single results table.

Reads all judge score files and computes average scores per dimension
as percentages (0-100%), sorted by overall mean. Outputs one clean table
to the terminal and exports results-weighted.csv to the judge's folder.

Overall score uses clinical utility weights:
  Hallucination 2x, Completeness 2x, Entity Marking 0.5x, rest 1x.
See evals/reflections/01-soap-rubric-issues.md for rationale.

Usage:
    python evals/scripts/analyze-scores.py                        # analyze Claude Opus scores (default)
    python evals/scripts/analyze-scores.py --gemini               # analyze Gemini Pro scores
    python evals/scripts/analyze-scores.py --claude --gemini      # analyze both
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

EVALS_DIR = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = EVALS_DIR / "transcripts" / "dictations"

JUDGES = {
    "claude-opus": "claude-opus-judge",
    "gemini-pro": "gemini-pro-judge",
}

SCORED_DIMENSIONS = [
    "hallucination",
    "completeness",
    "instruction_following",
    "template_adherence",
    "entity_marking",
]

BOOLEAN_DIMENSIONS = ["duplication"]

MODEL_DISPLAY = {
    "medgemma-1.5-4b": "MedGemma 1.5 4B",
    "medgemma-4b": "MedGemma 4B",
    "llama3-medical-cot": "Llama3 Medical COT",
    "llama-3.2-3b": "Llama 3.2 3B",
    "gemma3n-e2b": "Gemma 3n E2B",
    "phi-4-mini": "Phi-4 Mini",
    "qwen3.5-4b": "Qwen 3.5 4B",
    "gemini-flash": "Gemini 2.5 Flash",
}

DIMENSION_SHORT = {
    "hallucination": "No Halluc.",
    "instruction_following": "Instruct.",
    "completeness": "Complete",
    "template_adherence": "Format",
    "entity_marking": "Entities",
    "duplication": "No Dup.",
}

# Clinical utility weights — hallucination and completeness matter most,
# entity marking is non-differentiating for local models.
# See evals/reflections/01-soap-rubric-issues.md for rationale.
DIMENSION_WEIGHTS = {
    "hallucination": 2.0,
    "completeness": 2.0,
    "instruction_following": 1.0,
    "template_adherence": 1.0,
    "entity_marking": 0.5,
    "duplication": 1.0,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_scores(scores_dir: Path) -> list[dict]:
    """Load all score JSON files from a judge directory."""
    results = []
    if not scores_dir.exists():
        return results

    for template_dir in sorted(scores_dir.iterdir()):
        if not template_dir.is_dir():
            continue
        for transcript_dir in sorted(template_dir.iterdir()):
            if not transcript_dir.is_dir():
                continue
            for score_file in sorted(transcript_dir.glob("*.json")):
                data = json.loads(score_file.read_text())
                results.append(data)

    return results


def extract_scores(entry: dict) -> dict | None:
    """Extract dimension scores from a score entry. Returns None if malformed."""
    scores = entry.get("scores", {})
    if "error" in scores:
        return None

    result = {}
    for dim in SCORED_DIMENSIONS:
        dim_data = scores.get(dim, {})
        if isinstance(dim_data, dict) and "score" in dim_data:
            result[dim] = dim_data["score"]
        else:
            return None

    for dim in BOOLEAN_DIMENSIONS:
        dim_data = scores.get(dim, {})
        if isinstance(dim_data, dict) and "score" in dim_data:
            result[dim] = dim_data["score"]
        else:
            result[dim] = 0

    return result


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def compute_averages(entries: list[dict]) -> dict:
    """Compute per-model average score as percentage (0-100%) for each dimension.

    Overall is a weighted average using DIMENSION_WEIGHTS.

    Returns: { model: { dim: pct, ..., "No Dup.": pct, "Overall": pct } }
    """
    # model -> dimension -> [sum, count]
    raw = {}

    for entry in entries:
        model = entry.get("model", "unknown")
        scores = extract_scores(entry)
        if scores is None:
            continue

        if model not in raw:
            raw[model] = {dim: [0, 0] for dim in SCORED_DIMENSIONS + BOOLEAN_DIMENSIONS}

        for dim in SCORED_DIMENSIONS:
            raw[model][dim][0] += scores[dim]
            raw[model][dim][1] += 1

        for dim in BOOLEAN_DIMENSIONS:
            # duplication: 0 = no dup (good), 1 = dup (bad). Invert for "No Dup." %
            raw[model][dim][0] += (1 if scores[dim] == 0 else 0)
            raw[model][dim][1] += 1

    # Convert to percentages
    results = {}
    for model, dims in raw.items():
        results[model] = {}
        weighted_sum = 0.0
        weight_total = 0.0

        for dim in SCORED_DIMENSIONS:
            s, c = dims[dim]
            # Score is 0-3, convert to 0-100%
            pct = (s / (c * 3) * 100) if c > 0 else 0
            short = DIMENSION_SHORT.get(dim, dim)
            results[model][short] = round(pct)
            w = DIMENSION_WEIGHTS[dim]
            weighted_sum += pct * w
            weight_total += w
        for dim in BOOLEAN_DIMENSIONS:
            s, c = dims[dim]
            pct = (s / c * 100) if c > 0 else 0
            short = DIMENSION_SHORT.get(dim, dim)
            results[model][short] = round(pct)
            w = DIMENSION_WEIGHTS[dim]
            weighted_sum += pct * w
            weight_total += w
        results[model]["Overall"] = round(weighted_sum / weight_total) if weight_total > 0 else 0

    return results


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_results_table(averages: dict, judge_name: str, total_notes: int):
    """Print one comprehensive table sorted by mean."""
    dims = [DIMENSION_SHORT[d] for d in SCORED_DIMENSIONS] + \
           [DIMENSION_SHORT[d] for d in BOOLEAN_DIMENSIONS] + ["Overall"]

    # Sort by mean descending
    model_order = sorted(averages.keys(), key=lambda m: averages[m]["Overall"], reverse=True)

    # Column widths
    model_w = max(len(MODEL_DISPLAY.get(m, m)) for m in model_order)
    model_w = max(model_w, 5) + 2
    col_w = max(len(d) for d in dims) + 2

    # Title
    width = model_w + col_w * len(dims)
    print()
    print(f"  Judge: {judge_name}  |  {total_notes} notes scored")
    print(f"  Scores as % of maximum (higher = better)")
    print(f"  Weighted overall: Halluc. 2x, Complete 2x, Entities 0.5x, rest 1x")
    print()

    # Header
    header = f"  {'Model':<{model_w}}"
    for d in dims:
        header += f" {d:>{col_w}}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    # Rows
    for model in model_order:
        display = MODEL_DISPLAY.get(model, model)
        row = f"  {display:<{model_w}}"
        for d in dims:
            val = averages[model].get(d, 0)
            row += f" {val:>{col_w - 1}}%"
        print(row)

    print()


def export_csv(averages: dict, output_dir: Path):
    """Export results-weighted.csv to the judge's folder."""
    output_dir.mkdir(parents=True, exist_ok=True)

    dims = [DIMENSION_SHORT[d] for d in SCORED_DIMENSIONS] + \
           [DIMENSION_SHORT[d] for d in BOOLEAN_DIMENSIONS] + ["Overall"]

    csv_path = output_dir / "results-weighted.csv"
    with open(csv_path, "w") as f:
        f.write("Model," + ",".join(dims) + "\n")

        model_order = sorted(averages.keys(), key=lambda m: averages[m]["Overall"], reverse=True)
        for model in model_order:
            display = MODEL_DISPLAY.get(model, model)
            row = [display]
            for d in dims:
                row.append(f"{averages[model].get(d, 0)}%")
            f.write(",".join(row) + "\n")

    print(f"  Exported: {csv_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze eval scores")
    parser.add_argument("--claude", action="store_true", help="Analyze Claude Opus judge scores")
    parser.add_argument("--gemini", action="store_true", help="Analyze Gemini Pro judge scores")
    args = parser.parse_args()

    # Default to Claude if neither flag is set
    judges_to_run = []
    if args.claude or (not args.claude and not args.gemini):
        judges_to_run.append("claude-opus")
    if args.gemini:
        judges_to_run.append("gemini-pro")

    for judge_key in judges_to_run:
        scores_dir = EVALS_DIR / "results" / JUDGES[judge_key]
        entries = load_all_scores(scores_dir)

        if not entries:
            print(f"\nNo scores found in {scores_dir}")
            print(f"Run score-notes.py first to generate scores.")
            continue

        averages = compute_averages(entries)
        print_results_table(averages, judge_key, len(entries))
        export_csv(averages, scores_dir)
        print()


if __name__ == "__main__":
    main()
