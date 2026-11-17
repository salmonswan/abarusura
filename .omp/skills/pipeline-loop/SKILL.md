---
name: pipeline-loop
description: Run a task through the pipeline loop. Brief, plan, one git copy per piece, build, review, pull request, CI, report. Use when the owner asks for the pipeline loop.
---

# Pipeline loop

You run the owner's task as small pieces. Each piece gets its own copy, its own pull request and its own CI run. You never merge. The owner merges.

Start omp for this run with `--warn-cost 5`, so spend is flagged at 5 USD. If omp was started without it, tell the owner once. The config in `.omp/config.yml` also sets it.

Rules that hold for the whole run:
- Never merge. Never run `gh pr merge` or `devpipeline merge`.
- Never write `docs/standards-review.yml`. Never edit `.omp` or `.pipeline`.
- Push only through `devpipeline piece pr`. Never `git push` or `gh pr create`.
- Do not set `CI`. Do not use `script`, `expect` or `unbuffer`.
- No mention of AI, Claude or an LLM in commits or PR bodies, and no attribution trailer (no Co-Authored-By line, no session link). No em or en dashes in anything written. Plain short sentences.
- Use the agents by name: `piece-planner`, `piece-builder`, `piece-reviewer`, `piece-fixer`. A builder or fixer is always a fresh agent.
- Never pass a `model` when you start an agent. Each agent's own file sets its model.

## Run folder

Brief, plan, fence files, PR body files, the parking file and the report live in `~/.cache/devpipeline/runs/<repo>/<date>-<task>/`. This is outside the repo. Make it first.

## Steps

1. Run `devpipeline piece clean` with no `--yes`. It only lists. Show the owner what it would remove and ask. Run `devpipeline piece clean --yes` only after the owner agrees. Run `devpipeline piece list` and report any parked copies.
2. Brief. Ask `piece-planner` to write the brief, plus any journey changes (docs/journeys) and standards changes. **Stop. The owner approves the brief.**
3. Plan. Ask `piece-planner` for the plan. Each piece has: a goal, a fence file, the tests that prove it, a PR body file, and an optional `after:` list. Standards changes go in a first piece that the others wait for. **Stop. The owner approves the plan.**
4. Start pieces. A piece with no `after:` starts at once. A piece with `after:` starts only when those pieces are merged (check with `gh pr view` or `piece status`, and ask the owner if unsure). For each one:
   - `devpipeline piece start NAME --fence-file FENCE_FILE`. It prints the copy path. If it refuses (copy cap or low memory), tell the owner and wait. Do not use `--no-resource-check` on your own.
   - Install dependencies in the copy before the builder starts. Run the stack's install command inside the copy's `app_dir` (set in pipeline.yml, default the repo root). For a web project that is `npm ci`.
   - Start a fresh `piece-builder` in the copy. Give it the goal, the fence file, the copy path and the parking file. It writes tests first, then the code.
5. Review. Start `piece-reviewer` on the copy. If it returns DEFECTS, start a fresh `piece-builder` in the same copy with the defect list. At most 2 failed reviews per piece. After the second failed review, park the piece: write the reason in the parking file and tell the owner. The copy stays, and holds a slot until `devpipeline piece drop NAME`.
6. Pull request. Run `devpipeline piece pr NAME --body-file BODY_FILE`. If it refuses (a file outside the fence, or a gate fails), read the reasons and send them to a fresh `piece-builder`, at most 2 times per piece, then park the piece with the reason. These do not count as reviews.
7. CI. Run `devpipeline piece status NAME --wait`. Read the exit code:
   - 0: green. Ask the owner to merge, in one message with: the PR link; what changed and why, in 3 to 5 lines from the PR body; each item in the PR's review checklist and what it asks the owner to check; and what was not tested.
   - 3: needs owner (a protected file changed). Stop. Tell the owner which files. This is not a fix round.
   - 1: failed. Start a fresh `piece-fixer` in the copy with the printed failure text. Then run `piece pr` again, then `piece status --wait` again. At most 3 CI rounds. After the third failed round, park the piece with the reason.
   - 4: still pending after the wait. Tell the owner and stop for that piece.
8. Ideas outside a fence go in the parking file, not into the code.
9. Final report in the run folder, and a summary to the owner: each piece, its PR, its CI state, what was parked and why, and the counts of pieces, review rounds and CI rounds. The owner merges. Pieces that waited on others start after the owner merges what they wait for.

## Limits

- 2 failed reviews per piece.
- 3 CI rounds per piece.
- The copy cap is set by `resources.max_piece_copies` (default 3, ceiling 6). Do not work around it.
- Spend warning at 5 USD (`--warn-cost 5`).
