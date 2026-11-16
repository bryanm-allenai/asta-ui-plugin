---
name: workflow-explorer
description: Before building a scientist's interface, build them a place to explore it. Use when a scientist asks for a UI, tool, dashboard, viewer, workbench or app for their research and wants to see the options before committing, asks what their interface could look like, or asks to compare ways of building it. Infer their workflow as a tree of phases and tasks, turn each part you are unsure of into a choice between concrete ways that part could go, find the features other scientists' builds in the AstaUI knowledge base use for each task, draw two to four small working designs for each task, and build one explorer app: the workflow on the left, which they can select, edit, reorder and switch between choices, and on the right the designs and the knowledge base's features for whatever they selected, re-matched as they edit. Picks add up to a build request they can hand to workflow-to-ui.
---

# Workflow Explorer

A scientist has asked for an interface, and there are many interfaces it could be. One agent's best guess hides the others: the way of working they had not thought of, the view another field uses for the same step, the second design that would have suited them better. Instead of building one interface, build them a place to look at several, organised by their own workflow, so they can see what each part of their work could look like, change the workflow itself and watch the options change with it, and leave with an interface they chose.

The explorer is the thing you build. It is one app, made for this scientist, with their data or an example of it, in their words. On the left is their workflow as a tree they can edit. On the right, for the part they selected, are a few working designs you drew for it and the features other scientists' builds in the AstaUI knowledge base use for it. Every pick they make goes into a short plan, and the plan becomes a request they can give their agent to build the real interface.

## Running the tool

