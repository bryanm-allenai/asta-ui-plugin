---
name: workflow-check
description: Test how well AstaUI's computer-use agent works out the workflow of an interface from using it alone, and let the person who built it grade the result. Starts their app, runs the agent on it in a headless browser with no code and no description, then opens a page where they mark each phase, task and feature right, partly right or wrong, add what it missed, and send the grades to the AstaUI team. Use when someone asks to run a workflow check, to test the CUA or the computer-use agent on their app, or pastes the workflow-check line.
---

# Workflow check

AstaUI files public interfaces into its knowledge base by letting a computer-use agent use each one and write down its workflow: the goal, the phases and tasks, and the features that carry them. This skill runs that same agent on an interface the person built, so they can judge how accurate its account is. Only they know what their interface is really for, so their grades are the result; never grade for them, and never tell them what you think the right answer is before they have graded.

The agent must learn the interface only by using it. It gets a browser, the address and nothing else: not the code, not the README, not what you know about the app. Keep it that way. Do not pass `--about` unless the person asks to, and then use their words, not yours.

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 ~/.astaui/plugin/knowledge-base-v0/astaui_cli.py` (or `python3 <this skill's folder>/../../astaui_cli.py`). Everything below is `astaui cua …`.

It needs Node.js 18 or later (for the browser) and Claude Code signed in (the agent runs as `claude -p`, on the person's own Claude login; a run costs about what 10 to 20 minutes of Claude Code on Opus does). If either is missing, say which and how to get it, and stop.

## 1. Set up the browser, once

```sh
astaui cua setup
```

It installs Playwright and its Chromium into `~/.astaui/cua` (about 150 MB, once). Running it again does nothing if they are there.

## 2. Start the app

The app is the one in the current folder, unless the person names another. You may read its code to work out how to start it (its README, `package.json`, `pyproject.toml`, `app.py`, a notebook, a plain `index.html`): that is for you, not for the agent.

- A plain HTML app: `python3 -m http.server 8765 --bind 127.0.0.1` in its folder, so the address is `http://127.0.0.1:8765/<file>.html`.
- Anything else: start it the way its README or scripts say, in the background, and note the address it prints. Install its dependencies first if it needs them, in its own environment.

Leave it running, and check the address answers (`curl -sI <address>`) before going on. If it needs data to show anything, find out where it loads it from:

- If it reads files from its own folders, make sure they are there.
- If the person uploads files into it, ask them which test files the agent may use, or use sample files already in the folder, and put copies in a folder of their own (for example `/tmp/workflow-check-files`). Do not hand the agent anything private or under review.

## 3. Run the agent

```sh
astaui cua run --url <address> [--files <folder of test files>] [--name <short name>]
```

Run it in the background: it takes 10 to 20 minutes and prints each browser action as it goes. Tell the person it has started and roughly how long it takes. When it ends, it prints how many phases, tasks and features it found and the run's folder in `~/.astaui/checks/`. If it fails, it says why; the usual causes are a Claude login that has run out (say so, and stop) or an app that stopped answering (start it again and rerun).

`--actions N` changes how much it explores (default 60, as in the project's own runs). Keep the default unless the person asks: the point is to compare with those runs.

## 4. Have the person grade it

```sh
astaui cua review latest
```

Run it in the background too. It serves a page on 127.0.0.1 and opens it in the person's browser; give them the address it prints in case it did not open. On the page they mark each part of the tree right, partly right or wrong, add tasks and features the agent missed, say for each thing it could not do whether the interface cannot do it or the agent failed, and answer four overall questions. Their grades save as they go, into `review.json` in the run's folder.

Tell them, in a sentence or two, what to do there, and that the agent never saw their code. Then wait. Do not summarise the tree for them first or point out what you think it got wrong: that would grade it for them.

## 5. Sending, and finishing

The page has a **Send to the AstaUI team** button. Pressing it sends their grades, the tree, the brief the agent was given and the screenshots the tree cites (not their code, not the agent's transcript) to the AstaUI project's drive, through the link the line gave. Sending again sends the newer grades. If they ask you to send it instead, `astaui cua send latest` does the same.

When they are done, stop the review server and the app you started. `astaui cua summary latest` prints their grades in numbers if they ask for them; `astaui cua list` shows every run on this computer.

If they want to try again (another starting page, test files, more actions), run step 3 again: each run gets its own folder, and `astaui cua review <run folder name>` opens any of them.
