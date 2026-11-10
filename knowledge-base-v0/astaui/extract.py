"""The card extractor: reads a build and writes its card.

There are two ways to run it, and both use the same instructions:

- **agent**: ``astaui extract <id>`` prints the instructions and the build. The
  coding agent the scientist is already using reads them, writes the card as JSON,
  and files it with ``astaui card put``. No API key needed.
- **api**: ``astaui extract <id> --api`` sends the same instructions to Claude
  (the Claude API, or Claude on Vertex AI) with the card's JSON Schema as the
  required output format, then files the result through the same checks.

A request for an interface is described the same way (``astaui describe``), so a
query and a card are compared facet by facet.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .kb import Build, KBError
from .ontology import FACETS, LISTS, PART_LISTS, Ontology

EXTRACT_VERSION = "extract/4"
QUERY_VERSION = "describe/2"
MAX_CODE_LINES = 2500
MAX_FILE_LINES = 1600

FACET_GUIDE = """\
- summary: the description of the workflow. Two to four plain sentences saying what a person does with the interface, in order, and what they get out of it. Name no participant, no data values and no findings: describe the structure of the work, not its content.
- task: what the interface is for. `text` is one sentence; `verbs` are the ontology's task verbs that apply, most important first.
- data: the shape of the data. `text` says what the data is in general terms; `item` says what one item is ("a passage of an interview transcript", "a well on a 96-well plate"); `shapes` are the ontology's data shapes, every one that is present.
- stage: where in the work it is used. `text` is one short phrase; `terms` are the ontology's stage words.
- mechanism: how it works. `text` says how the views and interactions work together in one or two sentences; `views`, `interactions` and `patterns` are the ontology's words for what is there.
- field: the science. `text` is a short phrase in the builder's words ("qualitative interview study in HCI"); `disciplines` is the broad discipline from the ontology's list (usually one); `terms` are one to three narrower lowercase words a person would file it under ("thematic analysis", "interview study")."""

WORKFLOW_GUIDE = """\
- workflow: the job the interface serves, as a sequence. This is what the build is filed under, so other builds with the same workflow find it, and so the ways it differs from them show.
  - `name`: the general workflow in a few words, with no field words ("triage a collection one item at a time", "apply codes from a codebook to passages of text").
  - `steps`: three to seven steps in the order a person does them. Each has `step`, the general move in words any science could use ("decide keep or drop for each item, with a reason"); `here`, how this build does it, specifically ("k keeps a frame; r waits for a numbered reason: trail, cloud, blur, other"); and `parts`, the ids of the parts that do it.
  - `distinctive`: two to five things particular to this case that another build with the same workflow would not have: a constraint, an extra quantity, a rule of the field, a special view ("total exposure is tracked against a target, so the person knows when enough frames are kept")."""

QUERY_WORKFLOW_GUIDE = """- workflow: the job they want done, as a sequence. `name` is the general workflow in a few words with no field words; `steps` are the moves they describe, in order, each with `step` (the general move, in words any science could use) and `here` (how they want it done, in their terms); `distinctive` lists what is particular to their case: constraints, quantities, rules of their field, things they said they need."""

RULES = """\
- Use the ontology's words wherever one fits. Add a new word only when none does; it will be proposed as an addition to the ontology, so make it general ("sequence track", not "my plasmid strip").
- Describe what the code actually does. When the prompts asked for something the code does not do, leave it out.
- Keep it general enough that someone in another field could recognise the same structure: "items in a grid, triaged one at a time with the keyboard" rather than only "telescope frames".
- Leave out names of people, institutions, email addresses, data values and results."""


def _numbered(text: str, limit: int) -> Tuple[str, int, bool]:
    lines = text.splitlines()
    shown = lines[:limit]
    width = len(str(len(lines)))
    body = "\n".join(f"{str(i).rjust(width)}| {line}" for i, line in enumerate(shown, 1))
    return body, len(lines), len(lines) > limit


def build_material(build: Build, max_lines: int = MAX_CODE_LINES, code_only: bool = True) -> str:
    """The build as the extractor reads it: metadata, every prompt, the code with
    line numbers (entry file first). By default (``code_only``) the prompts and
    the filer's notes are left out, so the card says only what the code shows and
    a build found in a repository, with no conversation behind it, is described
    the same way as one filed with its prompts."""
    keys = ("id", "title", "sources", "entry") if code_only else ("id", "title", "author", "sources", "entry", "notes")
    meta = {k: build.meta.get(k) for k in keys if build.meta.get(k)}
    out = ["### build.json", json.dumps(meta, indent=2, ensure_ascii=False), ""]
    if not code_only:
        out.append("### Prompts, in order")
        if build.prompts:
            for i, t in enumerate(build.prompts, 1):
                out.append(f"[{i}] {t.get('text', '').strip()}")
        else:
            out.append("(none: this build came without prompts)")
        out.append("")
    files = build.code_files()
    entry = build.meta.get("entry")
    files.sort(key=lambda p: (0 if str(p.relative_to(build.path)) == entry else 1, str(p)))
    from .symbols import index_build, outline

    symbols = index_build(build)
    if symbols:
        out.append("### Symbols: every function, element with an id and style rule, by file, with its lines")
        for f in sorted({s.file for s in symbols}, key=lambda f: (f != entry, f)):
            out.append(f)
            out.extend(outline(symbols, f))
        out.append("")
    used = 0
    skipped: List[str] = []
    for p in files:
        rel = str(p.relative_to(build.path))
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.append(f"{rel} (binary)")
            continue
        room = max_lines - used
        if room <= 50:
            skipped.append(rel)
            continue
        body, total, cut = _numbered(text, min(room, MAX_FILE_LINES))
        used += min(total, room, MAX_FILE_LINES)
        out.append(f"### {rel} ({total} lines{', first ' + str(min(room, MAX_FILE_LINES)) + ' shown' if cut else ''})")
        out.append(body)
        out.append("")
    if skipped:
        out.append("### Not shown: " + ", ".join(skipped))
    if build.screenshot():
        out.append(f"### Screenshot: {build.screenshot().relative_to(build.path)} (open it if you can see images)")
    return "\n".join(out)


def card_schema() -> Dict[str, Any]:
    """The card's JSON Schema, in the subset structured outputs accept."""
    def words(desc: str) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "string"}, "description": desc}

    def facet(name: str) -> Dict[str, Any]:
        props: Dict[str, Any] = {"text": {"type": "string"}}
        if name == "data":
            props["item"] = {"type": "string"}
        for lst in LISTS[name]:
            props[lst] = words(f"Ontology words for {name}.{lst}")
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

    part = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "short-hyphenated-id"},
            "level": {"type": "string", "enum": ["view", "component"]},
            "parent": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "id of the containing part, or null"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            **{lst: words(f"Ontology words for mechanism.{lst}") for lst in PART_LISTS},
            "spans": {
                "type": "array",
                "description": "the code that makes this part: its markup, style rules, script and data, across files",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "symbol": {"type": "string", "description": "a name from the symbol list, or empty"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                        "role": {"type": "string", "enum": ["markup", "style", "logic", "data", "other"]},
                    },
                    "required": ["file", "symbol", "start", "end", "role"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["id", "level", "parent", "title", "summary", *PART_LISTS, "spans"],
        "additionalProperties": False,
    }
    app_props: Dict[str, Any] = {"title": {"type": "string"}, "summary": {"type": "string"}}
    for f in FACETS:
        app_props[f] = facet(f)
    app_props["workflow"] = workflow_schema(with_parts=True)
    return {
        "type": "object",
        "properties": {
            "app": {"type": "object", "properties": app_props, "required": list(app_props), "additionalProperties": False},
            "parts": {"type": "array", "items": part},
        },
        "required": ["app", "parts"],
        "additionalProperties": False,
    }


def workflow_schema(with_parts: bool) -> Dict[str, Any]:
    step: Dict[str, Any] = {"step": {"type": "string", "description": "the general move, in words any science could use"},
                            "here": {"type": "string", "description": "how it is done in this case"}}
    if with_parts:
        step["parts"] = {"type": "array", "items": {"type": "string"}, "description": "ids of the parts that do it"}
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "the general workflow, with no field words"},
            "steps": {"type": "array", "items": {"type": "object", "properties": step, "required": list(step), "additionalProperties": False}},
            "distinctive": {"type": "array", "items": {"type": "string"}, "description": "what is particular to this case"},
        },
        "required": ["name", "steps", "distinctive"],
        "additionalProperties": False,
    }


