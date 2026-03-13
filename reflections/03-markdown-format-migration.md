# Reflection 03: Migrating from Bold to Markdown Headings

**Date:** 2026-03-13
**Status:** Changes applied. Eval results need re-running.
**Depends on:** [01-soap-rubric-issues.md](./01-soap-rubric-issues.md), [02-scoring-changes.md](./02-scoring-changes.md)

---

## The Problem

The project had an internal inconsistency in how section headers were formatted, and the chosen format was fighting against how small language models naturally behave.

### What was happening

We were telling models to output `**Subjective**` (bold text) instead of `# Subjective` (markdown headings) for section headers in clinical notes. This was specified in:

- The system prompt in `run-models.py` (evals)
- The system prompt in `generateMedicalNote.ts` (online server)
- The system prompt in `gemma_engine.py` (offline sidecar)
- The eval templates (`soap.txt`, `hp.txt`, `dap.txt`)
- The app's template seeder (`systemTemplates.ts`)
- The documentation (`docs/prompts/medical-note-generation.md`)

The instruction was explicit: "Use **bold text** for section headers (NOT markdown headings)."

### Why this was a problem

**1. Small models can't follow it.** MedGemma 4B scored 24% on instruction following. Every LLM is pre-trained on massive amounts of markdown where `#` means "heading." Asking a 4B model to use `**bold**` as a heading is asking it to override deeply ingrained behavior — and it can't do that from a system prompt alone. This is the main reason instruction-following scores were so low across local models.

**2. It creates a fine-tuning tax.** If we fine-tune MedGemma 4B, every training example would need to teach the model a non-standard formatting convention. That's wasted training signal — we'd be spending capacity on teaching format quirks instead of teaching clinical documentation quality.

**3. Two different parsers, neither complete.** The project had two Lexical parsers:

| Parser | Location | Handled |
|--------|----------|---------|
| Server `textToLexical()` | `server/utils/editor/lexical.ts` | `**bold**` and `{{entity}}` — but no `#` headings, no `- bullets` |
| App `markdownToLexical()` | `app/src/lib/markdown-to-lexical.ts` | Full markdown via Lexical's `$convertFromMarkdownString` — but no `{{entity}}` support |

The offline app used the app parser, so:
- `# Subjective` would render correctly as a heading
- `**Subjective**` would render as bold paragraph text (visually similar but semantically different)
- `{{drug:metformin}}` would render as literal text `{{drug:metformin}}` — broken

The server used its own parser, so it handled entities but couldn't render proper headings or bullet lists.

**4. Templates and prompts were misaligned with the parser.** The templates said `**bold**`, the app parser understood markdown, and the models wanted to output markdown. Everyone was speaking a different language.

---

## The Decision

**Use standard markdown everywhere.** `# Heading`, `## Sub-heading`, `- bullets`.

### Why markdown wins

1. **It's what models know.** Every LLM's pre-training data is full of markdown. `# Heading` is the most natural way for a model to express "this is a section title." We stop fighting the model's training and start working with it.

2. **It's what Lexical already parses.** The app's `$convertFromMarkdownString` with the default `TRANSFORMERS` already handles headings, lists, bold, italic, links, code blocks — the full markdown spec. We don't need custom parsing for structure.

3. **It simplifies fine-tuning.** Training examples can use standard markdown, which means the model only needs to learn *what* to write (clinical content, entity markers), not *how* to format headers. Less format overhead = more capacity for clinical quality.

4. **It gives us proper semantic structure.** A `HeadingNode` in Lexical is semantically a heading — it can have different font sizes, be used for navigation, be exported correctly to PDF/HTML. A bold `TextNode` is just... bold text in a paragraph.

---

## What Changed

### Eval templates (`evals/templates/`)

| Before | After |
|--------|-------|
| `**Subjective**` | `# Subjective` |
| `**Chief Complaint**` | `## Chief Complaint` |
| `**Vital Signs:**` | `### Vital Signs` |

Heading hierarchy: `#` for top-level sections (Subjective, Objective, Assessment, Plan), `##` for sub-sections, `###` for sub-sub-sections.

