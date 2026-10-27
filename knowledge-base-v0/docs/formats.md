# File formats

Everything in the knowledge base is a plain file in git. The vectors are not: they are a cache rebuilt from these files (`astaui index`), so they never need merging.

```
kb/
  kb.json            settings: the default embedder, the search weights
  ontology.json      the facets and their vocabularies, with a log of changes
  builds/<id>/       what a scientist made: prompts, code, a screenshot
  cards/<id>.json    what the build is, in the ontology's terms
  eval/queries.jsonl requests with the builds you would want back
  eval/pairs.jsonl   pairs of builds you judged by eye
```

An id is lowercase letters, digits and hyphens, for example `transcript-coder`.

## A build: `kb/builds/<id>/`

| File | What it holds |
|---|---|
| `build.json` | Who made it, where it came from, what may be shared |
| `prompts.jsonl` | The prompts, one turn per line, in order |
| `code/` | The interface's own source files, as they were |
| `screenshot.png` | Optional: the running interface as it first opens (`.webp` and `.jpg` work too). The console shows it beside the build in its lists and inspector |

`build.json`:

```json
{
  "id": "transcript-coder",
  "title": "Interview transcript coder",
  "author": { "name": "P07", "role": "PhD student", "field": "HCI" },
  "created": "2026-10-23",
  "sources": ["prompt log"],
  "provenance": {
    "kind": "seed",
    "origin": "Written for the prototype; not a real participant's work.",
    "forked_from": null,
    "consent": "synthetic"
  },
  "entry": "code/index.html",
  "notes": "Anything a reader should know that the code and prompts do not say."
}
```

- `sources` uses the Workspace's list: `prompt log`, `repo`, `skill file`, `Claude artifact`, `Marble app`.
- `provenance.kind` is one of `seed` (written for the prototype), `study` (from a formative-study participant), `contributed` (filed by a scientist through `ui-to-workflow`), `paper` (a figure from a paper, usually with no prompts).
- `source` (optional) says where the full code lives when it came from a repository: `{"repo": "git@github.com:lab/app.git", "commit": "…", "path": "ui/"}`. A build with a source can be slimmed (`astaui slim`) to the files its card points at; `slimmed` then lists what was dropped, with sizes and fingerprints.
- `provenance.consent` says what the person agreed to: `synthetic`, `team` (people on this project may see it), `public`.
- `author.name` is a pseudonym (`P07`) unless the person asked to be named.

`prompts.jsonl`, one JSON object per line:

```json
{"turn": 1, "text": "I have 14 interview transcripts and a codebook ...", "at": "2026-10-02"}
{"turn": 2, "text": "the highlight disappears when I click another code, keep it", "at": "2026-10-02"}
```

`at` is optional. Keep the words as the person typed them, typos included. Leave out pasted logs and tool output.

## A card: `kb/cards/<id>.json`

One card file per build. It holds the card for the whole app and a card for each view and component inside it, each linked to its parent. The extractor writes it (`astaui extract`), and `astaui card put` checks it before saving.

```json
{
  "schema": "astaui.card/1",
  "id": "transcript-coder",
  "ontology": "1",
  "made": { "by": "agent", "model": "claude-opus-5", "prompt": "extract/1", "at": "2026-10-23T18:00:00Z" },
  "app": {
    "title": "Interview transcript coder",
    "summary": "A researcher reads interview transcripts one at a time, selects passages and applies codes from a shared codebook, then sees how often each code was used across participants.",
    "task":      { "text": "Apply qualitative codes to passages of interview text", "verbs": ["annotate", "summarize"] },
    "data":      { "text": "Transcripts split into speaker turns, and a codebook of named codes with definitions", "item": "a passage of a transcript", "shapes": ["text corpus", "codebook"] },
    "stage":     { "text": "First-pass coding of collected interviews", "terms": ["annotate"] },
    "mechanism": { "text": "Select text, then click a code in the sidebar; coded passages are tinted and counted per code", "views": ["document reader", "sidebar list"], "interactions": ["select text span", "apply label"], "patterns": ["category palette"] },
    "field":     { "text": "Qualitative interview study in HCI", "disciplines": ["hci"], "terms": ["thematic analysis"] },
    "workflow": {
      "name": "Apply categories from a scheme to stretches of text",
      "steps": [
        { "step": "step through items one at a time", "here": "one participant's transcript at a time, split into speaker turns", "parts": ["participant-tabs"] },
        { "step": "select a stretch and label it with a category", "here": "select a passage inside a turn and click a code in the sidebar", "parts": ["codebook-sidebar"] },
        { "step": "track progress toward a target or a total", "here": "segments per code and participants per code beside each code", "parts": ["codebook-sidebar"] },
        { "step": "export the result", "here": "a CSV of source, turn, speaker, code and quote", "parts": ["segment-export"] }
      ],
      "distinctive": [
        "A passage can carry two codes, shown as overlapping tints",
        "Each code's definition stays in view while coding"
      ]
    }
  },
  "parts": [
    {
      "id": "codebook-sidebar",
      "level": "view",
      "parent": null,
      "title": "Codebook sidebar",
      "summary": "Lists the codes with their definitions and counts; clicking one applies it to the selected passage.",
      "views": ["sidebar list"],
      "interactions": ["apply label"],
      "patterns": ["category palette"],
      "spans": [
        { "file": "code/index.html", "start": 93, "end": 101, "role": "markup", "symbol": "#code-list", "anchor": "3f1c09a2b7de", "first": "<div id=\"code-list\">" },
        { "file": "code/index.html", "start": 58, "end": 63, "role": "style", "symbol": ".code-head" },
        { "file": "code/index.html", "start": 338, "end": 380, "role": "logic", "symbol": "renderCodebook" }
      ]
    }
  ]
}
```

