---
name: workflow-to-ui
description: Build an interface for a scientist's work, informed by what other scientists built and how they work. Use when a scientist asks for a UI, tool, dashboard, viewer, workbench or app for their research (coding transcripts, reviewing papers, triaging images, checking plate data, exploring a dataset, anything for science), or asks how others do this kind of work. Infer their workflow as a tree of phases and tasks, with where it is slow, blind or fragile, and ask about the unsure parts; find builds in the AstaUI knowledge base whose workflow matches, and builds that work on the same data or goal differently; offer the two to four workflow shifts that would let them find or check something they cannot now, and let them choose. Build the interface in new code for the workflow they chose, with a Workflow view, a credit for each borrowed feature and shift, and the shifts they did not take as other ways to work. Offer a walkthrough, and add it when they ask.
---

# Workflow to UI

A scientist has asked you to build an interface. Other scientists have built interfaces for work with the same workflow, and the AstaUI knowledge base holds them: their prompts, their code, a screenshot, the features an agent found by using each one, and a card that says what each is for. Use them the way a designer uses references. Match the workflow, look at how those interfaces serve it, choose the features worth having, and then build this scientist's interface yourself, as well as you can, in new code.

The builds are references, not starting points. Their code was written for someone else's data, often quickly, by an agent that knew less about this scientist than you do, and copying it carries over its shortcuts and its assumptions. What is worth taking is the design: which views sit side by side, what a key does, how a correction is recorded, what a person needs to see before they decide.

The knowledge base also holds how those scientists work. Some of them, on the same kind of data or toward the same kind of result, arranged the work differently: they check something earlier, keep more in each record, split one pass into two, compare against a baseline, loop back when a result surprises them. Matching the scientist's workflow as it is finds interfaces that do what they already do, which can only give them back their own way of working, better drawn. So before you build, look for those differences on purpose, and offer the few that would let this scientist find or check something they cannot now. They choose. A difference is worth offering only when it serves their goal; never offer a change because it is new or because another field does it, and never make one for them.

## Running the tool

