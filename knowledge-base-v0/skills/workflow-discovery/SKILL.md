---
name: workflow-discovery
description: Help a scientist find better ways of doing their work, from how other scientists work, and build the interface for the way they choose. Use when a scientist asks for a UI, tool, dashboard, viewer, workbench or app for their research and could gain from working differently, or asks how others do this kind of work. Write down how they work now as a tree of phases and tasks, and where it is slow, blind or fragile; search the AstaUI knowledge base for other scientists' workflows on the same data, toward the same goal or around the same weak point, including other fields; line each one up against theirs and name what it does differently (a stage added, an order changed, a record that holds more, a loop, a second tier, a comparison against a baseline); judge which of those shifts would let this scientist find, check or do something they cannot now; offer two to four with their payoff, cost and source, and let them choose. Then match the chosen workflow to interfaces in the knowledge base, build the interface in new code, show the workflow change inside it with a credit for each stage and feature taken from another scientist's work, and offer the shifts they did not take.
---

# Workflow discovery

A scientist has asked you to build an interface for the way they work now. Other scientists work on the same kind of data, toward the same kind of result, and some of them have arranged that work differently: they check something earlier, keep more in each record, split one pass into two, compare against a baseline, loop back when a result surprises them. The AstaUI knowledge base holds their interfaces, and with each one the workflow an agent found by using it. Those workflows are what this skill is about.

Your job is in two halves. First, find the ways other scientists work that would help this one, and offer them as concrete changes to their own workflow, with what each would let them see or check, what it costs and where it comes from. Second, once they have chosen, build the interface for the workflow they chose, using the knowledge base's interfaces as references, the way a designer uses references.

Matching their workflow as it is finds interfaces that do what they already do. That is useful, but it can only give them back their own way of working, better drawn. Here you look for the differences on purpose. A difference is worth offering only when it serves their goal: a stage that catches an error they cannot catch now, a record that keeps what they will need later, an order that lets the data change their question before they commit to it. Never offer a change because it is new or because another field does it.

## Running the tool