The knowledge base's command is `astaui`. Use it if it is on the PATH. Otherwise run `python3 <this skill's folder>/../../astaui_cli.py`; this skill's folder is the base directory you were given when the skill loaded. Below, `astaui` means whichever works. Check it once with `astaui status`; its first line names the knowledge base folder, called `<kb>` below.

Nothing in these steps sends the scientist's data anywhere: describing the request is your own work, and the search runs on this machine.

## 1. Understand the request

Read what they asked for. If their data is in the working folder, look at it as a person would before building: file names, a header row, a few lines, the size. Note what one item is (a transcript passage, a well, a frame, a record) and what they will do to it. If there is no data, make a small example set in their field's terms, about a dozen items, realistic enough that a design can be judged on it, and say in the explorer that it is made up.

## 2. Infer the workflow, and turn what is unsure into choices

Write the work down as a tree in the knowledge base's own shape: one `goal` (what they want to come out of the work), the `phase`s it moves through in order, and under each phase the `task`s a person does there. Give each node a `general` line in words any field would use and a `specific` line in theirs. Include the parts an interface would need even when they did not mention them: how items come in, how a decision is recorded, what leaves at the end.

Score each node from 0 to 1 for how sure you are, with a few words on why. A node under 0.7 is one you are guessing: they did not say it, or what they said could go two ways that would make different interfaces.

Do not ask about the unsure parts. Make each one a **choice** in the tree instead: two to four concrete ways that part of their work could go, in their words, each with its own subtree (the tasks that way of working has), the likeliest first and marked as the default. Choices are what the explorer is for, so look for them beyond the unsure nodes too. Find at least three in the whole tree, and make sure at least one of them changes the shape of the work, not just a detail:

| Kind of choice | Example |
|---|---|
| One at a time or many at once | Code each passage in turn, or see all passages of a code side by side |
| Order | Clean the data first and then explore, or explore first and clean what turns up |
| Who decides | They label every item, or a model suggests and they accept or correct |
| What leaves at the end | A table of results, a figure for a paper, or files for the next tool |
| A step they may not need | Agreement between two coders, kept or left out |

Save it as JSON to `/tmp/astaui-tree.json`: each node with `id` (short, stable, such as `p2-t1`), `kind`, `general`, `specific`, `confidence`, `why` and `children`; a choice is a node with `kind: "choice"`, a `question` in their words, and `options`, each with `id`, `label`, `why` (what this way is good for, one line), `default` (true on one) and `children`.

## 3. Describe it, and search by workflow

Run `astaui describe "<their request, in their words>"`, adding `--context <file>` with a few lines about their data if you looked at it. Write the query card it asks for as JSON to `/tmp/astaui-query.json`, taking the `workflow` from the tree with every choice at its default. Fill only the facets the request supports.

```sh
astaui search "<their request>" --card /tmp/astaui-query.json --no-code --json --k 8
```

Keep the search id it logs. Then widen the search so that every way the work could go has builds behind it. For each choice option that is not the default, and for each phase, search again with what is particular to it:

```sh
astaui search "<the option or phase, in general words>" --no-code --json --k 5 --no-far
```

adding `--where shape=…` with the first card's data shape when the results drift off their data. Keep the far match from the first search: a build from another field with the same structure is often where the most surprising design comes from.

## 4. Gather the feature pool

From the builds those searches found (usually 8 to 20), read each `<kb>/builds/<id>/tree.json`. Its `features` list names each feature with a `general` description, the `specific` way the build does it, its `steps`, the tasks it serves (`serves_tasks`) and `screens` in the same folder. Its `tree` has the same shape as yours.

Keep the features that serve some task in your tree, in any option of any choice: between 25 and 80 in all. For each, record which of your task ids you think it serves (`serves`, possibly several, possibly none when you keep it as a general idea), and copy its best screen into the app as `app/explorer/screens/<build>-<file>`, so the explorer works opened straight from the file. A feature without a screen keeps the build's `screenshot.webp`.

Take each build's credit from its `<kb>/builds/<id>/build.json` and from nowhere else:

| The build's `provenance.consent` | `by` | `link` and `paper` |
|---|---|---|
| `public` | `author.name` | `source.repo`, and `provenance.found.paper` if it has one |
| anything else | the author's role and field ("a postdoc in microbiology"), never `author.name` | none |

and mark it `same_field: true` when its field is the scientist's own or a branch of it, judged by field, not by data shape.

## 5. Draw the designs

For each task in the tree, in every option of every choice, draw **two to four designs**: different ways an interface could serve that task. They must differ in how the person works, not in colour or spacing: one item at a time against a grid of many; a keyboard key per decision against a click; a table against a chart; the model's suggestion shown first against hidden until asked. Where several tasks share one screen (a phase that is really one view), draw the designs per phase instead, and say so.

Each design is a small working piece of interface, about the size of a card (up to 520 by 360 px), that the scientist can click, type into and try on their own or example data. It is a sketch of the one task, not the whole app: no header, no navigation. Keep each in plain HTML, CSS and a little script, scoped so designs never affect each other or the explorer (a shadow root, or an `<iframe srcdoc>`).

For each design, write:

- `name`: a few words in their terms, such as "One passage, codes as keys".
- `good_for`: when this design is the right one, one line.
- `costs`: what it gives up, one line. Every design gives something up; say what.
- `from`: the feature ids it draws on, or `new`. A design drawn from a feature is credited to that feature's build, as in step 4.

Mark one design per task as your recommendation (`pick: true`), with a line on why, given their tree.

## 6. Build the explorer

Write the explorer into `app/index.html`, with everything it needs beside it in `app/` and its data both in `app/explorer.json` and inside the page in `<script type="application/json" id="explorer-data">`, so it works opened from the file with no server. Its data holds the request, the tree (step 2), the pool (step 4), the designs (step 5), the references and the search id.

**Layout.** Two panes. On the left, a third of the width and no less than 280 px, the workflow: the goal at the top, then each phase with its tasks under it, indented. On the right, whatever is selected. At phone width, the tree becomes a list you open from a button, and the right pane fills the screen.

**The tree.** Each node shows its words in their terms, with its `general` line on hover. A node that came from a guess carries a small "guessed" mark until the scientist touches it. A choice shows its question and its options as a small segmented control; switching options swaps in that option's subtree at once, and the right pane follows. Every node can be:

- selected, with a click or the arrow keys;
- renamed in place (double-click or Enter), its `specific` line edited the same way;
- moved up or down among its siblings (drag, or Alt with an arrow key);
- removed, with Undo;
- given a new task under a phase, or a new phase under the goal.

**The right pane for a task** has two parts, one above the other.

1. **Ways to build this step**: its designs side by side (stacked at narrow widths), each live, with its name, good for and costs, a credit chip when it came from a build, and a Use this button. Your recommendation is chosen to begin with and says why. Picking another one is remembered.
2. **From other scientists**: the features from the pool that match this task, best first, each with its screen, its `general` description, the build and its field, and an Add to my plan toggle. Clicking the screen opens it large with the feature's steps.

**The right pane for a phase** shows each of its tasks as a row with the design picked for it, as a small preview, and the features added. **For the goal**, the same for the whole tree: this is the plan.

**Editing changes the options.** The feature list is not fixed to the tree you wrote. When the scientist renames a task, adds one or moves one to another phase, its features are matched again in the page, from the pool, by these rules:

- Words: lowercase, letters and digits, three letters or more, leaving out common words (the, and, for, with, each, from, into, that, this, their) and trimming a final `s`, `es`, `ed` or `ing`.
- A feature's text is its `general`, `specific`, `serves_tasks` and `steps`; a task's text is its `general` and `specific`, and its phase's `general`.
- Score is the sum, over the words both share, of each word's rarity in the pool (`log(1 + pool size / features with the word)`), divided by the square root of the feature's word count. A feature you linked to this task in `serves` adds the highest score in the pool, so your own judgment leads until the words change.
- Show the best eight scoring above a fifth of the best; say plainly when nothing matches ("No build in this pool does this step") and offer Copy request, which copies a line asking their agent to search the knowledge base for it: `Search AstaUI for builds that <task, in general words>, and add them to this explorer.`

A new task starts with no designs of its own. Show the best-matching design from any other task, if one scores well, under "From another step", and the same Copy request line otherwise. Removing a task drops its picks from the plan; Undo brings them back.

**Credits.** A design or feature from a build carries the Asta logo on a small round chip ringed in Asta green (`#0fcb8c`) when the build is from the scientist's own field, or Asta blue (`#2a88ef`) when it is from another, with "Your field: <field>" or "Another field: <field>" beside it in words, so colour is never the only sign. Use this SVG for the logo exactly:

