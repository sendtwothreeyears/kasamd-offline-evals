#!/usr/bin/env python3
"""
Convert patient-doctor dialogue transcripts into doctor dictation format.

Reads dialogues from transcripts/patient-doctor-conversations/ and writes
doctor dictations to transcripts/dictations/, preserving all clinical content.

Usage:
    python evals/scripts/convert-to-dictations.py              # convert selected 25
    python evals/scripts/convert-to-dictations.py --dry-run    # preview what would be converted
    python evals/scripts/convert-to-dictations.py --all        # convert all 50
"""

import argparse
import os
import re
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_DIR.parent
SOURCE_DIR = EVALS_DIR / "transcripts" / "patient-doctor-conversations"
OUTPUT_DIR = EVALS_DIR / "transcripts" / "dictations"

FRONTMATTER_RE = re.compile(r"^(---\s*\n.*?\n---\s*\n)", re.DOTALL)

# The 25 selected transcripts for the eval subset
SELECTED = [
    "01-htn-new-dx", "03-htn-uncontrolled", "04-dm2-routine-fu",
    "05-dm2-elevated-a1c", "06-hyperlipidemia-statin", "09-asthma-exacerbation",
    "14-multimorbid",
    "15-uri-viral", "17-strep-pharyngitis", "19-uti",
    "22-low-back-pain", "25-headache-migraine", "26-gout-flare",
    "27-depression-new", "29-anxiety-gad", "31-insomnia", "33-substance-use",
    "34-annual-physical", "35-well-child", "37-preop-clearance",
    "41-gerd", "42-ibs",
    "44-eczema", "45-suspicious-mole",
    "50-polypharmacy",
]

CONVERSION_PROMPT = """\
You are converting a patient-doctor dialogue transcript into a doctor dictation.

A doctor dictation is a voice recording made by the doctor AFTER the patient encounter, \
narrating what happened during the visit. It is spoken in first person from the doctor's \
perspective and sounds natural, as if the doctor is speaking into a recorder.

Rules:
1. Preserve ALL clinical information from the dialogue — every symptom, finding, vital sign, \
medication, lab order, diagnosis, plan item, and counseling point
2. Use natural dictation style — not overly formal, includes filler words and natural speech \
patterns (e.g., "um", "so", "basically", "went ahead and")
3. First person from the doctor's perspective (e.g., "I saw the patient today for...", \
"On exam, blood pressure was...")
4. Do NOT add any information not present in the original dialogue
5. Do NOT remove any clinical details, even minor ones
6. Keep the same level of clinical specificity (exact numbers, drug names, dosages)
7. The output should feel like a real doctor talking into a phone or recorder after seeing a patient
8. Do NOT include any preamble or explanation — output ONLY the dictation text

Example style:
"So I saw Mr. Johnson today, he's a 52-year-old gentleman coming in for follow-up on his \
blood pressure. Um, he's been on lisinopril 10 milligrams for about three months now. \
Blood pressure today was 128 over 82, which is much better than last time. He says he's \
been taking it regularly, no side effects. I think we'll keep him on the current dose and \
recheck in six months. Went ahead and ordered a BMP just to check his potassium and \
kidney function on the lisinopril."

Convert this dialogue into a doctor dictation:\
"""


def get_anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def convert_transcript(client, dialogue_text: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0.3,
        system="You convert patient-doctor dialogues into doctor dictation transcripts.",
        messages=[
            {"role": "user", "content": f"{CONVERSION_PROMPT}\n\n{dialogue_text}"},
        ],
    )
    return response.content[0].text.strip()


def main():
    parser = argparse.ArgumentParser(description="Convert dialogues to dictations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be converted")
    parser.add_argument("--all", action="store_true", help="Convert all 50, not just selected 25")
    args = parser.parse_args()

    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}", file=sys.stderr)
        sys.exit(1)

    # Gather files to convert
    if args.all:
        files = sorted(SOURCE_DIR.glob("*.txt"))
    else:
        files = [SOURCE_DIR / f"{name}.txt" for name in SELECTED]
        files = [f for f in files if f.exists()]

    if not files:
        print("No files to convert.", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {len(files)} dialogues to dictations")
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    if args.dry_run:
        for f in files:
            print(f"  {f.stem}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_anthropic_client()

    for i, filepath in enumerate(files, 1):
        name = filepath.stem
        print(f"  [{i}/{len(files)}] {name}...", end=" ", flush=True)

        raw_text = filepath.read_text()

        # Extract frontmatter and dialogue separately
        frontmatter = ""
        dialogue = raw_text
        fm_match = FRONTMATTER_RE.match(raw_text)
        if fm_match:
            frontmatter = fm_match.group(1)
            dialogue = raw_text[fm_match.end():].strip()

        dictation = convert_transcript(client, dialogue)

        # Write with original frontmatter preserved
        out_path = OUTPUT_DIR / filepath.name
        out_path.write_text(frontmatter + dictation + "\n")

        print("done")

    print(f"\nConverted {len(files)} transcripts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
