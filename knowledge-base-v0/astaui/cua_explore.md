You are exploring one scientific web interface to work out, from using it alone, what work it supports: the goal a scientist brings to it, the phases and tasks of that work, and the features that carry it. The person who built it will read what you write and judge how accurate it is, so describe what you saw the interface do, not what an interface like it usually does.

It is already running at {URL}. You have a headless browser and nothing else: no shell, no files, no code, no description of the interface beyond what it shows you. Only open pages on {ORIGIN} (http://localhost on the same port is the same server, and worth trying if a sign-in or a cookie does not hold); links elsewhere will not load.

{ABOUT}

The browser can do what a person's hands do, so use whatever the interface expects: choose from dropdown lists, press keys and shortcuts, drag (cards, sliders, handles, a box on a chart), select text by dragging across it, hover, scroll or zoom with the wheel, click a point on a chart or canvas by its position on the screenshot, and resize the window. Dialogs that ask "are you sure?" are accepted for you. When the interface asks for a file, browser_list_files shows the test files you may give it ({DATA}). Anything it downloads is kept, and you can read it. If the page is still starting, wait a few seconds and load it again.

Work in three passes, and stop after about {ACTIONS} actions in all:

1. Survey. Visit every view and try every control once, so you know the screens and what each control changes. Read the interface's own words (titles, labels, help text, empty states) for what it is for and who it is for. Note which controls work together, such as a map and the panel that acts on what is picked in it: those are candidate features.
2. Tasks. Work out the goals a scientist would bring to it from what you saw, then carry each goal through from start to result, the way a scientist in the field would, trying the alternatives the interface offers on the way (another method, an optional step, repeating a step for a second item). If a goal cannot be reached, say where it stopped and why.
3. Features. Take each candidate feature on its own and work through what it can do: its modes, the states it can be in, how it hands a result to the rest of the interface. A feature is a widget or component together with the few steps a person takes with it, which someone else could lift into their own tool (a plate map with well exclusion, a curve fit with residuals, a draggable outline on an image). One component, or a few always used together, with two to six steps of its own. A single button is not a feature.

Take a screenshot each time the screen shows the result of a step. Each screenshot reply names its file (screens/003.jpg); cite those names as evidence.

When you are done, reply with one JSON object and nothing else, in this shape:

{
  "interface": {"title": "...", "field": "...", "stage_of_work": "...", "what_it_is_for": "one sentence"},
  "data": {"source": "built-in | loaded example | uploaded test file | none", "note": "..."},
  "tree": {
    "kind": "goal", "general": "...", "specific": "...", "children": [
      {"kind": "phase", "general": "...", "specific": "...", "children": [
        {"kind": "task", "general": "...", "specific": "...", "screens": ["screens/003.jpg"], "branch": "optional | one-of | repeat | when ... (leave out if none)", "children": [
          {"kind": "action", "label": "pressed Fit all", "screens": ["screens/004.jpg"]}
        ]}
      ]}
    ]
  },
  "features": [
    {"name": "...", "general": "its small workflow in words any field could use", "specific": "the same in this tool's words", "steps": ["...", "..."], "serves_tasks": ["task general words", "..."], "screens": ["screens/005.jpg"]}
  ],
  "screens_never_reached": ["views or states you saw named but could not reach, and why"],
  "not_done": ["anything you could not do, and why"]
}

general is said in words any field could use ("decide which items give trustworthy measurements"); specific is said in this tool's own words ("drop the bad wells on the 96-well plate"). Phases and tasks may nest as deeply as the work really does: a phase can hold sub-phases and a task sub-tasks. Keep it flat where the work is flat; do not invent levels. Actions are always leaves, labelled with what you pressed or typed. Every task needs at least one screen, from a moment when its result was visible; a task you did not see done does not go in the tree (put it in not_done).
