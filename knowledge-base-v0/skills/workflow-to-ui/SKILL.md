---
name: workflow-to-ui
description: Build an interface for a scientist's work, informed by what other scientists already built. Use when a scientist asks for a UI, tool, dashboard, viewer, workbench or app for their research (coding transcripts, reviewing papers, triaging images, checking plate data, exploring a dataset, annotating sequences, anything for science). Infer the scientist's workflow from the request as a tree of phases and tasks, ask multiple-choice questions about the parts it is unsure of, describe the request in the AstaUI knowledge base's terms, find builds whose workflow matches (including one from another field), look at how those interfaces work, pick the features that serve this scientist's workflow, and build the interface in new code of its own using the retrieved UI code as a reference. Credit each borrowed feature inside the interface with the build, its field and, for a public build, the repository it came from, and offer ideas from other workflows on the same data, all behind one switch, coloured by whether each came from the scientist's own field or another. Offer a step-by-step walkthrough of the finished interface, and add it when they ask.
---

# Workflow to UI

A scientist has asked you to build an interface. Other scientists have built interfaces for work with the same workflow, and the AstaUI knowledge base holds them: their prompts, their code, a screenshot, the features an agent found by using each one, and a card that says what each is for. Use them the way a designer uses references. Match the workflow, look at how those interfaces serve it, choose the features worth having, and then build this scientist's interface yourself, as well as you can, in new code.

The builds are references, not starting points. Their code was written for someone else's data, often quickly, by an agent that knew less about this scientist than you do, and copying it carries over its shortcuts and its assumptions. What is worth taking is the design: which views sit side by side, what a key does, how a correction is recorded, what a person needs to see before they decide.

## Running the tool