### System prompts (6 files)

| File | Change |
|------|--------|
| `evals/scripts/run-models.py` | "Use markdown headings for section headers (# for top-level, ## for sub-sections, ### for sub-sub-sections)" |
| `server/utils/ai/generateMedicalNote.ts` | Same change |
| `server/utils/prompt.ts` | Standalone/fallback note template — all `**Section**` headers converted to `# Section` / `## Section` |
| `sidecar/src/engines/gemma_engine.py` | Example sections now use `# Subjective` format |
| `docs/prompts/medical-note-generation.md` | Documentation updated to match |
| `docs/prompts/standalone-note-template.md` | Documentation for fallback prompt updated to match `prompt.ts` |

### App template seeder (`app/src/lib/systemTemplates.ts`)

- `TemplateLine` type changed from `"bold" | "paragraph"` to `"heading" | "paragraph"` with optional `level` field
- `createEditorStateFromLines()` now creates `HeadingNode` via `$createHeadingNode()` instead of bold `TextNode`
- All 7 template arrays (SOAP, H&P, Progress, Discharge, Procedure, Consultation, DAP) updated
- `HeadingNode` added to `LEXICAL_NODES`

### Clinical entity support added to offline app

The app's markdown parser previously had no understanding of `{{drug:...}}` / `{{condition:...}}` markers — they rendered as literal text. Three files were added/changed to complete the pipeline:

| File | Change |
|------|--------|
| `app/src/lib/clinicalEntityNode.ts` | **New file.** Lexical `DecoratorNode` ported from server version. Renders entities as styled `<span>` with React `decorate()` method. Drugs: blue highlight. Conditions: amber highlight. |
| `app/src/lib/markdown-to-lexical.ts` | Added `$replaceEntityMarkers()` post-processing pass. After `$convertFromMarkdownString` parses standard markdown, walks all `TextNode`s, finds `{{drug:...}}` / `{{condition:...}}` via regex, splits into `ClinicalEntityNode` instances. Preserves original text formatting (bold, italic). |
| `app/src/components/sessions/SessionEditor.tsx` | Registered `ClinicalEntityNode` in `EDITOR_NODES` so the editor can deserialize and render entity nodes. |
| `app/src/index.css` | Added `.clinical-entity`, `.clinical-entity-drug` (blue), `.clinical-entity-condition` (amber) styles. |

This means the full chain now works end-to-end in the offline app: model outputs markdown with entity markers → parser creates heading nodes + entity nodes → editor renders structured note with highlighted drugs and conditions.

### NOT changed

- **`server/utils/editor/lexical.ts`** — The server's custom parser still uses the old `parseLineSegments()` approach with `**bold**` regex. This should eventually be migrated to use `$convertFromMarkdownString` + entity post-processing to match the app, but it's lower priority since the online server uses GPT-4o which can follow any format.
- **`evals/scripts/score-notes.py`** — The Template Adherence rubric is generic ("Perfect structure" vs "Sections missing/wrong") and doesn't mention bold vs headings specifically. No change needed — the judge scores against the provided template, which now uses markdown.

---

## Impact

### Eval results are invalidated

All existing results in `evals/results/` were generated with the old `**bold**` system prompt and templates. They need to be re-run:

```bash
# Re-generate all model responses with updated prompt/templates
python evals/scripts/run-models.py

# Re-score with both judges
python evals/scripts/score-notes.py --template soap
python evals/scripts/score-notes-gemini.py --template soap
python evals/scripts/analyze-scores.py --claude --gemini
```

### Expected score improvements

- **Instruction following** should improve across all local models — we're no longer asking them to do something unnatural
- **Template adherence** should improve — markdown headings match what models naturally produce
- **Completeness** and **hallucination** should be roughly unchanged — those measure content, not format
- **Entity marking** will still be low — this is a learned behavior that requires fine-tuning regardless of heading format

### Fine-tuning benefit