The knowledge base's command is `astaui`. Use it if it is on the PATH (`pip install -e` puts it there). Otherwise run `python3 <this skill's folder>/../../astaui_cli.py`; this skill's folder is the base directory you were given when the skill loaded. Below, `astaui` means whichever works. Check it once with `astaui status`; its first line names the knowledge base folder, called `<kb>` below.

It needs Python 3.9 or later and nothing else. Nothing in these steps sends the scientist's data anywhere: describing the request is your own work, and the search runs on this machine.

The commands you will use most:

| Command | What it gives you |
|---|---|
| `astaui search "<words>" --card <file> --no-code` | Builds whose card matches, each with its workflow lined up against yours: same steps, its own steps, your own steps, what is particular to it |
| `astaui workflows` | Every build grouped into workflow families, with each family's shared steps and each build's own steps and particular rules |
| `astaui compare <build> <build>` | Two builds' workflows lined up: shared steps, how each does them, what is each one's own |
| `astaui show <build>` | One build: its prompts, files and card |

## 1. Understand the request

Read what they asked for. If their data is in the working folder, look at it the way a person would before building: file names, a header row, a few lines, the size. Note what one item is (a transcript passage, a well, a frame, a record), what they will do to it, and what they want to come out at the end: a finding, a decision, a cleaned data set, a figure, a paper. Do not ask questions you can answer by looking, and do not ask anything yet: what looking leaves unclear, you will ask about in step 2.

## 2. Infer their workflow tree, and ask about what is unsure

Before searching, write down the work as you understand it, as a tree in the knowledge base's own shape: one `goal` (what they want to come out of the work), the `phase`s it moves through in order, and under each phase the `task`s a person does there. Give each node a `general` line in words any field would use and a `specific` line in theirs, as the builds' `tree.json` files do. Include the parts an interface for this work would need even when they did not mention them (how items come in, how a decision is recorded, what leaves at the end), since those are the parts most often guessed wrong.

Then score each node for how sure you are of it, from 0 to 1, with a few words on why:

| Score | When |
|---|---|
| 0.9 to 1 | They said it in so many words, or their data shows it |
| 0.7 to 0.9 | It follows clearly from what they said or from their data |
| Below 0.7 | You are guessing: they did not say it, or what they said could go two ways that would make different interfaces |

For the work as a whole, also write:

- `question`: what they are trying to find out or decide, in one line. A workflow serves a question, and a better workflow is better for that question.
- `weak_points`: where the work, as they describe it, is slow (a step done by hand item after item), blind (something they cannot see or check: an error that would pass unnoticed, a bias, a pattern across items that one-at-a-time work hides), or fragile (a decision that cannot be traced or redone, a result that depends on one person's judgment). Name each with the phase or task it sits in, and say whether they said it or you inferred it.
- `fixed`: what they cannot change: the data they have, an instrument, a rule of their field, a deadline, a requirement of a journal or a regulator, whether anyone else works on it with them. A shift that breaks one of these is no use to them.

Save it all as JSON to `/tmp/astaui-tree.json`: the tree, its root the `goal` node and each node with `kind`, `general`, `specific`, `confidence`, `why` and `children`, with `question`, `weak_points` and `fixed` as three more keys on the root.

Every node under 0.7 is a question for the scientist, unless looking at their data would answer it. Ask first about the ones that would change the interface most (a phase before a task; whether they decide one item at a time or compare many side by side; what they hand on at the end), and ask at most four in one round. Put each as one plain question with two to four answers, each a concrete way that part of their work could go, in their words, the likeliest first, and always leave room for an answer of their own. Use your client's question tool if it has one (in Claude Code, AskUserQuestion, which adds the write-your-own choice by itself); otherwise write the questions as a short numbered list with lettered answers, the last one "Something else (say how)". Above the questions, show the tree in a few lines, goal then phases then tasks, with the unsure parts marked, so they can see what each question is about and correct anything else while they are there. Do not ask about weak points here: they are yours to check against the knowledge base in step 5, and the scientist will see them with the shifts in step 8.

Fold their answers into the tree: an answered node scores 1, and an answer of their own may add, move or remove nodes. Ask a second round only if an answer opened a new question under 0.7. If nobody can answer (a test run, or they told you to go ahead without asking), take the likeliest answer for each, mark that node `"assumed": true`, and name those parts when you offer the plan in step 8.

## 3. Describe it as a query card

Run `astaui describe "<their request, in their words>"`, adding `--context <file>` with a few lines about their data if you looked at it. It prints the instructions and the vocabulary. Write the query card it asks for as JSON to a temporary file such as `/tmp/astaui-query.json`. Fill only the facets the request supports, counting their answers in step 2 as part of the request; an empty facet is better than a guessed one. Write `summary` as the workflow they want, in order.

Take most care over the `workflow`, because the knowledge base is organised by workflow and everything after this step is built from it. Build it from the tree you settled in step 2: its steps are the tree's tasks, in order, each worded generally (one of the listed moves when it fits) and then, in `here`, the way they want it done. Its `distinctive` list is what makes their case their own: the constraint, the quantity, the rule of their field, the thing they said they cannot do without, including what they told you in their answers. Those are what you will check each reference against.

(If the person has an Anthropic API key and prefers it, `astaui describe "<request>" --api --out /tmp/astaui-query.json` does this step through Claude instead.)

## 4. Search by workflow

```sh
astaui search "<their request>" --card /tmp/astaui-query.json --no-code
```

`--no-code` leaves the builds' code out of the answer, which is what you want: you are looking for workflows, not code. Each result carries why it matched (a score per facet and the ontology words it shares with the request), the builder's summary and first prompts, and its workflow lined up with the scientist's: the **same steps**, with how each side does them; the steps **only it** has; the steps **only they** asked for; what is **particular to it**; and their distinctive needs, each marked likely met or to check, with the closest thing the build has.

After the list comes the **far match**: the closest build from another field with the same structure, judged on data, task, mechanism and stage alone. Then a few **pieces from elsewhere**: views and components from other builds that fit. `--where shape=table` (or `verb=`, `stage=`, `view=`, `interaction=`, `pattern=`, `field=`, `kind=`) filters exactly; `--k 8` shows more.

Scores are only comparable within one search (their scale depends on the embedder), so judge closeness by what is shared. If no result shares the request's data shape or its task (the `shares:` line, or `shared` in JSON), the knowledge base has nothing close: say so, and build from the request alone.

This search is also the baseline for step 5: a step every close build already has is not news to them. It prints an id (`Logged as search …`). Keep it, and the ids of the searches in step 5, for steps 10 and 12.

## 5. Look for other ways of doing this work

A search by their workflow finds builds that work the way they already do; the differences come from the searches around it. Write a card for each search below as its own file, filling only the facets the request supports.

1. **Same data, any workflow.** Copy the first card to `/tmp/astaui-data.json`, keep the facets about their data and their field, and leave out the `workflow`. `astaui search "<their data, in their field>" --card /tmp/astaui-data.json --no-code --no-far --k 8`, with `--exclude <id>` for each build from step 4. A `--where shape=` or `field=` filter, using the first card's words, keeps it on their data. Scientists who hold the same data and do something else with it are the richest source of shifts.
2. **Same goal, other data.** A card with only the goal, the stage of research and the kind of result (the `question` from step 2, in general words), and no data shape. `astaui search "<the goal, in general words>" --card /tmp/astaui-goal.json --no-code --k 8`. This finds how other fields reach the same kind of result: a screening, a decision under uncertainty, a reconciled record, a comparison across conditions.
3. **Each weak point.** For the one or two weak points that matter most, a short search for work that handles that part well: "check one coder's codes against a second's", "flag a value against a baseline built from earlier runs", "keep an audit trail of every decision". `astaui search "<the weak point, as a need>" --no-code --k 6`, with no card or a card holding only that step.
4. **Workflow families.** `astaui workflows` once (it is long; search its output rather than reading it all). Find the family the builds from step 4 sit in, read its shared steps, and read the `its own steps` and `particular to it` lines of the builds in that family and in the families next to it. Those lines are where one lab's way of working shows: a rule for when a value passes, a two-tier check, a record split into phases, a re-audit against an earlier run.

Collect the builds whose workflow differs from theirs in a way that touches their goal or a weak point; five to ten is enough. For each, open `<kb>/builds/<id>/tree.json` and read its `tree` against yours, phase by phase. When two candidates seem to differ from each other in an interesting way, `astaui compare <a> <b>` lines them up. Read `prompts.jsonl` too: later prompts often say what the builder found wrong with their first way of working and what they changed, which is a shift someone has already tried.

Name each difference as a **shift**: one change to their workflow, said as what they would do differently. Most fall into one of these kinds:

| Kind | What changes | For example |
|---|---|---|
| `add-stage` | A phase or task they do not have: a check, a calibration, a baseline, a pilot, a held-out set, a plan written before the data | A second coder codes a sample blind, and disagreements are settled before the codebook is fixed |
| `reorder` | The same work in another order | Look over every item at a glance before coding any, so the categories come from the data |
| `schema` | What one record holds, or what counts as one item | Each call keeps its confidence and the evidence behind it, not only the label |
| `loop` | A step that sends work back when something changes | A new code sends the earlier passages back for a second look |
| `tier` | One pass split into a quick screen and a careful review, or many hands into one | A threshold flags candidates; only flagged ones go to a person, each checked on the raw signal |
| `compare` | A result read against something: a baseline, the item's own past, a reference population, another condition | Each well is scored against its own plate's controls, not a fixed cut-off |
| `hand-off` | What leaves at the end, and in what form | Every number in the report carries the file and command that made it |

Write each shift down with the builds that do it and how each does it, in one line. A shift that several builds share, from more than one field, is a common move; one that only one build has may be a single lab's habit. Say which.

The same searches may turn up something on their data that is not a change to how they work: a view, a chart, an AI step, an arrangement of views, a sequence to start the analysis in. Keep the best one or two of those as ideas for step 11.

If the searches find nothing that shares their data shape, their goal or a weak point (the `shares:` line, or `shared` in JSON, is empty throughout), the knowledge base has no other way of working to offer: say so in one line and go on to step 7 with their own workflow.

## 6. Judge which shifts would help this scientist

Go through the shifts and keep the ones that would let this scientist find, check or do something they cannot now. For each, write:

- `payoff`: what they could find, check or do, in their words, in one sentence. "You would see whether the two of you read 'reluctance' the same way before you code the other 40 interviews." Not "improves rigour".
- `serves`: the weak point it answers or the part of their `question` it helps with. A shift that serves neither is dropped.
- `cost`: what it asks of them: time, a second person, data they would have to collect, a change to what they hand on, a step they would have to take before the one they asked for.
- `fits`: whether their data and their `fixed` constraints allow it. A shift that needs data they do not have, or breaks a rule of their field, is dropped, or kept as an idea for later with that said.
- `evidence`: the builds and fields it comes from, whether each is their field (`same_field`) and whether it is a common move or one build's.

Rank what is left by payoff for this scientist against its cost. Prefer shifts that open discovery (a pattern they could not see, an error they could not catch, a question the data could change) over ones that only save time. Prefer a shift from another field when it answers a weak point that their own field's builds leave open: that is the knowledge base's best gift, and the one they are least likely to think of. Keep two to four. If two shifts only make sense together, offer them as one.

## 7. Look at the references

Take the one or two closest builds from step 4, the far match, and the builds behind the shifts you kept, and look at each interface as a person would see it, not at its code. A build that taught a shift often shows best how an interface serves it. Each build's folder is `<kb>/builds/<id>/`, and most hold:

- `screenshot.webp`: what it looks like. Open it.
- `tree.json`: what an agent found by using it. Its `tree` has the same shape as the one you wrote in step 2, so its phases and tasks can be read against the scientist's. Its `features` list names each feature, with a `general` description in words any field would use, the `specific` way this build does it, the `steps` a person takes with it, the tasks it serves (`serves_tasks`), and `screens` (in the same folder) that show it in use. Open the screens for the features that look useful.
- `prompts.jsonl`: what the builder asked for, in order. Later prompts often name what was wrong with a first version and what fixed it. Those are lessons you can take without taking any code.

Each result's `standing` line says how vetted the build is: its GitHub stars when it came from a public repository, or how many times agents fetched it and scientists approved it in AstaUI when a scientist sent it in (`astaui stats <id>` says the same for any build). Let it settle a tie between two builds that serve a step equally well, never outweigh a closer match: most public builds have few stars, and a build sent in last week has had no time to be approved.

For each feature, ask whether it serves a task in this scientist's tree, one of their distinctive needs, or one of the shifts you kept. Be selective: a feature that suited the original builder's field may only add clutter here, and two references may each do one step better than the other.

## 8. Plan the features, offer the shifts, and let them choose

Go through the scientist's workflow one step at a time and decide what the interface will do for each:

| For each step of their workflow | Decide |
|---|---|
| A reference does it well | Take the feature: from which build, and what about it is worth having |
| A reference does it, but for a different item or not well | Take the idea and say what you will do differently |
| No reference does it | It is new work |
| A reference has a feature for a step they did not ask for | Leave it out unless it clearly helps them; say which |

Then go through their distinctive needs and say how the interface will meet each one.

The plan covers every task they asked for, as fully as the references allow, whatever they choose next: a shift adds a stage, a record field or a check to their work, or changes how one step is done, and never takes away a feature that serves a step they asked for (moving through items, undoing a slip, finding one again, seeing what is left, the display controls that let them read their data).

Then show them, briefly and in plain words:

1. Their workflow as you understood it, in a few lines, with the weak points marked and any part you assumed because nobody could answer in step 2.
2. The closest builds and the field each came from (saying which are from their own field and which from another), the far match if it lends something, and the feature plan.
3. Each shift you kept, as a change to that workflow: what they would do differently and where in their work it goes, the payoff, the cost, and where it comes from ("blind double-coding of a sample, as the ecologists coding field notes in `<build id>` do; from another field"). Show it against their tree, so the new stage or the changed record is in its place, not in a list on its own. Say in one line what the closest builds already have, so they can see the shifts are differences, not the usual.

Say that each feature and shift taken from a build will carry a credit they can open from a Show sources switch, naming its builder where the build is public (step 10), and that the shifts they do not take will stay in the interface as other ways to work (step 11).

Then ask which shifts to take, as one multiple-choice question that allows several answers, with "Keep my workflow as it is" among the choices. Use your client's question tool; otherwise a numbered list they can answer with numbers. If they take none, build the plan for their workflow as it is.

If nobody can answer (a test run, or they told you to go ahead without asking), build their workflow as it is and take no shift: a change to how someone works is theirs to make. Every shift you kept is then offered in the interface, and you say so when you close.

When they take one or more, write their workflow with the chosen shifts folded in, in the same tree shape as step 2. Each node keeps where it came from: `"origin": "theirs"` for what they described, `"origin": "shift"` with `"shift": "<shift id>"` for a stage, task or record field that a shift added or changed, and for a moved node, where it was before (`"was": "<its old phase>"`). Then match interfaces to the workflow they chose: write a card from the chosen tree as in step 3, with the shifted stages in their place and the shifts themselves in `distinctive` (the second coder, the per-plate baseline, the confidence on each call), and run `astaui search "<their request, with the chosen shifts>" --card /tmp/astaui-chosen.json --no-code`. Look at any new reference as in step 7, add to the plan what the shifted stages need, and give them the most care: they are new to this scientist, so the interface has to make the new step easy to do and its payoff easy to see (the disagreements between coders laid side by side; the flagged wells next to their plate's controls). Tell them what the plan gained in a line or two, and go ahead unless they choose otherwise.

Save everything about the shifts as `app/astaui-shift.json`, and the same JSON inside the page in `<script type="application/json" id="astaui-shift">`, whatever they chose:

```json
{"searches": ["<search ids>"],
 "field": "the scientist's field, in a few words",
 "question": "what they are trying to find out or decide",
 "current": {"goal": "...", "phases": [{"phase": "...", "tasks": ["..."]}],
   "weak_points": [{"point": "...", "where": "phase or task", "kind": "slow | blind | fragile", "assumed": false}]},
 "shifts": [{"id": "s1", "shift": "what they would do differently, a few words, in their words",
   "kind": "add-stage | reorder | schema | loop | tier | compare | hand-off",
   "where": "the phase or task of theirs it changes",
   "change": "the change, one sentence",
   "payoff": "what they could find, check or do that they cannot now, one sentence",
   "serves": "the weak point or the part of their question it answers",
   "cost": "what it asks of them, one line",
   "common": "common move | one build",
   "from": [{"build": "<build id>", "title": "...", "field": "...", "same_field": false,
             "how": "how that workflow does it, one line", "step": "its step, in its words"}],
   "verdict": "chosen | offered | dropped", "reason": "why, one line"}],
 "chosen": ["s1"],
 "assumed": false,
 "workflow": {"goal": "...", "children": ["the tree they chose, each node with origin"]}}