The knowledge base's command is `astaui`. Use it if it is on the PATH (`pip install -e` puts it there). Otherwise run `python3 <this skill's folder>/../../astaui_cli.py`; this skill's folder is the base directory you were given when the skill loaded. Below, `astaui` means whichever works. Check it once with `astaui status`; its first line names the knowledge base folder, called `<kb>` below.

It needs Python 3.9 or later and nothing else. Nothing in these steps sends the scientist's data anywhere: describing the request is your own work, and the search runs on this machine.

## 1. Understand the request

Read what they asked for. If their data is in the working folder, look at it the way a person would before building: file names, a header row, a few lines, the size. Note what one item is (a transcript passage, a well, a frame, a record) and what they will do to it. Do not ask questions you can answer by looking, and do not ask anything yet: what looking leaves unclear, you will ask about in step 2.

## 2. Infer their workflow tree, and ask about what is unsure

Before searching, write down the work as you understand it, as a tree in the knowledge base's own shape: one `goal` (what they want to come out of the work), the `phase`s it moves through in order, and under each phase the `task`s a person does there. Give each node a `general` line in words any field would use and a `specific` line in theirs, as the builds' `tree.json` files do. Include the parts an interface for this work would need even when they did not mention them (how items come in, how a decision is recorded, what leaves at the end), since those are the parts most often guessed wrong.

Then score each node for how sure you are of it, from 0 to 1, with a few words on why:

| Score | When |
|---|---|
| 0.9 to 1 | They said it in so many words, or their data shows it |
| 0.7 to 0.9 | It follows clearly from what they said or from their data |
| Below 0.7 | You are guessing: they did not say it, or what they said could go two ways that would make different interfaces |

Save the tree as JSON to `/tmp/astaui-tree.json`, each node with `kind`, `general`, `specific`, `confidence`, `why` and `children`.

Every node under 0.7 is a question for the scientist, unless looking at their data would answer it. Ask first about the ones that would change the interface most (a phase before a task; whether they decide one item at a time or compare many side by side; what they hand on at the end), and ask at most four in one round. Put each as one plain question with two to four answers, each a concrete way that part of their work could go, in their words, the likeliest first, and always leave room for an answer of their own. Use your client's question tool if it has one (in Claude Code, AskUserQuestion, which adds the write-your-own choice by itself); otherwise write the questions as a short numbered list with lettered answers, the last one "Something else (say how)". Above the questions, show the tree in a few lines, goal then phases then tasks, with the unsure parts marked, so they can see what each question is about and correct anything else while they are there.

Fold their answers into the tree: an answered node scores 1, and an answer of their own may add, move or remove nodes. Ask a second round only if an answer opened a new question under 0.7. If nobody can answer (a test run, or they told you to go ahead without asking), take the likeliest answer for each, mark that node `"assumed": true`, and name those parts when you offer the plan in step 6.

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

The search prints an id (`Logged as search …`). Keep it for steps 8 and 10.

## 5. Look at the references

Take the one or two closest builds and the far match, and look at each interface as a person would see it, not at its code. Each build's folder is `<kb>/builds/<id>/`, and most hold:

- `screenshot.webp`: what it looks like. Open it.
- `tree.json`: what an agent found by using it. Its `tree` has the same shape as the one you wrote in step 2, so its phases and tasks can be read against the scientist's. Its `features` list names each feature, with a `general` description in words any field would use, the `specific` way this build does it, the `steps` a person takes with it, the tasks it serves (`serves_tasks`), and `screens` (in the same folder) that show it in use. Open the screens for the features that look useful.
- `prompts.jsonl`: what the builder asked for, in order. Later prompts often name what was wrong with a first version and what fixed it. Those are lessons you can take without taking any code.

For each feature, ask whether it serves a task in this scientist's tree or one of their distinctive needs. Be selective: a feature that suited the original builder's field may only add clutter here, and two references may each do one step better than the other.

## 6. Plan the features, and offer the plan

Go through the scientist's workflow one step at a time and decide what the interface will do for each:

| For each step of their workflow | Decide |
|---|---|
| A reference does it well | Take the feature: from which build, and what about it is worth having |
| A reference does it, but for a different item or not well | Take the idea and say what you will do differently |
| No reference does it | It is new work |
| A reference has a feature for a step they did not ask for | Leave it out unless it clearly helps them; say which |

Then go through their distinctive needs and say how the interface will meet each one.

Tell the scientist, briefly and in plain words: the closest builds and the field each came from (saying which are from their own field and which from another), the far match if it lends something, the feature plan, and any part of their workflow you assumed because nobody could answer in step 2. Say that each feature taken from a build will carry a credit they can open from a Show sources switch, naming its builder where the build is public (step 8), and that the interface will offer a few ideas from other workflows on the same data (step 9). Then go ahead unless they choose otherwise.

## 7. Build it new

Write the interface from nothing for this scientist: their item, their data, their categories, their words. Choose the structure, the libraries and the layout that suit their case best, which may differ from every reference. Implement each feature in the plan in your own way, and improve on the reference where you can see how.

- Do not paste a build's code or edit a copy of it, and do not open a build's code to get started.
- If a feature's behaviour is unclear from its screens and its steps (an edge case, a rule for when a value is missing, how an undo works), you may read how the build does it, with `astaui slice <build> <part>` or a search without `--no-code`, to understand it. Then write your own.
- Never carry over a reference's sample data or labels from its field. Its builder appears only in the credits of step 8, never in the interface's own labels or data.

Put one comment at the top of what you build, naming its references: `Features drawn from <build ids> in the AstaUI knowledge base; the code is new. Credits are in astaui-sources.json.` Build the credits (step 8) and the ideas (step 9) with the rest, then test it all and show it working, as you would any interface, with Show sources off (as it opens) and on.

## 8. Credit the references in the interface

Every feature you took from a reference keeps a credit inside the interface, so the scientist can see where an idea came from and who made it, and go and look at it. The credit is part of what they use, not a comment in the code.

Write the credits down first, as `app/astaui-sources.json` and the same JSON inside the page in `<script type="application/json" id="astaui-sources">`, so it works with no server:

```json
{"search": "<search id>",
 "field": "the scientist's field, in a few words, as in the query card",
 "references": [{"build": "<build id>", "title": "...", "by": "...", "link": "...", "paper": "...", "license": "...", "field": "...", "same_field": true, "workflow": "its goal, in general words"}],
 "features": [{"feature": "its name in the scientist's words", "from": "<build id> or new",
   "summary": "what it does for them, up to 10 words",
   "brought": "what the reference had and what its scientists use it for, up to 20 words",
   "why": "why it matched: the step both share and what makes it the same work, one sentence, up to 30 words",
   "use": "how to use it here, up to 12 words",
   "step": "the step of their workflow it serves, in their words", "matched": "the step of the reference's workflow it answered to, in its words",
   "took": "what you took, one line", "changed": "what you did differently, one line"}],
 "ideas": []}