The knowledge base's command is `astaui`. Use it if it is on the PATH (`pip install -e` puts it there). Otherwise run `python3 <this skill's folder>/../../astaui_cli.py`; this skill's folder is the base directory you were given when the skill loaded. Below, `astaui` means whichever works. Check it once with `astaui status`; its first line names the knowledge base folder, called `<kb>` below.

It needs Python 3.9 or later and nothing else. Nothing in these steps sends the scientist's data anywhere: describing the work is your own job, and the search runs on this machine.

The commands you will use most:

| Command | What it gives you |
|---|---|
| `astaui search "<words>" --card <file> --no-code` | Builds whose card matches, each with its workflow lined up against yours: same steps, its own steps, your own steps, what is particular to it |
| `astaui workflows` | Every build grouped into workflow families, with each family's shared steps and each build's own steps and particular rules |
| `astaui compare <build> <build>` | Two builds' workflows lined up: shared steps, how each does them, what is each one's own |
| `astaui show <build>` | One build: its prompts, files and card |

## 1. Understand the request

Read what they asked for. If their data is in the working folder, look at it the way a person would before building: file names, a header row, a few lines, the size. Note what one item is (a transcript passage, a well, a frame, a record), what they do to it, and what they want to come out at the end: a finding, a decision, a cleaned data set, a figure, a paper. Do not ask questions you can answer by looking, and do not ask anything yet.

## 2. Write down how they work now

Write the work as you understand it, as a tree in the knowledge base's own shape: one `goal`, the `phase`s it moves through in order, and under each phase the `task`s a person does there. Give each node a `general` line in words any field would use and a `specific` line in theirs, as the builds' `tree.json` files do. Include the parts they did not mention but must do (how items come in, how a decision is recorded, what leaves at the end).

Score each node for how sure you are of it, from 0 to 1, with a few words on why: 0.9 or more when they said it or their data shows it, 0.7 to 0.9 when it follows clearly, below 0.7 when you are guessing.

Then add what this skill needs that a plain workflow tree does not hold. For the work as a whole, write:

- `question`: what they are trying to find out or decide, in one line. A workflow serves a question, and a better workflow is better for that question.
- `weak_points`: where the work, as they describe it, is slow (a step done by hand item after item), blind (something they cannot see or check: an error that would pass unnoticed, a bias, a pattern across items that one-at-a-time work hides), or fragile (a decision that cannot be traced or redone, a result that depends on one person's judgment). Name each with the phase or task it sits in, and say whether they said it or you inferred it.
- `fixed`: what they cannot change: the data they have, an instrument, a rule of their field, a deadline, a requirement of a journal or a regulator. A shift that breaks one of these is no use to them.

Save it all as JSON to `/tmp/astaui-tree.json`: the tree, its root the `goal` node and each node with `kind`, `general`, `specific`, `confidence`, `why` and `children`, with `question`, `weak_points` and `fixed` as three more keys on the root.

Every node under 0.7, and any weak point you inferred, is a question for the scientist unless looking at their data would answer it. Ask at most four in one round, about what would change the search most: what they want to come out at the end, what goes wrong today, what they cannot change. Put each as one plain question with two to four concrete answers in their words, the likeliest first, and leave room for an answer of their own. Use your client's question tool if it has one (in Claude Code, AskUserQuestion); otherwise write a short numbered list with lettered answers, the last one "Something else (say how)". Above the questions show the tree in a few lines with the unsure parts marked.

Fold their answers in. If nobody can answer (a test run, or they told you to go ahead), take the likeliest answer for each, mark that node or weak point `"assumed": true`, and name those parts when you offer the shifts in step 6.

## 3. Look for other ways of doing this work

Search the knowledge base from several sides. A search by their workflow alone finds builds that work the way they already do; the differences come from the searches around it. Run `astaui describe "<their request, in their words>"` once to get the vocabulary and the card's shape, then write a card for each search below as its own file, filling only the facets the request supports.

1. **Their own workflow.** The card with the `workflow` built from your tree, as the knowledge base expects: steps in order, each worded generally and then, in `here`, their way. `astaui search "<their request>" --card /tmp/astaui-query.json --no-code`. This is the baseline: the shifts you find later are measured against what the closest builds already do, and a step every close build has is not news to them.
2. **Same data, any workflow.** Copy the card to `/tmp/astaui-data.json`, keep the facets about their data and their field, and leave out the `workflow`. `astaui search "<their data, in their field>" --card /tmp/astaui-data.json --no-code --no-far --k 8`, with `--exclude <id>` for the builds from search 1. Scientists who hold the same data and do something else with it are the richest source of shifts.
3. **Same goal, other data.** A card with only the goal, the stage of research and the kind of result (the `question` from step 2, in general words), and no data shape. `astaui search "<the goal, in general words>" --card /tmp/astaui-goal.json --no-code --k 8`. This finds how other fields reach the same kind of result: a screening, a decision under uncertainty, a reconciled record, a comparison across conditions.
4. **Each weak point.** For the one or two weak points that matter most, a short search for work that handles that part well: "check one coder's codes against a second's", "flag a value against a baseline built from earlier runs", "keep an audit trail of every decision". `astaui search "<the weak point, as a need>" --no-code --k 6`, with no card or a card holding only that step.
5. **Workflow families.** `astaui workflows` once (it is long; search its output rather than reading it all). Find the family the builds from search 1 sit in, read its shared steps, and read the `its own steps` and `particular to it` lines of the builds in that family and in the families next to it. Those lines are where one lab's way of working shows: a rule for when a value passes, a two-tier check, a record split into phases, a re-audit against an earlier run.

Each search prints an id (`Logged as search …`). Keep them for steps 7 and 11.

Collect the builds whose workflow differs from theirs in a way that touches their goal or a weak point. Five to ten is enough. If the searches find nothing that shares their data shape, their goal or a weak point (the `shares:` line, or `shared` in JSON, is empty throughout), the knowledge base has no other way of working to offer: say so in one line and skip to step 8 with their own workflow.

## 4. Line each workflow up against theirs

For each candidate, open `<kb>/builds/<id>/tree.json` and read its `tree` against yours, phase by phase. When two candidates seem to differ from each other in an interesting way, `astaui compare <a> <b>` lines them up. Open `screenshot.webp` and the screens of the features that look relevant, and read `prompts.jsonl`: later prompts often say what the builder found wrong with their first way of working and what they changed, and that is a workflow shift someone has already tried.

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

## 5. Judge which shifts would help this scientist

Go through the shifts and keep the ones that would let this scientist find, check or do something they cannot now. For each, write:

- `payoff`: what they could find, check or do, in their words, in one sentence. "You would see whether the two of you read 'reluctance' the same way before you code the other 40 interviews." Not "improves rigour".
- `serves`: the weak point it answers or the part of their `question` it helps with. A shift that serves neither is dropped.
- `cost`: what it asks of them: time, a second person, data they would have to collect, a change to what they hand on.
- `fits`: whether their data and their `fixed` constraints allow it. A shift that needs data they do not have, or breaks a rule of their field, is dropped, or kept as an idea for later with that said.
- `evidence`: the builds and fields it comes from, whether each is their field (`same_field`) and whether it is a common move or one build's.

Rank what is left by payoff for this scientist against its cost. Prefer shifts that open discovery (a pattern they could not see, an error they could not catch, a question the data could change) over ones that only save time. Prefer a shift from another field when it answers a weak point that their own field's builds leave open: that is the knowledge base's best gift, and the one they are least likely to think of. Keep two to four. If two shifts only make sense together, offer them as one.

## 6. Offer the shifts, and let them choose

Show them, briefly and in plain words:

1. Their workflow as you understood it, in a few lines, with the weak points marked and any part you assumed.
2. Each shift you kept, as a change to that workflow: what they would do differently and where in their work it goes, the payoff, the cost, and where it comes from ("blind double-coding of a sample, as the ecologists coding field notes in `<build id>` do; from another field"). Show it against their tree, so the new stage or the changed record is in its place, not in a list on its own.
3. What the closest builds to their own workflow already have (search 1), in one line, so they can see the shifts are differences, not the usual.

Then ask which to take, as one multiple-choice question that allows several answers, with "Keep my workflow as it is" among the choices. Use your client's question tool; otherwise a numbered list they can answer with numbers. If they take none, build for their workflow as it is, and offer the shifts inside the interface (step 9).

If nobody can answer, take the one or two shifts with the best payoff for their cost that fit together and fit their constraints, mark the choice `"assumed": true`, and say so when you close.

## 7. Write the chosen workflow

Write their workflow with the chosen shifts folded in, in the same tree shape as step 2. Each node keeps where it came from: `"origin": "theirs"` for what they described, `"origin": "shift"` with `"shift": "<shift id>"` for a stage, task or record field that a shift added or changed, and for a moved node, where it was before (`"was": "<its old phase>"`).

Save everything about the shifts as `app/astaui-shift.json`, and the same JSON inside the page in `<script type="application/json" id="astaui-shift">`:

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
 "workflow": {"goal": "...", "children": ["the chosen tree, each node with origin"]}}
```