```

List every shift you weighed in step 6, dropped ones too, each with its reason. `offered` is a shift you kept but they did not choose. `assumed` is true when nobody could answer. With no shift chosen, `chosen` is empty and `workflow` is their tree as it stands, every node `"origin": "theirs"`.

## 9. Build it new

Write the interface from nothing for this scientist: their item, their data, their categories, their words, organised around the workflow they chose. Choose the structure, the libraries and the layout that suit their case best, which may differ from every reference. Implement each feature in the plan in your own way, and improve on the reference where you can see how.

- Do not paste a build's code or edit a copy of it, and do not open a build's code to get started.
- If a feature's behaviour is unclear from its screens and its steps (an edge case, a rule for when a value is missing, how an undo works), you may read how the build does it, with `astaui slice <build> <part>` or a search without `--no-code`, to understand it. Then write your own.
- Never carry over a reference's sample data or labels from its field. Its builder appears only in the credits of step 10, never in the interface's own labels or data.

Put one comment at the top of what you build, naming its references: `Features drawn from <build ids> in the AstaUI knowledge base; the code is new. Credits are in astaui-sources.json, workflow shifts in astaui-shift.json.`

**Show the workflow in the interface.** Give it a Workflow view, opened from the header or menu: their workflow as a row of phases in order, each with its tasks, laid out the way the interface is (a phase that is a tab here is that tab there, and clicking it goes to it). When they chose a shift, mark each stage, task or record field it added or changed with a small "New" or "Changed" tag; selecting a marked part shows the shift: the change, its payoff, its cost, and where it came from. A toggle in the view, "As you described it", then shows their original workflow beside it, so the difference reads at a glance. With no shift chosen there is nothing to tag and no toggle: the view is their workflow as a map of the interface. At the foot of the view sits Other ways to work (step 11).

Build the credits (step 10) and the other ways to work (step 11) with the rest, then test it all and show it working, as you would any interface, with Show sources off (as it opens) and on.

## 10. Credit the references in the interface

Every feature and every shift you took from a reference keeps a credit inside the interface, so the scientist can see where an idea came from and who made it, and go and look at it. The credit is part of what they use, not a comment in the code.

Write the credits down first, as `app/astaui-sources.json` and the same JSON inside the page in `<script type="application/json" id="astaui-sources">`, so it works with no server:

```json
{"search": "<the search id from step 4, or from the chosen-workflow search in step 8>",
 "field": "the scientist's field, in a few words, as in the query card",
 "references": [{"build": "<build id>", "title": "...", "by": "...", "link": "...", "paper": "...", "license": "...", "field": "...", "same_field": true, "workflow": "its goal, in general words",
   "standing": {"signal": "github | astaui | example", "line": "...", "vetted": "well vetted | some vetting | barely vetted", "stars": 0, "stars_at": "...", "retrieved": 0, "fetched": 0, "approved": 0, "checked": "<today>"}}],
 "features": [{"feature": "its name in the scientist's words", "from": "<build id> or new",
   "shift": "<shift id> when the feature serves a chosen shift, else omit",
   "summary": "what it does for them, up to 10 words",
   "brought": "what the reference had and what its scientists use it for, up to 20 words",
   "why": "why it matched: the step both share and what makes it the same work, one sentence, up to 30 words",
   "use": "how to use it here, up to 12 words",
   "step": "the step of their workflow it serves, in their words", "matched": "the step of the reference's workflow it answered to, in its words",
   "took": "what you took, one line", "changed": "what you did differently, one line"}],
 "ideas": []}
