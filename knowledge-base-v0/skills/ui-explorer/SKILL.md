---
name: ui-explorer
description: Browse the AstaUI knowledge base of scientists' interfaces by hand. Draws the embedding space as a map, places requests on it, shows any build's card, prompts and code, compares representations, and exports the vectors for other tools. Use when someone wants to see, explore, inspect, visualise or pull the knowledge base or its embedding space, asks what kinds of interfaces exist for some kind of work, or wants to know how the cards cluster.
---

# UI explorer

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 <this skill's folder>/../../astaui_cli.py`. `astaui status` says what is in the knowledge base.

## The console

`astaui console` opens a local page with everything below in one place: health, every build with its card and slices, a search playground, workflow families and comparisons, the evaluation, what was searched and whether it helped, and the ontology. Offer it when someone wants to see how the knowledge base is working; the commands below are for answering one question at a time.

## The map

```sh
astaui map --open
astaui map --query "screen abstracts for a systematic review" --query "QC a plate of growth curves" --open
```

It writes one HTML file (`kb/.out/map.html` unless `--out` says otherwise) and opens it. Each build is a point, placed so that similar builds sit together. The buttons at the top switch what "similar" means:

| Button | Places builds by |
|---|---|
| Card | The whole description: summary, workflow and all five facets |
| Workflow | The general workflow alone: its name and steps in words any science could use |
| Structure | The ontology's words for task, data, stage and mechanism, with nothing from the field, so builds from different sciences that work alike sit together |
| Prompts and code | The raw text, before any describing |
| Data shape, Task, Mechanism | One facet alone |
| Prompts | The prompts alone |

Comparing Card with Prompts and code is the Workspace's first question: does describing first put the same jobs together better than the raw text does? Colour by field and then by task: if the field colours scatter while the task colours cluster, the card is finding structure across sciences. Lines join the pairs judged by eye (solid for the same job, dashed for related). A request passed with `--query` lands among its nearest builds. Clicking a point shows its card, its parts with their line ranges, its prompts and its nearest neighbours under the current placement.

`--method umap` uses UMAP instead of PCA when `umap-learn` and `numpy` are installed; with a few dozen builds PCA is usually as readable and is stable from run to run.

## Looking at one build

- `astaui show <id>`: its prompts, files and card.
- `astaui show <id> --part <part-id>` or `astaui slice <id> <part-id>`: one view or component's code as a slice, with what it uses from elsewhere in the build.
- `astaui symbols <id>`: every function, element and style rule in the build, with its lines.
- `astaui card show <id> --json`: the card as stored.

## Workflows

```sh
astaui workflows
astaui compare plate-reader-qc sky-frame-triage
```

`workflows` groups the builds into families that share a workflow, says which steps the family shares, and for each member which steps are its own and what is particular to it. `compare` lines up any two builds' workflows step by step: the same steps with how each does them, the steps only one has, each one's distinctive needs, and which of one's needs the other already meets. Colour the map by workflow family to see the families in the space.

## Answering questions about the space

- "What exists for X?": `astaui search "X" --k 10 --no-code`, or filter exactly: `--where shape=image collection`, `--where verb=triage`, `--where pattern=review queue`.
- "Which words do the cards use that the ontology lacks?": `astaui ontology proposals`.
- "How good is it?": `astaui eval` (see the README's evaluation section).

## Pulling the vectors out

- `astaui export projector --channel card`: two TSV files for projector.tensorflow.org (Load, pick both files). Any channel works: `card`, `structure`, `raw`, `data`, `task`, `mechanism`, `stage`, `summary`, `prompt`, `field`.
- `astaui export jsonl`: one line per vector with its card's metadata, for a notebook.
- `astaui export sql --out kb.sql`: a load script for Postgres with pgvector (Cloud SQL, AlloyDB, or `docker run pgvector/pgvector`).

The vectors are a cache rebuilt from the cards (`astaui index`), so every export reflects the cards as they are now. Vectors from different embedders cannot be compared; each export says which embedder made it.