List every shift you weighed in step 5, dropped ones too, each with its reason. `offered` is a shift you kept but they did not choose.

## 8. Find interfaces for the chosen workflow

Now match interfaces to the workflow they chose, not the one they came with. Run `astaui describe "<their request>"` again if you need the instructions, and write the query card from the chosen tree: its steps are the tree's tasks in order, each worded generally and then, in `here`, their way, with the shifted stages in their place. Put in `distinctive` what makes their case their own, and the shifts themselves: the second coder, the per-plate baseline, the confidence on each call. Those are what you will check each reference against.

```sh
astaui search "<their request, with the chosen shifts>" --card /tmp/astaui-chosen.json --no-code
```

Each result carries why it matched, its workflow lined up with theirs (same steps, only it, only them, particular to it) and their distinctive needs marked likely met or to check. After the list comes the far match from another field, and a few pieces from elsewhere. `--where shape=table` (or `verb=`, `stage=`, `view=`, `interaction=`, `pattern=`, `field=`, `kind=`) filters exactly; `--k 8` shows more. Scores are only comparable within one search. The builds a shift came from are references too: a build that taught them the shift often shows best how an interface serves it.

Take the one or two closest builds, the far match and the builds behind the chosen shifts, and look at each interface as a person would see it, not at its code: `screenshot.webp`, `tree.json` (its `features`, each with a `general` description, the `specific` way the build does it, the `steps` a person takes, the tasks it serves and `screens` that show it in use), and `prompts.jsonl`. For each feature, ask whether it serves a task in the chosen tree or one of their distinctive needs. Be selective.