```

`same_field` says whether the reference comes from the scientist's own field: `true` when its field is theirs or a branch of it (a microbiologist, and a build from bacteriology), `false` when it is another field (a linguist, and a build from ecology). Judge it from the build's field, not from its data: two fields can share a data shape and still be different fields.

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

In the interface, each element that does a credited feature carries `data-astaui-feature="<feature>"` and `data-astaui-ref="<build id>"`, and AstaUI annotates it from outside, the way a reviewer marks up a page. The credit should read as a note laid over the interface ("this came from elsewhere"), never as one of its own controls:

- **Colour by field.** A feature from a reference in the scientist's own field (`same_field: true`) is marked in Asta green (`#0fcb8c`); one from another field in Asta blue (`#2a88ef`). The two differ in hue only: the same frame, weight, opacity and logo, so they read as one kind of mark, and a glance at the colour says whether the idea came from next door or from further away. Colour is never the only sign: the hover line and the card say it in words too.
- **Highlight.** A light frame around the element: a 1.5 px outline in the feature's field colour at about 40% opacity, 3 px outside the element, its corners a little rounder than the element's, over a faint wash of the same colour (about 6%). It is drawn in a layer over the page, positioned on the element and kept there as the page scrolls or resizes, never inside the element's own layout: it takes no space, moves nothing, and never hides the scientist's data. (An outline or pseudo-element on the element itself is clipped by scrolling containers and not drawn at all on inputs and images.)
- **Logo.** The Asta logo, about 16 px, pinned on the frame's top-left corner so that it sits half outside it, on a small round chip in the page's background colour, ringed 1.5 px in the field colour, so it reads on any surface. Use this SVG exactly; do not redraw the logo, recolour it or use another symbol:

```html
<svg viewBox="0 0 180 180" width="16" height="16" aria-hidden="true"><path fill="#0fcb8c" d="M72,70.25h-36v-34.25h28.98c3.87,0,7.02-3.15,7.02-7.02V0h34.25v36c0,18.92-15.33,34.25-34.25,34.25ZM36,73.75H0v34.25h28.98c3.87,0,7.02,3.15,7.02,7.02v28.98h34.25v-36c0-18.92-15.33-34.25-34.25-34.25ZM151.02,72c-3.87,0-7.02-3.15-7.02-7.02v-28.98h-34.25v36c0,18.92,15.33,34.25,34.25,34.25h36v-34.25h-28.98ZM73.75,144v36h34.25v-28.98c0-3.87,3.15-7.02,7.02-7.02h28.98v-34.25h-36c-18.92,0-34.25,15.33-34.25,34.25Z"/></svg>
```

At rest the frame is faint and the logo full strength. The frame strengthens while the pointer is over the element or its logo, or the logo has focus. Only the logo takes the pointer: the frame lets clicks through to the element. The logo is a button labelled `Source: <feature>`. Hovering or focusing it shows one line: `<summary> · your field` or `<summary> · from <field>`. Clicking it, or Enter on it, opens a small card beside it, no wider than about 320 px, that can be read in a few seconds. Open at first:

- the feature's name, and under it a field tag: a dot in the field colour and "Your field: <field>" or "Another field: <field>";
- `summary`, as the card's first line, a little larger than the rest;
- Why it's here: two short lines, **Brought** with `brought` and **Matched** with `why`;
- **Use**: `use`.

Under a More disclosure, closed at first:

- what was taken and what was changed;
- your step and the reference's step it matched, side by side;
- the reference: its title, who made it, and the workflow it serves;
- its repository and paper, when it is public, opening in a new tab;
- Explore in AstaUI: the command that opens it, `astaui show <build id>`, with a Copy button;
- Build on this: a Copy button for a request the scientist can give their agent to take the interface further along that reference's workflow ("Using <build id> from AstaUI as a reference, change this interface so that …").

