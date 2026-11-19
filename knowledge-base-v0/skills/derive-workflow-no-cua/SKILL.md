---
name: derive-workflow-no-cua
description: Work out the workflow of an interface someone built (its goal, the phases and tasks of the work, the actions a person takes and the features that carry them) from its code alone, with the coding agent reading the code twice (once for what it does, once for what a person using it would meet) and no computer-use agent, then save it as workflow.json and workflow.md and show it on a local page where the person reads it, checks each part, and corrects it. Use when someone asks for the workflow of their app without running it or without the computer-use agent, or asks for the no-CUA derive-workflow.
---

# Derive a workflow from the code

A workflow here is a tree: the goal a person brings to the interface, the phases and tasks of that work (nested as deeply as the work really is), the actions they take, and the features that carry those tasks (a component with the few steps a person takes with it, which someone else could reuse). It is the shape AstaUI files every interface under.

This skill is derive-workflow without the computer-use agent. Nothing runs the app and nothing uses it in a browser: you, the coding agent, read the code and write the same workflow the two sources would have given. You read it twice, because the two sources find different things:

- **What the code does.** Every path the code has, including ones that are hard to reach, with file and line for every part. On its own it can mistake code that exists for work a person really does.
- **What a person meets.** The computer-use agent would have found what the interface itself shows: its views, its own words, the order a person meets things in, and what they cannot reach. You find the same from the code, by walking it the way a person would use the app, from the first screen to each result.

The result is one workflow from the code, shown and checked on the same page, and sent the same way, as derive-workflow's. It costs no run and needs no Node.js, browser or app server. Say in one sentence that you are deriving it from the code alone, then go on.

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 ~/.astaui/plugin/knowledge-base-v0/astaui_cli.py` (or `python3 <this skill's folder>/../../astaui_cli.py`). Everything below is `astaui derive …`. Each workflow is a folder in `~/.astaui/workflows/`; `latest` names the newest.

The app is the one in the current folder, unless the person names another. Run every command from the app's folder, so the workflow knows where its code is. Do not start the app, install its dependencies or run `astaui derive setup` or `astaui derive run`: this skill never uses them.

## 1. Read what the code does

```sh
astaui derive brief code
```

prints what to read for and the exact JSON shape. Follow it: read the code that draws the interface and answers the person, follow each control to what it does, and write the JSON to a file such as `/tmp/workflow-code.json`, with `code` references (`path:line` or `path:first-last`, relative to the app's folder) on every part. Then keep it:

```sh
astaui derive put /tmp/workflow-code.json --from code --skill derive-workflow-no-cua
```

It checks the shape (and says what to fix if it is wrong), numbers the parts, and starts a new workflow folder. `--skill` records that this skill derived it, so a copy the person sends reaches this skill's own list on the team's testbench; keep it on every `put`.

## 2. Walk it as a person would

Now read the code again from the person's side, the way the computer-use agent would have used the running app, and correct the tree you wrote. Work in three passes, as that agent does:

1. Survey. Find the first screen a person sees (the entry page, the default route, the view the app opens on, the state it starts in) and every view they can get to from it. Read the interface's own words in the markup and the strings the code shows (titles, labels, button text, help text, empty states, error messages) for what it is for and who it is for. Note which controls work together on one screen, such as a map and the panel that acts on what is picked in it: those are candidate features.
2. Tasks. For each goal, trace what a person does from the first screen to the result: which control they use, what the handler changes, what the screen shows next. Follow the alternatives the interface offers on the way (another method, an optional step, repeating a step for a second item). A task stays in the tree only if this walk reaches it from the first screen with what the app has to work on (its built-in or example data, or a file the person uploads); move one it cannot reach to `not_done` with where it stops and why. Put views or states the interface names but a person cannot get to in `not_done` too.
3. Features. Take each candidate feature on its own and trace what it can do: its modes, the states it can be in, how it hands a result to the rest of the interface.

Then correct the JSON: name phases, tasks and actions in the interface's own words where it has them (`specific`), and label each action with the control as a person sees it ("press Fit all", not the handler's name); order phases and tasks the way a person meets them, not the way the files are laid out; keep the `code` references, pointing at the lines that draw what the person sees or answer what they do. Keep the corrected tree in the same workflow:

