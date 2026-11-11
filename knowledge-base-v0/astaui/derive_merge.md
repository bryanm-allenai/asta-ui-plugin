There are two accounts of the same app's workflow, in the same shape:

- {UI}: written by a computer-use agent that used the running app in a browser and never saw the code. Its evidence is "screens": the screenshots it took.
- {CODE}: written from the code. Its evidence is "code": file and line.

Merge them into one workflow, in the same shape, and write it as one JSON object to a file (for example /tmp/workflow-both.json).

- Line up the parts that are the same work, even when the words differ, and keep one part for each, with both sources' evidence ("screens" and "code") and "from": ["ui", "code"]. Keep the clearer words; prefer the words of use for what a person does and sees.
- A part only one source has stays, with "from": ["ui"] or "from": ["code"]. A task in the code that the agent never reached is usually real; a task the agent did that the code does not seem to have usually means the code was misread: look again before you keep it.
- Where the two disagree about the same part (a different order, a step one of them has and the other lacks, a different reading of what it is for), keep the account the evidence supports, and say what the other one said in "differs" on that part, in one sentence.
- Keep the interface block, the data block, features, not_done and screens_never_reached, merged the same way. Keep the actions under each task from both; they do not need lining up.
- Do not add parts neither source has, and do not drop a part only because one source lacks it.

Leave out names of people, email addresses, keys and data values.