Escape or a click elsewhere closes the card. Features no reference had (`from: new`) get no frame and no logo.

Add a Sources list: the references from their own field first, then those from other fields, each with its field tag and its credit, and under each the features taken from it, each as its `summary` with its `why` beneath. That puts in one place everything the interface owes to others, what each part is for and why it was brought over.

Give the interface one switch for all of it, Show sources, in its settings or menu, or as a small toggle in a corner when it has neither. It is off at first: the interface opens as the scientist's own tool, with no frame, logo, card or list drawn, and they turn the switch on when they want to see which features were borrowed and where each came from. Put the Asta logo beside the switch's label so they can find it without the frames to point at it. Remember the choice in `localStorage` under a key named for this app, so once they turn it on it stays on. Turning it on or off moves nothing else on the page.

## 9. Offer what other workflows do

The scientist described one way of working with their data. Other scientists with the same kind of data, or in the same field, worked with it in other ways, and some of what their builds do may be worth having here: an AI step, a view or chart they had not thought of, a different arrangement of views, another order to start the analysis in. Find two to four of these and offer them inside the interface. Do not build them.

1. Search again, by data and field instead of by workflow. Copy the first card to `/tmp/astaui-ideas.json`, keep the facets about the data and the field, and leave out the `workflow`. Run `astaui search "<their data, in their field>" --card /tmp/astaui-ideas.json --no-code --no-far --k 8`, with `--exclude <id>` for each build you already drew from. A `--where shape=` or `field=` filter, using the first card's words, keeps it on their data.
2. Keep the results whose workflow differs from the scientist's: a different goal, or aligned steps that are mostly the build's own. Look at their `tree.json` and screenshots as in step 5.
3. Choose the ideas that serve something the scientist is likely to do next, or to check, given their tree: a task they will reach but did not describe, or another way to do one they did. Each is a feature, an AI step, a view, an arrangement of views, or a sequence of steps. Leave out what only suits the other field.

Add each to `ideas` in `astaui-sources.json`: `{"idea": "what it adds, a few words", "kind": "feature | ai | view | arrangement | sequence", "why": "what it would let them do, one line, in their words", "workflow": "the other workflow, in general words", "from": "<build id>", "prompt": "the request that would add it"}`, and put the build's credit in `references` as in step 8, with its `same_field`.

In the interface, under the same Show sources switch, add an Ideas from other workflows panel, closed at first, opened from a button carrying the Asta logo. Each idea is a short row: what it adds and why, the workflow and build it comes from with its field tag (its logo, ringed in the field colour, opens that build's card, as in step 8), and Copy request, which copies its `prompt` so the scientist can ask their agent for it. Dismiss puts an idea away, remembered in `localStorage`. These are offers: the interface does not change until the scientist asks for one.

If the second search finds no other workflow on their data, leave the panel out and say so in one line.

## 10. Close the loop

Once the scientist has the interface:

- Tell them in one sentence where the credits are, how many come from their own field and how many from others, how many ideas from other workflows it offers, and that both appear when they turn on Show sources, which is off at first.
- Offer a walkthrough in one sentence: you can add a step-by-step guide to the interface that goes through their work in order, ringing each control and saying what to do with it. Do not add it unasked. It is a layer on top of the interface, made once it works the way they want. When they ask, follow `walkthrough.md` in this skill's folder.
- Record whether the references helped. It is part of the research this knowledge base exists for: `astaui feedback <search id> <build id> --used yes --helped yes` (or `no`), with `--note "…"` naming the features you took from it and anything the scientist said about it.
- Do not file it. The scientist has not used it yet, and it will change as they do: what you send now may not be ready for anyone else, or be what they would want shared. Say in one sentence that when it is working the way they want, they can ask you to file it into AstaUI so the next scientist can start from it. Then leave it with them.
- File it only when they ask. Then follow the `ui-to-workflow` skill, with this folder as the app and this conversation's prompts as its prompts (`--session this`).
- If it was filed before (`astaui filed` says so) and they change it, do not send the newer copy on your own either. File it again under the same id with `--replace` when they ask.