When we generate training data for fine-tuning MedGemma 4B, the training examples will use standard markdown. This means:
- The model's pre-training knowledge of markdown is reinforced, not overridden
- Training signal is focused on clinical quality and entity marking — the hard problems
- The fine-tuned model should generalize better because the format is familiar

### Database migration note

The `seedSystemTemplates()` function checks by template name to avoid duplicates. Existing installations already have the old bold-format templates seeded. Options:
1. Delete existing system templates from the database and re-seed
2. Add a version field to templates and update in place
3. Accept that existing installs keep old templates until a migration is added

---

## How This Affects Fine-Tuning MedGemma 4B

This migration directly shapes what the fine-tuned model needs to learn — and what it no longer needs to learn.

### What the model no longer needs to learn

**Heading format.** Before this change, every training example would have needed to teach the model "output `**Subjective**` not `# Subjective`" — a non-standard convention that contradicts pre-training. That's wasted LoRA capacity. Now training examples use standard markdown headings, which reinforces what the model already knows. The model doesn't need to spend adaptation budget on format quirks.

**Template structure.** With markdown headings, the model's pre-trained sense of document structure (h1 > h2 > h3) aligns with our heading hierarchy (SOAP sections > sub-sections > Vital Signs). The model is more likely to produce well-structured output even with minimal fine-tuning, because the structure mirrors patterns it has seen billions of times.

### What fine-tuning should now focus on

With format overhead removed, the LoRA adapters can focus on the three things the base model genuinely can't do from a prompt alone:

1. **Entity marking (3% score).** `{{drug:metformin}}` and `{{condition:hypertension}}` is novel syntax not in any pre-training data. This is the single highest-value target for fine-tuning. Every training example must demonstrate correct entity marking: right syntax, first-occurrence-only, drugs and conditions only (not symptoms, procedures, or labs).

2. **Clinical documentation patterns.** How to translate a messy doctor-patient conversation into structured SOAP sections. What belongs in Subjective vs Objective. When to write "Not documented" vs omit a section. These are clinical conventions the model needs examples of.

3. **Hallucination resistance.** The model must learn to stop at what the transcript says. Training examples should include sparse transcripts where many sections are "Not documented" — teaching the model restraint is as important as teaching it what to write.

### Training data format

All fine-tuning training examples should follow this format:

```
User: [system prompt + template + transcript]
Assistant:
# Subjective
## Chief Complaint
Patient presents with...

## History of Present Illness
- Onset: 3 days ago
- {{condition:type 2 diabetes}} — well-controlled on {{drug:metformin}} 500mg

# Objective
## Physical Examination
### Vital Signs
BP: 130/85
HR: 78

# Assessment
1. {{condition:hypertension}} — uncontrolled on current regimen

# Plan
1. Increase {{drug:lisinopril}} to 20mg daily
2. Follow-up in 4 weeks
```

This format is what the model naturally wants to produce (markdown), what the app parser can handle (headings + entities), and what the eval rubric scores against (template adherence + entity marking). All three are now aligned.

### Expected fine-tuning outcomes

| Dimension | Base MedGemma 4B | Expected after fine-tuning | Why |
|-----------|-----------------|---------------------------|-----|
| Entity Marking | 3% | 60-80% | Novel syntax learned from examples |
| Instruction Following | 24% | 70-85% | No longer fighting format; focus on clinical rules |
| Template Adherence | 47% | 75-90% | Markdown headings align with pre-training |
| Completeness | 45% | 55-70% | Better instruction following → less content missed |
| Hallucination | 43% | 50-65% | Training examples emphasize restraint |
| Overall | 41% | 65-80% | Compound improvement across dimensions |

These are rough estimates. The key insight is that removing the format tax lets the same number of training examples and LoRA parameters go further on the dimensions that actually matter.

---

## Remaining Work

1. **Re-run evals** with updated prompts and templates
2. **Generate fine-tuning training data** using the new markdown format + entity markers
3. **Fine-tune MedGemma 4B** with LoRA via MLX
4. **Migrate `server/utils/editor/lexical.ts`** to match the app's markdown + entity parsing (lower priority)