Then go through the chosen workflow one step at a time and decide what the interface does for each: take a reference's feature (from which build, and what about it is worth having), take its idea and do it differently, build it new because no reference does it, or leave a reference's feature out. Give the shifted stages the most care: they are new to this scientist, so the interface has to make the new step easy to do and its payoff easy to see (the disagreements between coders laid side by side; the flagged wells next to their plate's controls).

Tell the scientist the feature plan in a few lines and go ahead unless they choose otherwise.

## 9. Build it new

Write the interface from nothing for this scientist: their item, their data, their categories, their words, organised around the chosen workflow. Choose the structure, the libraries and the layout that suit their case best, which may differ from every reference. Implement each feature in the plan in your own way, and improve on the reference where you can see how.

- Do not paste a build's code or edit a copy of it, and do not open a build's code to get started.
- If a feature's behaviour is unclear from its screens and its steps, you may read how the build does it, with `astaui slice <build> <part>` or a search without `--no-code`, to understand it. Then write your own.
- Never carry over a reference's sample data or labels from its field. Its builder appears only in the credits of step 10, never in the interface's own labels or data.

Put one comment at the top of what you build: `Workflow shifts and features drawn from <build ids> in the AstaUI knowledge base; the code is new. Shifts are in astaui-shift.json, credits in astaui-sources.json.`

**Show the workflow change in the interface.** The scientist should be able to see, from inside the interface, how it asks them to work and what is new. Give it a Workflow view, opened from the header or menu: their workflow as a row of phases in order, each with its tasks, laid out the way the interface is (a phase that is a tab here is that tab there, and clicking it goes to it). Mark each stage, task or record field that a chosen shift added or changed with a small "New" tag, and with the Asta credit of step 10, coloured by field. Selecting a marked part shows the shift: the change, its payoff, its cost, and where it came from. A toggle in the view, "As you described it", shows their original workflow beside it, so the difference reads at a glance. The shifts they did not choose (`offered`) sit at the foot of the view under "Other ways to work", each with its payoff, its source and Copy request: a request they could give their agent to take that shift up. Dismiss puts one away, remembered in `localStorage`.

Build the credits and the ideas (steps 10 and 11) with the rest, then test it all and show it working, with Show sources on and off.

## 10. Credit the references in the interface

Every shift and every feature you took from another scientist's work keeps a credit inside the interface, so the scientist can see where an idea came from and who made it, and go and look at it.

Write the feature credits down as `app/astaui-sources.json` and the same JSON inside the page in `<script type="application/json" id="astaui-sources">`:

```json
{"search": "<the search id from step 8>",
 "field": "the scientist's field, in a few words",
 "references": [{"build": "<build id>", "title": "...", "by": "...", "link": "...", "paper": "...", "license": "...", "field": "...", "same_field": true, "workflow": "its goal, in general words"}],
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

Put every build that a shift came from in `references` too. `same_field` is `true` when the reference's field is theirs or a branch of it, `false` when it is another field; judge it from the build's field, not from its data. Keep `summary`, `brought`, `why` and `use` within their limits; never write a reason the reference does not support.

Take `by`, `link`, `paper` and `license` from the build's `<kb>/builds/<id>/build.json` and from nowhere else:

| The build's `provenance.consent` | `by` | `link` and `paper` |
|---|---|---|
| `public` | `author.name`, the GitHub user or organisation | `source.repo`, and `provenance.found.paper` if it has one |
| anything else | the author's role and field ("a postdoc in microbiology"), never `author.name` | none |

Never write a name you found anywhere else, and never guess one.

In the interface, each element that does a credited feature carries `data-astaui-feature="<feature>"` and `data-astaui-ref="<build id>"`, and each part of the Workflow view that a shift added carries `data-astaui-shift="<shift id>"` and `data-astaui-ref="<the first build it came from>"`. AstaUI annotates them from outside, the way a reviewer marks up a page; the credit reads as a note laid over the interface, never as one of its own controls:

- **Colour by field.** A shift or feature from a reference in the scientist's own field is marked in Asta green (`#0fcb8c`); one from another field in Asta blue (`#2a88ef`). The two differ in hue only, and colour is never the only sign: the hover line and the card say it in words too.
- **Highlight.** A light frame around the element: a 1.5 px outline in the field colour at about 40% opacity, 3 px outside the element, its corners a little rounder than the element's, over a faint wash of the same colour (about 6%). Draw it in a layer over the page, positioned on the element and kept there as the page scrolls or resizes, never inside the element's own layout: it takes no space, moves nothing, and never hides the scientist's data.
- **Logo.** The Asta logo, about 16 px, pinned on the frame's top-left corner so it sits half outside it, on a small round chip in the page's background colour, ringed 1.5 px in the field colour. Use this SVG exactly; do not redraw the logo, recolour it or use another symbol:

```html
<svg viewBox="0 0 180 180" width="16" height="16" aria-hidden="true"><path fill="#0fcb8c" d="M72,70.25h-36v-34.25h28.98c3.87,0,7.02-3.15,7.02-7.02V0h34.25v36c0,18.92-15.33,34.25-34.25,34.25ZM36,73.75H0v34.25h28.98c3.87,0,7.02,3.15,7.02,7.02v28.98h34.25v-36c0-18.92-15.33-34.25-34.25-34.25ZM151.02,72c-3.87,0-7.02-3.15-7.02-7.02v-28.98h-34.25v36c0,18.92,15.33,34.25,34.25,34.25h36v-34.25h-28.98ZM73.75,144v36h34.25v-28.98c0-3.87,3.15-7.02,7.02-7.02h28.98v-34.25h-36c-18.92,0-34.25,15.33-34.25,34.25Z"/></svg>
```

At rest the frame is faint and the logo full strength; the frame strengthens while the pointer is over the element or its logo. Only the logo takes the pointer. The logo is a button labelled `Source: <feature or shift>`. Hovering or focusing it shows one line: `<summary> · your field` or `<summary> · from <field>`. Clicking it, or Enter on it, opens a small card beside it, no wider than about 320 px. For a feature, open at first: its name with a field tag (a dot in the field colour and "Your field: <field>" or "Another field: <field>"), `summary` as the first line, **Brought** and **Matched** with `brought` and `why`, and **Use**. For a shift: its name with the field tag, the `change`, **Payoff**, **Cost**, and **From** with each source build's `how`. Under a More disclosure, closed at first: what was taken and changed (or, for a shift, your step and theirs side by side), the reference's title, who made it and its workflow, its repository and paper when public, Explore in AstaUI with the command `astaui show <build id>` and a Copy button, and Build on this, a Copy button for a request the scientist can give their agent to take the interface further along that reference's workflow. Escape or a click elsewhere closes the card. Features no reference had (`from: new`) get no frame and no logo.

Add a Sources list: the references from their own field first, then those from other fields, each with its field tag, and under each the shifts and the features taken from it.

Give the interface one switch for all of the annotation, Show sources, in its settings or menu, or as a small toggle in a corner when it has neither. It is on at first; remember the choice in `localStorage` under a key named for this app. With it off, no frame, logo, card or Sources list is drawn and nothing else on the page moves. The Workflow view stays, since it is how they find their way around the work; only its credits go.

## 11. Offer the other shifts as ideas

The shifts they did not choose already sit under "Other ways to work" in the Workflow view. Add them to `ideas` in `astaui-sources.json` as well, so the credits list them, each as `{"idea": "the shift, a few words", "kind": "sequence | feature | ai | view | arrangement", "why": "its payoff, in their words", "workflow": "the other workflow, in general words", "from": "<build id>", "shift": "<shift id>", "prompt": "the request that would take it up"}`. Do not build them. If search 2 or 3 turned up a view, a chart or an AI step on their data that is not a workflow change, it can be an idea too, with the same fields and no `shift`.

## 12. Close the loop

Once the scientist has the interface:

- Tell them in two or three sentences how the interface asks them to work differently from how they described, what each chosen shift should let them find or check, and where it came from. If you chose for them, say so and say how to change it.
- Tell them in one sentence where the Workflow view and the credits are, how many come from their own field and how many from others, and that Show sources hides the credits.
- Record whether the references helped: `astaui feedback <search id> <build id> --used yes --helped yes` (or `no`) for each build a shift or feature came from, with `--note "…"` naming the shift or features you took and anything the scientist said about them.
- Offer a walkthrough in one sentence, and add it only when they ask: when they do, follow `walkthrough.md` in the workflow-to-ui skill's folder, starting with the stages that are new to them.
- Do not file it. Say in one sentence that when it is working the way they want, they can ask you to file it into AstaUI so the next scientist can start from it, and then the workflow they chose becomes one the next scientist can find. File it only when they ask, following the `ui-to-workflow` skill.
