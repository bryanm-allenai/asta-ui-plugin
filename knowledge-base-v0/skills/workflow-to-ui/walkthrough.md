# Add a walkthrough to an interface

An interface for a scientist's work is easier to pick up when it shows the work in order: what comes out at the end, the parts the work moves through, and in each part the control to use and what to do with it. This adds that walkthrough on top of an interface that already works, without changing how the interface works. It applies to any interface for scientific work, whether or not it was built with the AstaUI knowledge base.

A walkthrough is two things:

- `walkthrough.json`: the content, written by you for this interface.
- `astaui-walkthrough.js`: the player, the same file for every interface (`walkthrough/player.js` beside this file). It shows a Walkthrough button in the bottom-left corner. The first time the interface opens it offers an overview: the goal and the parts. Then it goes step by step, ringing each step's control and putting a short card beside it, with Back, Next and a bar that shows which part of the work you are in. The person can keep using the interface while it is open.

## 1. Learn the interface as its user would

Read the interface's code to find its controls, views and the order the work goes in. Then open it (headless Chromium is fine) and use it with its example data: load something, do the main action once, and see what comes out. Write down:

- the goal: what the scientist has at the end (a coded data set, a table of labelled calls, a list of hits, a figure);
- the parts the work moves through, in order: usually bringing data in, a part or two of the real work, checking, and handing the result on;
- in each part, the one to three controls a person uses, and what each is for at that point in the work.

If the folder holds a record of what the interface is for (an `astaui-tree.json`, `astaui-sources.json` or README), read it, but describe what the interface does, not what was planned: every step must be something a person can do in it now.

## 2. Write the walkthrough

```json
{"title": "How to <the work>, in a few words",
 "goal": "What the scientist has at the end, one sentence",
 "phases": [
   {"name": "A part of the work, 2 to 4 words",
    "say": "What happens in this part, one short line",
    "steps": [
      {"target": "CSS selector of one control",
       "title": "Up to 6 words",
       "say": "What this control is and why it comes at this point in the work, up to 30 words",
       "do": "The one action to try, up to 16 words",
       "prep": ["selectors to click first, in order, so the target is on screen"],
       "next_on": "click"}]}],
 "end": "What leaves at the end and how, one sentence"}
```

- Three to six phases and six to twelve steps in all. Order them as the work goes, not as the screen is laid out.
- Each step points at one control the person uses: a button, a field, a list, a canvas they draw on. Never a whole panel or the page.
- Target with a selector that finds exactly one visible element and will keep finding it: an `id`, an `aria-label`, a `data-` attribute, or a class the code gives only that control. If none fits, add a `data-walkthrough="<name>"` attribute to the element in the interface's markup and target `[data-walkthrough="<name>"]`. Adding that attribute is the only change you make to the interface. When you cannot edit the interface, use what is there.
- When a control only appears after something else (a tab, an open dialog, a selected row), list the clicks that bring it on screen in `prep`. The player and the checker make them first.
- `do` is optional: give one when there is an action worth trying here. `next_on` (`click`, `input` or `change`) moves on by itself when the person does it; leave it out when they should look first.
- Write in the scientist's words and their field's: their item, their data, their categories. Say what a control is for in the work, not what it looks like ("Box each call so its times and frequencies are recorded", not "Drag on the canvas"). No praise of the interface, no "simply", no "powerful".

## 3. Check it

Run the checker on the interface and the walkthrough:

```sh
node <this skill's folder>/walkthrough/check.mjs app/index.html walkthrough.json --shots tmp/walkthrough-shots
```

It opens the page, makes each step's `prep` clicks, and says for each step whether its target is there, shown and the only match, and flags words over the limits. Open a few of the pictures in the shots folder to see that each boxed control is the one the step talks about. Fix every line marked FIX and run it again until none is left. If Playwright is not there, open the page in any browser with the player and go through every step yourself.

## 4. Put it in the interface

Copy `walkthrough/player.js` into the interface's folder as `astaui-walkthrough.js`. In `index.html`, before `</body>`, add the walkthrough and the player:

```html
<script type="application/json" id="astaui-walkthrough">…the contents of walkthrough.json…</script>
<script src="astaui-walkthrough.js"></script>
```

Keep `walkthrough.json` in the folder too. Open the interface once more, press Walkthrough and go through it from the start.

(The test bench makes walkthroughs for apps it compares and puts them in itself: there, write `walkthrough.json` where you are told and leave step 4 to it.)
