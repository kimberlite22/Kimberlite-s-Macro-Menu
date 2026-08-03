---
name: taskbatch
description: Picks a coherent batch of 2-8 open tasks (a whole group, an explicit range like "task 3-6 in gui-ux", or the agent's own judgment call) and works through them one at a time via subagents, claim through merge, verifying each is actually done before dispatching the next. Use for "mach ein taskbatch", "erledige mehrere tasks", "/taskbatch", "task 3-6 in <group>", "batch die naechsten X tasks" - anything asking for several tasks done in one go rather than a single one (that's the nexttask skill). Load the tasklist skill first for the file format and routine; this skill only sequences a multi-task, multi-subagent run.
---

# Taskbatch

Works through several open tasks in one run, each one dispatched to its own subagent, one subagent
at a time: start it, let it finish the task completely (claim through merge), verify it actually
landed, only then start the next. The `tasklist` skill and the "Tasklist routine" / "Claiming a
task" / "Codex delegation" sections in `CLAUDE.md` are the source of truth for every rule
referenced below; do not restate them here, follow them.

This differs from `nexttask` (one task, worked inline or by one subagent) in two ways: it always
uses subagents, one per task, and it picks a *batch* that has to make sense as a set, not just the
single lowest-`Prio` file.

## 1. Work out the batch

- **Sweep first.** Before anything else, resolve any `tasklist/PENDING_REVIEW.md` entries with a
  filled-in `Review:` line (see "Every time this skill runs" in the `tasklist` skill) - this is not
  optional, it always runs first, and it can create, merge into an existing open task, split into
  several, or reprioritize task files (see "merge or split" in the `tasklist` skill / CLAUDE.md) that
  the batch selection below needs to see.
- **If the user named a group and/or range** ("task 3-6 in gui-ux", "die naechsten 3 aus fixes"):
  read `tasklist/OVERVIEW.md`, resolve that to the actual task files by their current `Prio` order
  in that group (Prio numbers shift as tasks complete, so always re-read OVERVIEW.md fresh, never
  reuse a range from earlier in the conversation). If the named range includes a task marked
  `BLOCKED` in its OVERVIEW.md one-liner, say so and ask whether to skip it or handle it anyway
  rather than silently dropping or forcing it.
- **If the user gave no group/range**, pick the batch yourself: start in the highest-priority
  non-empty group in the fixed order `fixes`, `workflow`, `gui-ux`, `major`, and take a run of tasks
  from the lowest `Prio` up. Judge coherence as you go - a "batch" means these tasks make sense done
  together (same widget/screen/subsystem, a natural sequence, similar scope), not just "next N by
  number". Stop the batch earlier than 8 (down to the 2-task minimum) if the next task in line is a
  poor fit: wildly different scope (a one-line label change next to a multi-file architecture
  change), a different subsystem with nothing in common, or `BLOCKED`. State your batch choice and
  the reasoning in the chat before dispatching anything, so the user can redirect you if your read
  of "coherent" is off.
- **Never cross groups** when picking automatically - `fixes` and `gui-ux` tasks don't form one
  batch. A user-named range can cross groups if they explicitly ask for that; picking on your own
  never does.
- **Size bounds are hard**: minimum 2 tasks, maximum 8. If the coherent set you'd pick is only 1
  task, that's a `nexttask` run, not a `taskbatch` one - say so instead of forcing a second,
  unrelated task in just to hit the minimum.

## 2. Claim the whole batch immediately, before resolving any Open: question

Do this before step 3's blocking questions, not after: resolving `Open:` questions means waiting on
an `AskUserQuestion` reply, which can take real wall-clock time, and any task in the batch that is
still unclaimed during that wait is one another session could start. So claim every task in the
batch right now, in `Prio` order, one by one:

1. Run the branch/PR check from "Claiming a task" in `CLAUDE.md`
   (`git ls-remote --heads origin`, `gh pr list --state all --head worktree-<slug>`) for each task's
   slug.
2. For every task that comes back free, claim it with a lightweight remote branch pointing at the
   current tip of main, without creating a worktree yet: `git fetch origin` then
   `git push origin origin/main:refs/heads/worktree-<slug>`. This is the same claim mechanism as a
   single task (a branch existing is what other sessions check for), just without the worktree
   overhead before it is this task's turn in step 4.
3. If a task in the batch turns out to already be claimed by a **live** branch here, drop it from
   the batch now and say so, the same as the "already claimed" handling in step 4 below - better to
   find this out before spending a round of questions on a task you cannot work on anyway.
