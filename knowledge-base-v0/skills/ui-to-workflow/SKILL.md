---
name: ui-to-workflow
description: File an interface a scientist built into the AstaUI knowledge base, with its prompts, its code and a card describing it, so other scientists can find and adapt it. Use after building a research UI with someone who agreed to share it, when someone asks to add, contribute, save or file a UI to the knowledge base, or to capture a formative-study participant's build.
---

# UI to workflow

What a scientist builds goes back into the knowledge base as a build (their prompts, their code, a screenshot) and a card (what it is, in the ontology's terms), and is sent to the knowledge base's owner. Installing these skills is how the person agreed to share what they build with the project team, so do the whole thing without stopping to ask, and tell them at the end what was sent and under what name.

## Running the tool

The command is `astaui`: on the PATH if it was installed with pip, otherwise `python3 <this skill's folder>/../../astaui_cli.py`. Check it with `astaui status`.

The status line says where the knowledge base is. When the plugin installed it, astaui files into the person's own copy (`~/.astaui/kb`), which it keeps up to date with the plugin by itself; there is nothing to set up.

Someone may have started you with the line from the console's Sharing lens, in the folder of the app they built, in whichever coding agent they use. Then the build is the app in the current folder, and its prompts are in their conversations with their agent in that folder. If the line ran `install.py … --link` or ends with "Send it to" and an address ending in `/s/` and a code, step 6 sends the build there, and astaui remembers the address, so builds filed later go there without it.

`astaui filed` says whether this folder was filed before. If it was, file it again under the same id with `--replace` and send it: the newer copy replaces the one sent before.

## 1. Name it and say who may see it, without asking

- **Name.** The name git has for them (`git config user.name`), or a name they gave in this conversation. If git has none, `Not given`. Their role and field only if they said them; leave them out otherwise.
- **Who may see it.** `team`, the people on this project. Use `public` only if they said so.
- If they said in this conversation how they want to be named, who may see it, or that this one should not be shared, do what they said; if it should not be shared, stop here.

A participant's build from the formative study, filed by the owner, is `--kind study` under a pseudonym such as `P07`; one filed through this skill is `--kind contributed`.

## 2. Gather the build

- **Prompts.** If the interface was built with a coding agent in this folder, `astaui sessions` lists the conversations it finds (Claude Code, Codex, Gemini CLI and Cursor), with their first prompt, leaving out the one filing it; `--session latest` takes the newest of the rest. If it was built in this same conversation, `--session this` takes this one. If your agent keeps its conversations somewhere astaui does not read, write the person's prompts from this conversation, or from where your agent saved them, into a file and pass it with `--prompts`. Several sessions can be combined by passing `--prompts` files. Otherwise collect the prompts into a text file with a blank line between them, typed as the person wrote them.
- **Code.** The interface's own files: the HTML, scripts and styles, a notebook, the app folder. `astaui add` skips dependencies, build output, lockfiles and large or binary files on its own.
- **A screenshot** of the interface running, if you can take one.

If the interface lives in a git repository, note its URL and commit: pass them as `--repo` and `--commit` (and `--subdir` if the interface is one folder of it). Then a big repository can later be slimmed to the files the card points at, without losing the way back to the rest.

Pick an id: lowercase words with hyphens that say what it is (`spectra-peak-picker`). Then:

```sh
astaui add <id> --title "<what it is>" --session latest --code <path> [--code <path>] \
  --screenshot shot.png --author "<their name>" \
  --kind contributed --consent team --source "prompt log"
```

`--source` is one or more of `prompt log`, `repo`, `skill file`, `Claude artifact`, `Marble app`. `--forked-from <id>` records the build it was adapted from.

## 3. Strip what must not leave

```sh
astaui lint <id>
```

Anything marked MUST GO (API keys, email addresses) has to be removed; `astaui lint <id> --strip` replaces keys, emails and home paths with placeholders. Look at everything else it lists, and read the prompts once yourself: a program cannot tell a real participant's name, a patient detail or an unpublished result from invented text. Remove those by editing the files in the build's folder, and tell the person what you removed.

## 4. Write the card

Run `astaui extract <id> --out /tmp/astaui-card.json`. It prints the instructions, the vocabulary and the build with line numbers. Write the card as they say, then `astaui card put <id> /tmp/astaui-card.json`. Fix whatever it reports and put it again until it is saved. (`astaui extract <id> --api` does the same through the Anthropic API, if the person has a key.)

The build is filed under its **workflow**, so that part of the card matters most. Name the workflow in general words. List the steps in the order the person works, each worded generally (one of the ontology's moves when it fits, so it lines up with other builds that do the same move) and then, in `here`, as this build does it, with the parts that do it. Then list what is distinctive about this case. Ask the person what is particular to their work if the prompts do not say: it is what will set their build apart from others with the same workflow.

For every part, name its code as spans: its markup, style rules, script and data, by symbol from the list the instructions print (`astaui symbols <id>` shows it too). Then read each part's slice with `astaui slice <id> <part>`: it should hold what someone needs to rebuild that one feature, and little else. If it is missing a piece, add a span; if it drags in another part's code, narrow one.

A card describes structure, not content: what a person does with the interface, what one item is, how the views work together. No names, no data values, no findings.

## 5. Make it findable

`astaui index` brings the vectors up to date; then `astaui search "<a request this should answer>"` should find it. If it does not, the card's facets are probably too specific to its field: say the structure more generally and put it again.

For a build from a big repository, once the card is saved and the slices read right, `astaui slim <id> --dry-run` shows which files the card points at; `astaui slim <id>` keeps only those and records where the rest live.

Then show the person where it was filed. `astaui workflows` lists the workflow families; find theirs, and run `astaui compare <id> <a neighbour>` against the closest one. Tell them which builds share their workflow and what is theirs alone: the steps no one else has, and the distinctive needs. If their build sits alone, say so: it is a new workflow for the knowledge base.

## 6. Send it

```sh
astaui send <id>
```

(add `--to <link>` if the line gave one; after the first build, astaui remembers it). That adds the build to a page in the drive of the knowledge base's owner. Their drive checks it and takes it into the knowledge base and its index by itself, within the hour; nothing else is needed from anyone. The link can add to that page and do nothing else, so sending needs no access to the repository. If `send` says the link opens nothing, the owner has turned it off: tell the person to ask them for the line again. If it says the build is too big, `astaui slim <id>` keeps only the files the card points at; then send it again.

Then tell the person, in two or three sentences: what was sent and its id, the name it carries and that the project team may see it, and what was taken out as private. If they want it named differently or not shared, file it again as they say and send it, or tell the owner.

If `send` says there is no link yet, nobody has given this computer the line: tell the person the build is filed here and that the knowledge base's owner can send them the line that sends it. If the knowledge base is a git clone they can push to, put the build and card on a branch named `add-<id>` and push it instead. The knowledge base's owner sees every `add-*` branch in their console (the Sharing lens) as waiting, and checks it with the `review-publish` skill before it joins; open a pull request as well if `gh` is set up. If the push is refused, they have no write access yet: say so, and that the owner can add them on GitHub.

```sh
git checkout -b add-<id>
git add knowledge-base-v0/kb/builds/<id> knowledge-base-v0/kb/cards/<id>.json
git commit -m "Add <id> to the knowledge base"
git push -u origin add-<id>
```
