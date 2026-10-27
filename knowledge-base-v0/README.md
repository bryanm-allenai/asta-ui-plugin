# AstaUI

Scientists now build their own research interfaces by prompting coding agents: a transcript coder, a plate-reader QC workbench, a screen for telescope frames. AstaUI is a knowledge base of those interfaces, packaged as skills for Claude Code. When a scientist asks their agent for an interface, the agent finds builds with the same structure, from their field and from others, and adapts the closest one to their data. What they build is filed and sent back, so the next scientist can start from it.

This repository is the plugin: the skills, the `astaui` tool they run, and a set of invented example builds to search. The knowledge base the project shares, with the builds scientists have sent in, lives with the project's owner.

## Installing

You need Claude Code and Python 3.9 or later. Nothing else is installed.

```sh
claude plugin marketplace add bryanm-allenai/asta-ui-plugin
claude plugin install asta-ui@asta-ui
```

If someone on the project sent you a line to paste, use that instead. It installs the plugin, files the app in the folder you run it in, and sends it to the project's knowledge base. After the first time, an interface you ask Claude Code to build for your research is filed and sent the same way, and filing an app again sends its newer copy.

## What filing sends

A build is your prompts to Claude Code, the interface's code and a screenshot, with a card that describes what the interface does in the knowledge base's shared words. It is filed under the name git has for you and marked for the project team. Before anything leaves your computer, keys, email addresses and paths that name your home folder are replaced with placeholders, and the agent reads the prompts for anything else private. It tells you what it sent. If you would rather be named differently, or a build should not be shared, say so in the conversation.

A copy of everything filed stays on your computer, in `~/.astaui/kb`.

## The skills

`workflow-to-ui` builds an interface for your work, starting from the builds that share its structure. `ui-to-workflow` files an interface you built. `ui-explorer` draws the knowledge base as a map and shows any build. `review-publish` is the check a build passes before it joins a shared knowledge base.

The tool behind them is `astaui` (`python3 knowledge-base-v0/astaui_cli.py`, or `pip install ./knowledge-base-v0`). `astaui search "<what you need>"` finds builds, `astaui show <id>` shows one, and `astaui --help` lists the rest.