4. If the branch found is **stale** instead (already merged into main, or no commits and no open
   PR - a dead session, not an active claim, per "Claiming a task" in `CLAUDE.md`), do not push over
   it yourself: `CLAUDE.md` is explicit that a stale branch is reported for the user to clean up, not
   silently taken over. Drop the task from this batch the same as a live claim, and name it in the
   batch-selection summary so the user can clean up the stale branch and rerun.
5. **Re-check the batch size after dropping anything.** If claim conflicts (live or stale) drop the
   batch below the 2-task minimum from step 1, this is a batch-selection failure, not something to
   push through: stop, report which tasks got dropped and why, and either fall back to a `nexttask`
   run for the one task left (if any), or go back to step 1 and extend the range with the next
   coherent task(s) to rebuild a valid batch - do not silently dispatch a 1-task "batch".

## 3. Resolve blocking questions for the whole batch up front

For every task in the (now-claimed) batch whose `Open:` field is not `-`, resolve it now, before
dispatching any subagent - not one at a time as you get to each task. Batch the questions into one or
more `AskUserQuestion` calls (up to 4 questions per call). Do not guess at a decision a task file
itself flagged as undecided, and do not let a later subagent re-ask something already answered here.

A task that only has `Goal:`/`Open: -` with no `Files:`/`Steps:` yet is fine as-is - per
just-in-time planning, filling those in is the *next* subagent's job, right before it implements
that one task, not something to do here for the whole batch at once.

## 4. Dispatch, one task at a time, foreground

For each task in the batch, in order:

1. Launch exactly one `Agent` (subagent_type `general-purpose`) for that task, **with
   `run_in_background: false`** - you need its result before deciding whether to move on, matching
   the "start it, it finishes, you check, you start the next" control flow this skill exists for.
   **Pick that call's `model` yourself, per task** - the `Agent` tool's `model` param overrides the
   inherited model for this one subagent; omitting it just inherits the session's default. Judge each
   task by its own `Goal:`/`Steps:` the same way `CLAUDE.md`'s Codex model-choice rule judges
   delegation difficulty: a small, mechanical, low-risk task (a one-line fix, boilerplate, a
   doc/config tweak) can run on a lighter model to save cost; a task with non-trivial logic, tricky
   state handling, or architecture-adjacent scope warrants a stronger model, or just the inherited
   default when unsure. This is left to your judgment, not a fixed mapping - state which model you
   picked for each task, and why, in the batch-selection summary from step 1 (or inline per task if
   the batch is mixed), so the user can override it.
2. Brief it as a self-contained task (it has no memory of this conversation): point it at
   `CLAUDE.md` and the task's file, restate the Title/Goal verbatim, pass along any decisions
   resolved in step 3 that apply to it, and tell it explicitly that this task's branch
   (`worktree-<slug>`) was already pushed as its claim back in step 2 - it must reuse that branch,
   not create a fresh one, then run the rest of the cycle itself: just-in-time planning if
   `Files:`/`Steps:` are still empty, Codex delegation per `CLAUDE.md`'s model-choice rule
   (`gpt-5.6-luna` for simple/boilerplate, `gpt-5.6-terra` for non-trivial logic, never for
   architecture/security), verification (tests, manual review if it wrote code itself), the tasklist
   finish steps (`done/`, `PENDING_REVIEW.md` including an optional `Notes:` paragraph when there is
   something specific worth telling the user to test or check, left out otherwise (see "Pending
   release lists" in `CLAUDE.md`), regenerate `OVERVIEW.md`, rebased onto `origin/main`
   since earlier tasks in the same batch just merged), commit, push, PR, immediate merge
   (`gh pr merge <branch> --merge`, never `--delete-branch`), delete the remote branch, remove the
   worktree. Tell it explicitly **not** to launch `tower_defense_macro_gui.ahk` or `gui.exe` to test.
3. **Known gotcha**: `EnterWorktree` creates a *new* branch, so it cannot be pointed at the
   already-pushed `worktree-<slug>` from step 2. Tell the subagent to check that branch out instead,
   in this order: first `git fetch origin`, then - since earlier tasks in the batch may have merged
   into main since step 2 pushed the claim - fast-forward the claim ref with
   `git push origin origin/main:refs/heads/worktree-<slug>` (no `--force`: nothing has been committed
   onto the claim branch yet, so this is a plain fast-forward and Git accepts it silently), and only
   then create the local worktree branch explicitly from the remote one instead of relying on
   checkout's name-matching to find it:
   `git worktree add -b worktree-<slug> ../wt-<slug> origin/worktree-<slug>` (from the repo root).
   If that fast-forward push is instead *rejected* as non-fast-forward, the claim
   branch was not the ancestor-only ref step 2 left it as - someone else pushed commits onto
   `worktree-<slug>` - treat this exactly like bullet 8 below (claimed by someone else: stop, report,
   skip this task in the batch) rather than proceeding onto a branch you no longer know the state of.
   The same fallback (the explicit `git worktree add -b` above, `git worktree remove <path>` for
   cleanup) also covers `EnterWorktree` separately refusing to run from inside a subagent with a
   pinned cwd ("cannot create
   a worktree from a subagent with a cwd override").
4. **When a subagent's turn ends without actually finishing** (it started a background wait - a
   `Monitor`, a long Codex delegation, a Bash `run_in_background` call - and stopped to be resumed
   later), that is not the same as the task being done. Read its own summary/result critically
   before treating it as complete: "kicked off X in the background" or "waiting for a monitor to
   fire" is a mid-task status, not a finish. `SendMessage` it (by the `agentId` from its spawn
   result) to continue, and wait for its next notification rather than starting the next task early.