```

Put every build a shift came from in `references` too, offered shifts included. `same_field` says whether the reference comes from the scientist's own field: `true` when its field is theirs or a branch of it (a microbiologist, and a build from bacteriology), `false` when it is another field (a linguist, and a build from ecology). Judge it from the build's field, not from its data: two fields can share a data shape and still be different fields.

Every feature taken from a reference says, in four short parts, what it is and why it is here, so the scientist can take it in at a glance:

- `summary`: what it does for them, in their words. A label, not a sentence: "Earlier passages with this code, beside the one you are coding".
- `brought`: what the reference had and what its scientists use it for: "Ecologists coding field notes keep every passage already given a code in a side panel."
- `why`: why it matched, the reason it was brought over: the step of their work and the reference's step it answered to, and what makes them the same kind of work. "Both of you decide one item against a growing set of past decisions, so earlier ones keep new codes consistent."
- `use`: the click, key or gesture: "Press a code's number key; its past passages open on the right."

Keep each within its limit; cut a word before you add a clause. Fill `step` from your tree and `matched` from the reference's `tree.json`, and write `why` from the two. Never write a reason the reference does not support: if all you can say is that it looked useful, the feature does not belong in the plan.

Take `by`, `link`, `paper` and `license` from the build's `<kb>/builds/<id>/build.json` and from nowhere else:

| The build's `provenance.consent` | `by` | `link` and `paper` |
|---|---|---|
| `public` | `author.name`, the GitHub user or organisation | `source.repo`, and `provenance.found.paper` if it has one |
| anything else | the author's role and field ("a postdoc in microbiology"), never `author.name` | none |

Never write a name you found anywhere else, and never guess one.

Take each reference's `standing` from `astaui stats <build ids> --json`, run once for all of them while you write the file, and copy its fields as they come; add `checked` with today's date. It tells the scientist how far to trust a borrowed idea:

| `standing.signal` | What it is judged on | What the card says |
|---|---|---|
| `github` | the repository's GitHub stars (`stars`, counted on `stars_at`) | "240 GitHub stars", with `vetted` |
| `astaui` | a build a scientist sent in: how often agents fetched it in AstaUI and how many approved it after building from it (`fetched`, `approved`) | "Fetched 12 times in AstaUI, approved by 4", with `vetted`; "New to AstaUI: nobody has fetched it yet" when both are 0 |
| `example` | nothing: an example made for AstaUI, not a scientist's own tool | its `line`, with no level |

When `stars` is null (not checked yet) write "GitHub stars not checked" and no level. Never round a count up, call a build vetted that `vetted` does not, or leave a low count out: a barely vetted reference is worth knowing about, so say it.

In the interface, each element that does a credited feature carries `data-astaui-feature="<feature>"` and `data-astaui-ref="<build id>"`, and each part of the Workflow view that a chosen shift added or changed carries `data-astaui-shift="<shift id>"` and `data-astaui-ref="<the first build it came from>"`. AstaUI annotates them from outside, the way a reviewer marks up a page. The credit should read as a note laid over the interface ("this came from elsewhere"), never as one of its own controls:

- **Colour by field.** A feature or shift from a reference in the scientist's own field (`same_field: true`) is marked in Asta green (`#0fcb8c`); one from another field in Asta blue (`#2a88ef`). The two differ in hue only: the same frame, weight, opacity and logo, so they read as one kind of mark, and a glance at the colour says whether the idea came from next door or from further away. Colour is never the only sign: the hover line and the card say it in words too.
- **Highlight.** A light frame around the element: a 1.5 px outline in the field colour at about 40% opacity, 3 px outside the element, its corners a little rounder than the element's, over a faint wash of the same colour (about 6%). It is drawn in a layer over the page, positioned on the element and kept there as the page scrolls or resizes, never inside the element's own layout: it takes no space, moves nothing, and never hides the scientist's data. (An outline or pseudo-element on the element itself is clipped by scrolling containers and not drawn at all on inputs and images.)
- **Logo.** The Asta logo, about 16 px, pinned on the frame's top-left corner so that it sits half outside it, on a small round chip in the page's background colour, ringed 1.5 px in the field colour, so it reads on any surface. Use this SVG exactly; do not redraw the logo, recolour it or use another symbol:

