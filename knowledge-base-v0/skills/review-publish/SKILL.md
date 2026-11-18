---
name: review-publish
description: The gate between a scientist's local copy of the AstaUI knowledge base and the shared one. Checks that new or changed builds and cards carry no private data, that consent allows sharing, and that every card is sound, before a pull request merges. Use when reviewing a contribution to the knowledge base, before pushing or merging one, or when asked whether a build is safe to share.
---

# Review and publish

A build leaves a scientist's machine only after this review. It is the extractor's strip step, run again by a second reader, plus the checks the repository's CI runs.

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 <this skill's folder>/../../astaui_cli.py`.

## 1. Find what is new

In the clone, `git diff --name-only origin/main...HEAD -- knowledge-base-v0/kb` lists the builds and cards the branch adds or changes. Review each build id in it.

## 2. Check each build

- `astaui check`: every build, card, query and judged pair is well formed, every card matches its build's code, and nothing that must go (keys, emails) is left. It must pass.
- `astaui lint <id>`: read every line it lists, not only the ones marked MUST GO.
- Read the prompts in `kb/builds/<id>/prompts.jsonl` and skim the code's embedded data. Look for what a program cannot: names of real people, patient or participant details, unpublished results, a lab's private paths or hostnames, data that is not synthetic.
- Read `build.json`: `author.name` is a pseudonym unless the person asked to be named; `provenance.consent` allows where this is going (`team` for the project's repository, `public` for anything published); `provenance.kind` is right.
- Read the card (`astaui card show <id>`): it describes structure, not content, and its summary would make sense to someone in another field.

## 3. Decide

If everything holds, say so in the pull request and merge it. If something must change, say exactly what and where (file and line), and leave it to the contributor, or fix it with them. Never merge a build whose consent does not cover the audience, whatever else is right with it.

After merging, the CI job rebuilds the index, runs the evaluation and publishes the map as a build artifact, so everyone sees the space with the new build in it.