The five facets come from the Architecture board:

| Facet | Says | Weighted in search |
|---|---|---|
| `task` | What the interface is for | high |
| `data` | The shape of the data and what one item is | high |
| `stage` | Where in the work it is used | medium |
| `mechanism` | Views, interactions and patterns, and how they work together | medium |
| `field` | The science, in the builder's words | low: kept so a match can cross fields |

`summary` is the description of the workflow in plain sentences. It names no participant, no data values and no findings.

`workflow` is what the build is filed under. `name` is the general workflow, with no field words. Each step is said twice: `step` in general words any science could use (one of the ontology's `workflow.moves` when one fits, so steps that are the same move read the same), and `here` as this build does it, with the `parts` that do it. `distinctive` lists what is particular to this case, that another build with the same workflow would not have. Search matches on the general workflow; comparing the steps' `here` and the `distinctive` lists says how two cases of the same workflow differ.

Terms in `verbs`, `shapes`, `terms`, `views`, `interactions` and `patterns` come from `ontology.json`. A term the ontology does not have yet is kept, and `astaui ontology proposals` lists it, so the vocabulary grows from what the cards needed.

A part's `level` is `view` (a region of the screen) or `component` (a piece inside a view). `spans` are the code that makes it, across files: `role` is `markup`, `style`, `logic`, `data` or `other`; lines are 1-based and inclusive. A writer may give a `symbol` from `astaui symbols <id>` instead of lines, and `card put` fills the lines in. `anchor` and `first` are filled in too: a fingerprint of the span's code and its first line, so a later check can tell whether the code moved (and where to) or changed. Cards written before spans have a single `code` range, read as one `logic` span.

## A query card

A request for an interface becomes a card too, with the same facets, any of which may be missing:

```json
{
  "request": "I need to code focus group transcripts with my labmate and see where we disagree",
  "task":  { "text": "Code transcripts with a second coder and compare", "verbs": ["annotate", "reconcile"] },
  "data":  { "text": "Focus group transcripts and a shared codebook", "shapes": ["text corpus", "codebook"] },
  "stage": { "terms": ["annotate", "compare"] },
  "field": { "text": "education research" },
  "workflow": {
    "name": "Apply categories from a scheme to stretches of text, with a second coder",
    "steps": [
      { "step": "select a stretch and label it with a category", "here": "each of us codes the transcripts separately" },
      { "step": "find where people disagree and resolve it", "here": "see where we disagree and settle it together" }
    ],
    "distinctive": ["two coders work on the same transcripts"]
  }
}
```

## Evaluation files

`kb/eval/queries.jsonl`: a request, optionally its query card, and the builds you would want back.

```json
{"id": "q01", "request": "...", "card": {"task": {...}}, "wanted": ["transcript-coder"], "far": ["sequence-annotator"], "note": "..."}
```

`far` lists builds from another field with the same structure, which the search should offer as the far match.

`kb/eval/pairs.jsonl`: two builds and what you judged by eye, before seeing any scores.

```json
{"a": "plate-reader-qc", "b": "sky-frame-triage", "judgment": "related", "note": "Both triage a grid of items, different data."}
```

`judgment` is `same` (the same job), `related` or `different`. `by` says who judged and when they did: a pair judged in the console is written with `"by": "judged in the console, with the similarity scores in view"` and a `date`, because a judgment made while looking at the scores is not the blind judgment the evaluation assumes. Weigh those pairs apart, or judge them again before looking.

## Changes made by hand

`astaui manage` changes the ontology's words, the words on a card, and the judged pairs. A change to the ontology raises its version (`3` → `3.1` → `3.2`) and adds one entry to its `changes`:

```json
{"version": "3.1", "date": "2026-10-24", "change": "Renamed the data shape “table” to “tabular data”; “table” stays on as another word for it.", "because": "Clearer to scientists.", "by": "the console"}
```

Then every card is checked again under the new version, so the cards say the same thing in the new words. A renamed or merged word becomes another word (`also`) for the one that replaced it, so nothing that used it stops finding it.

| Change | Fixed when queued | Written by the person |
|---|---|---|
| `add-term` | facet, list, term | means, because |
| `rename-term` | facet, list, term | to, because |
| `merge-term` | facet, list, term (a word in the list, or one a card proposed) | into, because |
| `add-word` | facet, list, term | word, because |
| `set-meaning` | facet, list, term | means, because |
| `retire-term` | facet, list, term (only when no card uses it) | because |
| `tag`, `untag` | build, facet, list, term | |
| `judge` | a, b, judgment | note |
| `unjudge` | a, b | |
| `set-weight` | facet (one of the five, `summary` or `workflow`) | weight, because |

In the console page each waiting change is one row of the list `kb-queue`: an `li` with `data-action` and the fixed arguments as `data-*` attributes, each written argument in an element with `data-arg="<name>"`, an element of class `problem` where Apply says what is wrong, and `data-dropped` when the person dropped it. `astaui manage apply --doc <page>` reads those rows, makes every change or none, and takes the rows it made out of the list.