```html
<svg viewBox="0 0 180 180" width="16" height="16" aria-hidden="true"><path fill="#0fcb8c" d="M72,70.25h-36v-34.25h28.98c3.87,0,7.02-3.15,7.02-7.02V0h34.25v36c0,18.92-15.33,34.25-34.25,34.25ZM36,73.75H0v34.25h28.98c3.87,0,7.02,3.15,7.02,7.02v28.98h34.25v-36c0-18.92-15.33-34.25-34.25-34.25ZM151.02,72c-3.87,0-7.02-3.15-7.02-7.02v-28.98h-34.25v36c0,18.92,15.33,34.25,34.25,34.25h36v-34.25h-28.98ZM73.75,144v36h34.25v-28.98c0-3.87,3.15-7.02,7.02-7.02h28.98v-34.25h-36c-18.92,0-34.25,15.33-34.25,34.25Z"/></svg>
```

At rest the frame is faint and the logo full strength. The frame strengthens while the pointer is over the element or its logo, or the logo has focus. Only the logo takes the pointer: the frame lets clicks through to the element. The logo is a button labelled `Source: <feature or shift>`. Hovering or focusing it shows one line: `<summary> · your field` or `<summary> · from <field>`, then ` · ` and the reference's standing in a few words (`★ 240`, `4 approvals`, `new to AstaUI`, `example`), so the scientist can tell a well-vetted idea from an untried one without opening anything. Clicking it, or Enter on it, opens a small card beside it, no wider than about 320 px, that can be read in a few seconds. For a feature, open at first:

