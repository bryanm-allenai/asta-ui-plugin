---
name: derive-workflow
description: Work out the workflow of an interface someone built (its goal, the phases and tasks of the work, the actions a person takes and the features that carry them) from its code, from AstaUI's computer-use agent using the running app, or both merged, then save it as workflow.json and workflow.md and show it on a local page where the person reads it, checks each part, and corrects it. Use when someone asks for the workflow of their app, to derive, extract or map the workflow or task tree of an interface, to see what work their UI supports, or pastes the derive-workflow line.
---

# Derive a workflow

A workflow here is a tree: the goal a person brings to the interface, the phases and tasks of that work (nested as deeply as the work really is), the actions they take, and the features that carry those tasks (a component with the few steps a person takes with it, which someone else could reuse). It is the shape AstaUI files every interface under.

There are two ways to work it out, and they find different things:

- **From the code.** You read the app's files and write the tree, citing file and line for every part. Fast and cheap, and it finds every path the code has, including ones that are hard to reach. It can mistake code that exists for work a person really does.
- **From using it.** AstaUI's computer-use agent (Claude with a headless browser and nothing else) uses the running app and writes the tree, citing the screenshots it took. It never sees the code, so it finds what the interface itself shows a person. It costs a run (about 2 to 20 minutes and $1 to $5 on the person's own Claude login) and can miss what it did not reach.

**Default to both**, merged, so each part says whether it was seen in use, found in the code, or both: that is the easiest version for the person to check. Use the code alone when the app cannot be started here, when Node.js or Claude Code is missing, or when the person asks for something quick. Use the interface alone only when the person asks for it. Say which you are doing and why in one sentence, then go on; do not ask unless the person's request leaves it open and the choice matters to them.

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 ~/.astaui/plugin/knowledge-base-v0/astaui_cli.py` (or `python3 <this skill's folder>/../../astaui_cli.py`). Everything below is `astaui derive …`. Each workflow is a folder in `~/.astaui/workflows/`; `latest` names the newest.

The app is the one in the current folder, unless the person names another. Run every command from the app's folder, so the workflow knows where its code is.

## 1. From the code

```sh
astaui derive brief code
```

prints what to read for and the exact JSON shape. Follow it: read the code that draws the interface and answers the person, follow each control to what it does, and write the JSON to a file such as `/tmp/workflow-code.json`, with `code` references (`path:line` or `path:first-last`, relative to the app's folder) on every part. Then keep it:

```sh
astaui derive put /tmp/workflow-code.json --from code
```

It checks the shape (and says what to fix if it is wrong), numbers the parts, and starts a new workflow folder. Do this before the run in step 2, while the code is fresh in mind, and do not tell the computer-use agent anything you learned from it.

## 2. From using it

Once per computer, set up the agent's browser (Playwright and its Chromium in `~/.astaui/cua`, about 150 MB; running it again does nothing):

```sh
astaui derive setup
```

It needs Node.js 18 or later and Claude Code signed in. If either is missing, say which and how to get it, and fall back to the code alone.

Start the app. You may read its code to work out how (its README, `package.json`, `pyproject.toml`, `app.py`, a plain `index.html`): that is for you, not for the agent.

- A plain HTML app: `python3 -m http.server 8765 --bind 127.0.0.1` in its folder, so the address is `http://127.0.0.1:8765/<file>.html`.
- Anything else: start it the way its README or scripts say, in the background, and note the address it prints. Install its dependencies first if it needs them, in its own environment.

Check the address answers (`curl -sI <address>`). If the app needs data to show anything: if it reads files from its own folders, make sure they are there; if the person uploads files into it, ask which test files the agent may use (or use sample files already in the folder), and put copies in a folder of their own, such as `/tmp/derive-workflow-files`. Never hand the agent anything private or under review.

```sh
astaui derive run --url <address> --into latest [--files <folder of test files>]
```

`--into latest` adds it to the workflow step 1 started; leave it out when there was no step 1. Run it in the background: it prints each browser action as it goes. Tell the person it has started and roughly how long it takes. If it fails, it says why; the usual causes are a Claude login that has run out (say so, and go on with the code alone) or an app that stopped answering (start it again and rerun).

The agent gets the address and nothing else. Do not pass `--about` unless the person asks to, and then use their words. `--actions N` changes how much it explores (default 60).

## 3. Merge the two

When both are in, the tool says so.

```sh
astaui derive brief merge latest
```

prints how to merge and where the two files are. Read both, write the merged tree to a file such as `/tmp/workflow-both.json`, and keep it:

```sh
astaui derive put /tmp/workflow-both.json --from both --into latest
```

## 4. Show it

```sh
astaui derive show latest
```

Run it in the background. It serves a page on 127.0.0.1 and opens it in the person's browser; give them the address it prints in case it did not open. The page shows what the interface is for, the goal, the phases and tasks in order, the features, and what was not reached. Each part says where it was found and opens its evidence: the screenshot the agent took, or the lines of code. The person can correct any words by clicking them, mark each part right or needing a fix (with a note), remove parts and add missing ones (a phase after any phase, a task in any phase, a feature), move phases, tasks and features up and down, and fold phases away to see the shape of the whole. Everything saves as they go, into `workflow.json` and `workflow.md` in the workflow's folder.

Also put the outline in your reply, so they can read it without the page: `astaui derive outline latest` prints it. Keep your own words short: say how it was made (code, use, or both), how many phases, tasks and features it has, and anything the two sources disagreed on (the parts with `differs`). Then let them check it.

## 5. Send it

The workflow, as the person checked it, goes to the AstaUI team: every part, each mark (right or needs a fix) with its note, the words they corrected, the parts they added, moved or removed, and the screenshots the parts rest on. None of the app's code goes. It travels the way a filed build does, as one row added to the team's drive page through the Add only link the line carried (`astaui setup --link` kept it on this computer).

When you show the page, tell the person that once they have checked it they can press **Send to the AstaUI team** at the top; it asks for the name the team sees (the one git has, unless they change it) and says what is sent. Pressing it again later sends the newer copy, which replaces the first. If they ask you to send it instead, run

```sh
astaui derive send latest [--author "<the name they give>"]
```

and say what it printed: how many parts they had checked, how many need a fix, and where it went. Send only when they have said so, by the button or in words. If it says there is no link, the line they pasted had one: run `astaui setup --link <that link>` and send again. If the app in this folder was filed into AstaUI before (`astaui filed`), the workflow says which build it describes, and the team keeps the two together.

## 6. Afterwards

When they are done, `astaui derive outline latest` shows their corrections, and the parts they marked as needing a fix carry their notes. If they ask you to fix those, edit the workflow JSON (a copy of `workflow.json`) and keep it with `astaui derive put <file> --from both --into latest` (or `--from code` / `--from ui` for a single source), then reload the page.

If they want the workflow in their project, `astaui derive export latest --to <folder or path.json>` writes `workflow.json` and `workflow.md` there, marks and notes included. Do not write into their project without being asked.

If they later file the app with the ui-to-workflow skill, `astaui add` run from this folder keeps the newest checked workflow in the build (`derived/`), so sending and publishing the build carry their marks with it.

Stop the page server and any app you started when they are finished. `astaui derive list` shows every workflow on this computer, and `astaui derive show <name>` opens any of them.