5. **If Codex is unavailable** (quota exhausted, or any other reason a delegation call fails/hangs)
   mid-task, don't leave the subagent waiting on it indefinitely: message it to fall back to
   `CLAUDE.md`'s own rule - implement/review by hand and proceed, noting plainly in its report that
   no Codex review happened, rather than silently claiming one did.
6. **Verify independently before moving on** - don't just trust the subagent's self-report. Run
   `git fetch origin --quiet && git log origin/main --oneline -5` (and, once you have merged
   commits, `git pull --ff-only origin main` locally) to confirm the PR actually merged, the task
   file actually moved to `tasklist/done/`, and `OVERVIEW.md` reflects it. Only then dispatch the
   subagent for the next task in the batch.
7. **If a task turns out to already be implemented**, that is not a skip: per "Tasklist routine"
   step 4 in `CLAUDE.md`, the subagent still has to do the finish steps with the evidence it found
   (move the file to `tasklist/done/`, rewrite it to `Title`/`Completed`/`Commit`/`Result`, append
   the `PENDING_REVIEW.md` entry, regenerate `OVERVIEW.md`) instead of writing any code. Only a
   genuinely unresolvable blocker (not "already done") is an actual skip - have the subagent say so
   plainly, note it in the final report, and move to the next task in the batch without padding it
   back up to replace the skipped one.
8. **If a subagent somehow finds its assigned task claimed by someone else's branch/PR** (should be
   rare now that step 2 claimed the whole batch up front - this is the residual same-second race
   CLAUDE.md's "Claiming a task" describes, not the normal path), it must stop and report that back
   rather than following the normal single-task fallback of grabbing the next task down - a batch
   subagent wandering off into a task outside the preselected batch would break the batch's own
   coherence and could collide with another task in the same batch. Treat a reported claim conflict
   the same as an unresolvable blocker (previous bullet): skip it in this batch, note it, and move on.
9. **Clean up the claim branch of any task skipped this way**: bullet 7's unresolvable-blocker case,
   or bullet 8's late-discovered claim conflict where the branch was still yours (not the case where
   it turned out to belong to someone else - see that exception below). Step 2's upfront claim pushed
   `worktree-<slug>` for every task in the batch; a skipped task never gets that branch merged or
   deleted through the normal "Ship" path, so it would otherwise sit there looking like a live claim
   and block the task for every future session. Delete it yourself:
   `git push origin --delete worktree-<slug>` (skip this for the claim-conflict case where the branch
   turned out to belong to someone else, not you - deleting someone else's claim would be the exact
   thing "Claiming a task" in `CLAUDE.md` says not to do).

## 5. Report back

Once every task in the batch is handled (done, or explicitly skipped with a reason), summarize in
the chat: a short table or list of task -> PR -> one-line result, any batch-selection reasoning
worth restating, and anything from each subagent's own "Workflow feedback" worth surfacing (tool
gotchas, Codex quota issues, anything that would make the next `taskbatch`/`nexttask` run cheaper).
Also mention directly if you made any small fix yourself outside the subagent flow (e.g. a
one-line doc typo you noticed while verifying) rather than folding it silently into the batch.