```html
<svg viewBox="0 0 180 180" width="16" height="16" aria-hidden="true"><path fill="#0fcb8c" d="M72,70.25h-36v-34.25h28.98c3.87,0,7.02-3.15,7.02-7.02V0h34.25v36c0,18.92-15.33,34.25-34.25,34.25ZM36,73.75H0v34.25h28.98c3.87,0,7.02,3.15,7.02,7.02v28.98h34.25v-36c0-18.92-15.33-34.25-34.25-34.25ZM151.02,72c-3.87,0-7.02-3.15-7.02-7.02v-28.98h-34.25v36c0,18.92,15.33,34.25,34.25,34.25h36v-34.25h-28.98ZM73.75,144v36h34.25v-28.98c0-3.87,3.15-7.02,7.02-7.02h28.98v-34.25h-36c-18.92,0-34.25,15.33-34.25,34.25Z"/></svg>
```

Clicking the chip opens a small card: the build's title, who made it and its field, the workflow it serves, its repository and paper when public, and `astaui show <build id>` with a Copy button.

**State.** Every edit, choice and pick is kept in `localStorage` under a key named for this app, and the explorer opens where the scientist left it. A Start over button, with a confirmation, goes back to the tree you wrote. A Changes list (a small count by the tree's title that opens a list) shows every edit they made to your tree, in plain words, each with its own Undo.

## 7. The plan, and handing it on

At the foot of the right pane, always in reach, sits the plan: how many steps have a design picked and how many features are added, and Copy build request. That copies a request in plain words that their agent can build from with the `workflow-to-ui` skill:

```
Build the interface I planned in the AstaUI explorer. My workflow, as I settled it: <goal; phases; tasks, in order, with each choice as I chose it>. For each step, the design I picked: <task: design name, what it does, good for>. Features I want from other builds: <feature, build id>. Changes I made to the workflow: <list>. The full plan is in explorer-plan.json below.
<the plan as JSON>
```

Download plan saves the same JSON as `explorer-plan.json`.

## 8. Test it, and hand it over

Open the explorer in a browser and use it as the scientist would. Check that:

- every task in every option of every choice has at least two designs, or says why it has one;
- every design works on the data shown: a click does what it says;
- switching each choice swaps the subtree and the right pane follows;
- renaming a task to something else changes its feature list, and a made-up task with no match says so;
- the plan and Copy build request reflect every pick, and a reload keeps them;
- the layout holds at phone width.

Then tell them in a few sentences: what the explorer covers (how many choices, how many designs, how many builds the features come from, how many from their own field), which part of their workflow you were least sure of and where to look first, and that when they have picked, Copy build request hands the plan to their agent. Offer to build it from their plan straight away, with `workflow-to-ui`, when they say so. Do not build the interface itself unasked.

Record whether the references helped: `astaui feedback <search id> <build id> --used yes --helped yes` (or `no`) for each build whose features you used, with `--note` naming them.