- the feature's name, and under it a field tag: a dot in the field colour and "Your field: <field>" or "Another field: <field>";
- `summary`, as the card's first line, a little larger than the rest;
- Why it's here: two short lines, **Brought** with `brought` and **Matched** with `why`;
- **Use**: `use`;
- **Vetted**: the reference's `standing.line`, and `vetted` after it when there is one ("240 GitHub stars · well vetted", "Fetched 3 times in AstaUI, approved by 1 · some vetting"). For `github` the count links to the repository's stargazers page. Draw the level as a small meter of three steps in the field colour (one filled for barely vetted, two for some vetting, three for well vetted, none for an example), beside the words and never instead of them.

For a shift: its name with the field tag, the `change`, **Payoff**, **Cost**, and **From** with each source build's `how` and its standing, as **Vetted** above.

Under a More disclosure, closed at first:

- what was taken and what was changed;
- your step and the reference's step it matched, side by side;
- the reference: its title, who made it, and the workflow it serves;
- how its standing was counted: for GitHub, the date the stars were counted; for AstaUI, how many searches retrieved it, how many times it was fetched and approved, and that an approval is a scientist saying it helped; with the date it was `checked`;
- its repository and paper, when it is public, opening in a new tab;
- Explore in AstaUI: the command that opens it, `astaui show <build id>`, with a Copy button;
- Build on this: a Copy button for a request the scientist can give their agent to take the interface further along that reference's workflow ("Using <build id> from AstaUI as a reference, change this interface so that …").