```sh
astaui derive put /tmp/workflow-code.json --from code --into latest --skill derive-workflow-no-cua
```

It replaces the first reading.

## 3. Show it

```sh
astaui derive show latest
```

Run it in the background. It serves a page on 127.0.0.1 and opens it in the person's browser; give them the address it prints in case it did not open. The page shows what the interface is for, the goal, the phases and tasks in order (each phase folded until they open it), what was not reached, the features (each folded to its name), a short survey and a box for the workflow they intended. Each part says it was found in the code and opens its evidence, the lines of code. Each task names the features it uses; pointing at one shows that feature, and clicking it goes to it.

The person rates each part Right, Needs a fix (with a note) or Doesn't belong (with a note if they want); a part that does not belong stays on the page, struck through, so the team sees it. They correct any words by clicking them, drag a phase or task by its grip to put it in order (into another phase too; the arrow keys on the grip move it as well), and add what is missing (a phase after any phase, a task in any phase, a feature); a part they added can be deleted again. Every change is marked where it is: reworded parts show the words they had, moved ones where they were, added ones say so. The survey asks, about the workflow as it was first written, how closely it matches the one they meant the interface to support, how much of the interface's work the phases and tasks cover, and how many of its features the list includes (each 1 to 5). Everything saves as they go, into `workflow.json` (each part keeps its first form as `orig`, and `changes` lists every change with its before and after) and `workflow.md` (with the changes, the survey answers and their own description at the end), in the workflow's folder.

Also put the outline in your reply, so they can read it without the page: `astaui derive outline latest` prints it. Keep your own words short: say it was derived from the code alone, how many phases, tasks and features it has, and what the walk in step 2 changed (tasks moved to not reached, parts renamed in the interface's words, a new order). Then let them check it.

## 4. Send it

The workflow, as the person checked it, goes to the AstaUI team: every part, each rating (right, needs a fix, doesn't belong) with its note, every change with its before and after, the workflow as it was derived (`derived.json`), their survey answers and their own description. None of the app's code goes, and there are no screenshots. It travels the way a filed build does, as one row added to the team's drive page through the Add only link the line carried (`astaui setup --link` kept it on this computer).

When you show the page, tell the person that once they have checked it they can press **Send to the AstaUI team** at the top; it asks them to confirm, says what is sent and what they have not done yet (rated, answered the survey, described their workflow), and asks for the name the team sees (the one git has, unless they change it). Nothing goes until they press Send there. Pressing it again later sends the newer copy, which replaces the first. If they ask you to send it instead, run

```sh
astaui derive send latest [--author "<the name they give>"]
```

and say what it printed: how many parts they had rated, how many need a fix or do not belong, and where it went. Send only when they have said so, by the button or in words. If it says there is no link, the line they pasted had one: run `astaui setup --link <that link>` and send again. It goes to the team's testbench, not into the knowledge base: sending a workflow files nothing.

## 5. Afterwards

When they are done, `astaui derive outline latest` shows their corrections and ends with what they changed, their survey answers and their own description; the parts they marked as needing a fix or not belonging carry their notes. If they ask you to fix those, edit the workflow JSON (a copy of `workflow.json`) and keep it with `astaui derive put <file> --from code --into latest --skill derive-workflow-no-cua`, then reload the page.

If they want the workflow in their project, `astaui derive export latest --to <folder or path.json>` writes `workflow.json` and `workflow.md` there, marks and notes included. Do not write into their project without being asked.

Stop the page server when they are finished. `astaui derive list` shows every workflow on this computer, and `astaui derive show <name>` opens any of them.