def query_schema() -> Dict[str, Any]:
    full = card_schema()["properties"]["app"]
    props = {"request": {"type": "string"}, "summary": {"type": "string"}}
    for f in FACETS:
        props[f] = full["properties"][f]
    props["workflow"] = workflow_schema(with_parts=False)
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


CODE_ONLY_NOTE = """
## Reading the code for what nobody said

This build is read from its code alone: there are no prompts and no notes from the person who made it. Everything on the card has to come from what the code shows: its labels, headings, button text and placeholders, the names of its functions, fields and files, its sample or seed data, its comments, and a README if there is one. Three facets are easy to get wrong this way. Work them out in this order before you write the card.

1. **The workflow.** Walk the interface as a person would use it. Start where the data comes in (a file input, a paste box, seeded data) and end where the result leaves (an export, a copy button, a saved file, a final status). On the way, go through every control a person touches, in the order the code makes them available: what is disabled until something else is done, what a view needs before it can draw. Every control that does part of the job is a step, including the small ones: a search that finds every occurrence, a slider that narrows to one period, a total by category, a click in one view that finds the item in another. Merge two controls only when they make the same move. Then name the workflow by what the person ends up with, because that is the job: the file it exports, the number it computes, the text it drafts, the decision it records. "Estimate each sample's concentration from a standard curve and flag the ones out of range" names the job; "plot absorbance against standards" names only the screen.

2. **The stage.** Read it from what must already exist before the interface is any use, and from what it hands on. The input says what has been done: raw instrument output means it comes early (explore, clean); items someone already labelled mean it comes after annotating (compare, confirm). The output says what comes next: a cleaned table goes to analysis; a written judgement goes to review or report. Write `text` as one short phrase that names the work and where it sits, the way the person would say it ("cleaning sensor logs after a deployment, before modelling"), with no data values. Put first the term for what the person spends most of their time doing, and add another only when the interface covers that stage as a whole, not because one button touches it: an export button is not "report", and a confirm dialog is not "confirm". Whether the scheme can change during the work says something too: a label set the person can edit as they go means exploratory, inductive work; a fixed one means applying a scheme already agreed.

3. **The field.** The code can show three things that are easy to mix up. The sample's topic is what this one study is about (coral bleaching, voter turnout). The method is what the interface computes and how it treats the data (curves fitted per sample, passages coded against a scheme, agreement measured between raters). The discipline is the community whose method that is. `field` is the method and the discipline, never the sample's topic, because the next person with the same method studies a different topic. Write `text` as the method in the discipline ("dose-response assays in pharmacology"), and put the discipline's usual name among the `terms` ("pharmacology"). Read the method from the domain words in labels and function names, the units, the statistics computed, the file formats and the libraries, and name it in that field's own terms ("dose-response", "peak picking", "occupancy modelling"). Add a narrower term (a subfield, a venue, a community) only when the code names it, in a heading, a label or a README.

When the code does not show a facet, say the least it supports rather than guessing, and leave the words empty if nothing supports any.
"""