Escape or a click elsewhere closes the card. Features no reference had (`from: new`) get no frame and no logo.

Add a Sources list: the references from their own field first, then those from other fields, each with its field tag, its credit and its **Vetted** line, and under each the shifts and the features taken from it, each feature as its `summary` with its `why` beneath. That puts in one place everything the interface owes to others, what each part is for and why it was brought over.

Give the interface one switch for all of it, Show sources, in its settings or menu, or as a small toggle in a corner when it has neither. It is off at first: the interface opens as the scientist's own tool, with no frame, logo, card or list drawn, and they turn the switch on when they want to see which features and shifts were borrowed and where each came from. Put the Asta logo beside the switch's label so they can find it without the frames to point at it. Remember the choice in `localStorage` under a key named for this app, so once they turn it on it stays on. Turning it on or off moves nothing else on the page. The Workflow view stays either way, since it is how they find their way around the work; only its credits go.

## 11. Offer other ways to work

The shifts they did not choose, and the ideas you kept in step 5, stay in the interface as offers. Do not build them.

Add each to `ideas` in `astaui-sources.json`: `{"idea": "what it adds, a few words", "kind": "sequence | feature | ai | view | arrangement", "why": "what it would let them do, its payoff for a shift, one line, in their words", "workflow": "the other workflow, in general words", "from": "<build id>", "shift": "<shift id>, for an offered shift, else omit", "prompt": "the request that would add it"}`, with the build's credit in `references` as in step 10. Two to five in all; an offered shift comes before an idea that is not a change to how they work.

