# AstaUI

Scientists now build their own research interfaces by prompting coding agents: a transcript coder, a plate-reader QC workbench, a screen for telescope frames. AstaUI is a knowledge base of those interfaces, packaged as skills for Claude Code. When a scientist asks their agent for an interface, the agent finds builds with the same structure, from their field and from others, and adapts the closest one to their data. When what they build works the way they want, they can file it and send it back, so the next scientist can start from it.

This repository is the plugin: the skills, the `astaui` tool they run, and the builds anyone may search. Most of those are open-source interfaces for science found on GitHub, each run by a computer-use agent that recorded its workflow, its features and screenshots of it in use; a few are invented examples. The plugin holds what each one is and how it works, but not its code: when a skill opens a build's code, `astaui` downloads those files from the build's repository at the commit it was run at and checks each one against its fingerprint. The knowledge base the project shares, with the builds scientists have sent in, lives with the project's owner.

## Installing

It works with any coding agent that reads skills: Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, OpenCode and others. You need Python 3.9 or later and nothing else.

If someone on the project sent you a line, paste it into your coding agent in the folder of an app you built. The agent installs AstaUI, files the app and sends it to the project's knowledge base. After that, an interface your agent builds for your research is not filed on its own: use it first, and when it works the way you want, ask your agent to file it. Filing an app again sends its newer copy.

To install it yourself, in a terminal:

```sh
curl -fsSL https://raw.githubusercontent.com/bryanm-allenai/asta-ui-plugin/main/install.py | python3 -
```

It downloads AstaUI into `~/.astaui/plugin` and puts the skills in `~/.agents/skills`, where most agents look, with a link from Claude Code's `~/.claude/skills`. Running it again brings it up to date. On Claude Code you can install it as a plugin instead:

```sh
claude plugin marketplace add bryanm-allenai/asta-ui-plugin
claude plugin install asta-ui@asta-ui
```

## What filing sends

A build is your prompts to Claude Code, the interface's code and a screenshot, with a card that describes what the interface does in the knowledge base's shared words. It is filed under the name git has for you and marked for the project team. Before anything leaves your computer, keys, email addresses and paths that name your home folder are replaced with placeholders, and the agent reads the prompts for anything else private. It tells you what it sent. If you would rather be named differently, or a build should not be shared, say so in the conversation.

A copy of everything filed stays on your computer, in `~/.astaui/kb`.

## Seeing the workflow of your own app

`derive-workflow` works out the workflow of an app you built: its goal, the phases and tasks of the work, the actions a person takes and the features that carry them, in the same shape as every build here. Ask your coding agent for it in your app's folder. It reads your code, and, if the app can run, lets a computer-use agent (Claude with a headless browser and nothing else) use it for a few minutes without seeing the code, then merges the two. A page opens where each part says where it was found and shows its evidence, the screenshot or the lines of code, and you can correct the words, mark each part right or needing a fix, remove parts and add what is missing.

`derive-workflow-no-cua` does the same from the code alone: your coding agent reads it twice, once for what it does and once walking it the way a person using it would meet it, and nothing runs the app. It needs no Node.js or browser and costs no computer-use run.

Reading the code needs nothing extra. Using the app needs Node.js 18 or later, for the browser, and Claude Code signed in: the computer-use agent runs on your own Claude login, usually 2 to 20 minutes and $1 to $5 a run. Nothing is sent anywhere. Every workflow stays on your computer in `~/.astaui/workflows`, as `workflow.json` and `workflow.md`; `astaui derive --help` lists the commands.

## The skills

`workflow-to-ui` builds an interface for your work, starting from the builds that share its structure. It also looks at how other scientists do the same kind of work and offers you the changes to your workflow that would let you find or check something you cannot now; the ones you do not take stay in the interface as other ways to work. Each idea it borrows is credited in the interface with how well vetted its source is: GitHub stars for a public repository, or how often AstaUI users fetched and approved it (`astaui stats <id>`). `workflow-discovery` first looks at how other scientists do the same kind of work, offers you two to four changes to your workflow with what each would let you do, and builds the interface for the way you choose. `workflow-explorer` builds a place to explore your interface before it is built: your workflow on the left, which you can edit, and on the right small working designs and other builds' features for each part, with your picks adding up to a request for `workflow-to-ui`. `ui-to-workflow` files an interface you built. `ui-explorer` draws the knowledge base as a map and shows any build. `review-publish` is the check a build passes before it joins a shared knowledge base. `derive-workflow` works out the workflow of an interface you built and shows it to you to check, and `derive-workflow-no-cua` does it from the code alone (see above).

The tool behind them is `astaui` (`python3 ~/.astaui/plugin/knowledge-base-v0/astaui_cli.py` after the installer, or `pip install ./knowledge-base-v0`). `astaui sessions` finds your conversations with Claude Code, Codex, Gemini CLI and Cursor in a folder, which is where a build's prompts come from. `astaui search "<what you need>"` finds builds, `astaui show <id>` shows one, and `astaui --help` lists the rest.