def extract_prompt(ont: Ontology, build: Build, out_path: Optional[str] = None, code_only: bool = True) -> str:
    example = {
        "app": {
            "title": "…",
            "summary": "…",
            "task": {"text": "…", "verbs": ["…"]},
            "data": {"text": "…", "item": "…", "shapes": ["…"]},
            "stage": {"text": "…", "terms": ["…"]},
            "mechanism": {"text": "…", "views": ["…"], "interactions": ["…"], "patterns": ["…"]},
            "field": {"text": "…", "disciplines": ["…"], "terms": ["…"]},
            "workflow": {"name": "…", "steps": [{"step": "…", "here": "…", "parts": ["…"]}], "distinctive": ["…"]},
        },
        "parts": [
            {"id": "…", "level": "view", "parent": None, "title": "…", "summary": "…",
             "views": ["…"], "interactions": ["…"], "patterns": ["…"],
             "spans": [{"file": "code/index.html", "symbol": "#grid", "role": "markup"},
                       {"file": "code/index.html", "symbol": ".tile", "role": "style"},
                       {"file": "code/index.html", "symbol": "buildGrid", "role": "logic"},
                       {"file": "code/index.html", "start": 412, "end": 420, "role": "logic"}]},
        ],
    }
    put = f"astaui card put {build.id} {out_path or '<file>'}" + ("" if code_only else " --from prompts")
    finish = f"Write the JSON to {out_path or 'a file'} and run `{put}`. "
    return f"""\
# Write the card for build `{build.id}`

You are describing an interface a scientist built with a coding agent, so that other scientists can find it when they need something with the same structure. Read the build below ({'its code' if code_only else 'its prompts and its code'}) and write its card as JSON.
{CODE_ONLY_NOTE if code_only else ''}
## The card

{FACET_GUIDE}
{WORKFLOW_GUIDE}

Then list the parts: the views (regions of the screen) and the components inside them (a palette, a chart, a form, a queue control). Three to eight parts, each with:
- `id` (short-hyphenated), `level` (`view` or `component`), `parent` (the id of the view it sits in, or null), `title`, a one-sentence `summary` of what it does for the person,
- `views`, `interactions`, `patterns` from the mechanism vocabulary,
- `spans`: the code that makes the part, so someone can lift this one feature without reading the whole build. Name every piece it needs, wherever it is: its markup (`role: markup`), its style rules (`style`), its script (`logic`) and any data it is built from (`data`), across files. Point at a piece by `symbol`, using a name from the symbol list (a function, an `#id` element, a CSS selector), and the lines are filled in for you; or give `start` and `end` lines for code the list does not name, such as part of a long function or an event handler. Helpers the part's own functions call are found by following the code, so name the part's own code, not everything it touches.

## Rules

{RULES}

## The ontology's words (ontology version {ont.version})

{ont.vocabulary_text()}
## The shape of the answer

```json
{json.dumps(example, indent=2)}
```

{finish}If it reports problems, fix them and put it again.

## The build

{build_material(build, code_only=code_only)}
"""