Show them at the foot of the Workflow view under Other ways to work. Each is a short row: what it adds and its payoff, for a shift where in their work it would go and what it costs, the workflow and build it comes from with its field tag and how vetted it is (when Show sources is on, its logo, ringed in the field colour, opens that build's card, as in step 10), and Copy request, which copies its `prompt` so the scientist can ask their agent for it. Dismiss puts one away, remembered in `localStorage`. These are offers: the interface does not change until the scientist asks for one.

If step 5 found nothing to offer, leave Other ways to work out and say so in one line.

## 12. Close the loop

Once the scientist has the interface:

- If they took a shift, tell them in two or three sentences how the interface asks them to work differently from how they described, what each chosen shift should let them find or check, and where it came from. If they took none, or nobody could choose, say in one sentence how many other ways to work it offers and where they are.
- Tell them in one sentence where the Workflow view and the credits are, how many credits come from their own field and how many from others, and that the credits appear when they turn on Show sources, which is off at first.
- Offer a walkthrough in one sentence: you can add a step-by-step guide to the interface that goes through their work in order, ringing each control and saying what to do with it, starting with any stage that is new to them. Do not add it unasked. It is a layer on top of the interface, made once it works the way they want. When they ask, follow `walkthrough.md` in this skill's folder.
- Record whether the references helped. It is part of the research this knowledge base exists for, and it is what the next scientist's **Vetted** line counts as an approval: `astaui feedback <search id> <build id> --used yes --helped yes` (or `no`) for each build a feature or a chosen shift came from, with `--note "…"` naming the features or the shift you took from it and anything the scientist said about it.
- Do not file it. The scientist has not used it yet, and it will change as they do: what you send now may not be ready for anyone else, or be what they would want shared. Say in one sentence that when it is working the way they want, they can ask you to file it into AstaUI so the next scientist can start from it, and then the workflow they chose becomes one the next scientist can find. Then leave it with them.
- File it only when they ask. Then follow the `ui-to-workflow` skill, with this folder as the app and this conversation's prompts as its prompts (`--session this`).
- If it was filed before (`astaui filed` says so) and they change it, do not send the newer copy on your own either. File it again under the same id with `--replace` when they ask.
