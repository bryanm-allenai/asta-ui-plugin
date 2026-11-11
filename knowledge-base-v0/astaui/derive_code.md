Work out, from the code of the app in this folder, what work its interface supports: the goal a person brings to it, the phases and tasks of that work, the actions they take, and the features that carry them. The person who built it will read what you write and check it against what they built, so describe what the code makes the interface do, not what an interface like it usually does, and not what a comment, README or commit message says it will do one day.

Read the code that draws the interface and answers the person: the entry page or app file first, then the components, handlers and the state they change. Follow each control to what it does. Skip vendored libraries, build output, lock files, tests and data files. If the code holds several apps, ask the person which one.

- A task is something a person does to get a result, carried by controls the code really wires up. A control with no handler, a view that is never shown, or a branch no control reaches is not a task: put it in not_done with where it is.
- A feature is a widget or component together with the few steps a person takes with it, which someone else could lift into their own tool (a plate map with well exclusion, a curve fit with residuals, a draggable outline on an image). One component, or a few always used together, with two to six steps of its own. A single button is not a feature.
- Cite the code for every goal, phase, task, action and feature as "path:line" or "path:first-last", with the path relative to the app's folder, pointing at the lines that do it (the handler, the component, the view), not at the line that merely names it.

Write one JSON object and nothing else, in this shape, to a file (for example /tmp/workflow-code.json):

{
  "interface": {"title": "...", "field": "...", "stage_of_work": "...", "what_it_is_for": "one sentence"},
  "data": {"source": "built-in | loaded example | uploaded by the person | fetched | none", "note": "what data it works on, and where it comes from in the code"},
  "tree": {
    "kind": "goal", "general": "...", "specific": "...", "code": ["app.js:1-40"], "children": [
      {"kind": "phase", "general": "...", "specific": "...", "code": ["..."], "children": [
        {"kind": "task", "general": "...", "specific": "...", "code": ["app.js:212-260"], "branch": "optional | one-of | repeat | when ... (leave out if none)", "children": [
          {"kind": "action", "label": "press Fit all", "code": ["app.js:230"]}
        ]}
      ]}
    ]
  },
  "features": [
    {"name": "...", "general": "its small workflow in words any field could use", "specific": "the same in this tool's words", "steps": ["...", "..."], "serves_tasks": ["task general words", "..."], "code": ["components/PlateMap.tsx:1-180"]}
  ],
  "not_done": ["what the code names or starts but a person cannot reach, and where"]
}

general is said in words any field could use ("decide which items give trustworthy measurements"); specific is said in this tool's own words ("drop the bad wells on the 96-well plate"). Phases and tasks may nest as deeply as the work really does: a phase can hold sub-phases and a task sub-tasks. Keep it flat where the work is flat; do not invent levels. Actions are always leaves, labelled with the control a person uses and what they do with it ("type a sample name", "drag the threshold line"). Order phases and tasks the way a person meets them. Leave out names of people, email addresses, keys and data values.