def describe_prompt(ont: Ontology, request: str, context: str = "") -> str:
    ctx = f"\n## What else is known about their situation\n\n{context.strip()}\n" if context.strip() else ""
    return f"""\
# Describe a request for an interface

A scientist asked for an interface. Describe what they asked for as a query card, in the same facets and words the knowledge base's cards use, so it can be matched facet by facet. Fill a facet only from what the request says or clearly implies; leave its words empty if you would be guessing. Write `summary` as the workflow they want: what they will do with it, in order.

{FACET_GUIDE}
{QUERY_WORKFLOW_GUIDE}

## Rules

{RULES}

## The ontology's words (ontology version {ont.version})

{ont.vocabulary_text(include_means=False)}
## The request

{request.strip()}
{ctx}
Answer with the JSON only, shaped like:

```json
{{"request": "…", "summary": "…", "task": {{"text": "…", "verbs": []}}, "data": {{"text": "…", "item": "…", "shapes": []}}, "stage": {{"text": "…", "terms": []}}, "mechanism": {{"text": "…", "views": [], "interactions": [], "patterns": []}}, "field": {{"text": "…", "disciplines": [], "terms": []}}, "workflow": {{"name": "…", "steps": [{{"step": "…", "here": "…"}}], "distinctive": []}}}}
```
"""


# -- through the API -------------------------------------------------------------------

def _client(provider: str):
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise KBError("--api needs the Anthropic SDK: pip install anthropic (or 'anthropic[vertex]' for Vertex AI)") from None
    if provider == "vertex":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
        region = os.environ.get("CLOUD_ML_REGION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        if not project:
            raise KBError("Claude on Vertex AI needs GOOGLE_CLOUD_PROJECT (and gcloud application-default credentials)")
        return anthropic, anthropic.AnthropicVertex(project_id=project, region=region)
    return anthropic, anthropic.Anthropic()


def call_claude(prompt: str, schema: Dict[str, Any], provider: str = "anthropic", model: str = "claude-opus-5") -> Dict[str, Any]:
    """One request to Claude with the answer constrained to ``schema``."""
    anthropic, client = _client(provider)
    params: Dict[str, Any] = {
        "model": model,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    try:
        if provider == "anthropic":
            # If a safety classifier declines the request, let the server retry on a fallback model.
            resp = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        else:
            resp = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise KBError("Claude refused the credentials: set ANTHROPIC_API_KEY, or run `ant auth login`") from None
    except anthropic.NotFoundError:
        raise KBError(f"Model {model!r} was not found on {provider}") from None
    except anthropic.RateLimitError:
        raise KBError("Rate limited by the API; wait a minute and run it again") from None
    except anthropic.APIStatusError as e:
        raise KBError(f"The API answered {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise KBError("Could not reach the API; check the network") from None
    if resp.stop_reason == "refusal":
        raise KBError("Claude declined to describe this build")
    if resp.stop_reason == "max_tokens":
        raise KBError("The answer was cut off at max_tokens; the build may be too large to describe in one pass")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise KBError("The API's answer was not valid JSON") from None
