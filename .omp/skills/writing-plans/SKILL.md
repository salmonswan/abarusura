---
name: writing-plans
description: Rules for writing a plan that someone else will carry out. Read it before writing any plan, in plan mode or as a planning agent.
---

# Writing plans

A plan is instructions for someone who has not seen this conversation. Write it so they can carry it out without asking you anything.

- Start with the goal in one sentence, and what "done" looks like.
- Put open questions at the top, before the steps, so they get answered first.
- Step 1 checks that everything the plan relies on is there: files, scripts, servers, logins. Say how you checked each one. Never write that something exists unless you looked. If one is missing, stop there and say so.
- Number the steps. One action per step, in the order they happen.
- Each step names the exact file, function or command. Never "update the config" or "handle errors".
- Each step says how to check it worked: the command to run and the result to expect.
- Keep each task small enough to finish in one go. Split big work into separate tasks, for example: collect the results, sort them, then fix them. A run over 5 minutes gets its own step, with what to do if it fails partway.
- A pattern or parser that reads tool output (a regex, a log filter) is tried on a real sample of that output before the plan uses it.
- When a step hands work to a helper, name the tools it needs (for example a shell) and its model. A script or the cheapest model extracts, matches and counts. The strong model decides order and design, and writes anything the owner will read to make a decision, such as a recommendation and its risks.
- State every decision you made, as a decision, with its reason. Mark guesses as guesses. Elsewhere, say why only where the reason changes what someone does.
- End with what the plan does not cover and what will not be tested.
- Plain words, short sentences, one idea per sentence. No em or en dashes.
