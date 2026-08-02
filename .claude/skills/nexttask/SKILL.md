---
name: nexttask
description: Picks the highest-priority open task in tasklist/ and works it end to end, claim through merge. Use when the user gives an imperative to just do the next task ("/nexttask", "mach die naechste task", "erledige den naechsten task", "work off the top of the backlog", "do the next task") rather than asking what is next. Load the tasklist skill first for the file format and routine; this skill only sequences the steps for an unattended run.
---

# Next task

Runs the top of the backlog to completion: pick, claim, implement, finish, merge. The `tasklist`
skill and the "Tasklist routine" / "Claiming a task" sections in `CLAUDE.md` are the source of truth
for every rule referenced below; do not restate them here, follow them.

## Sequence

1. **Pick.** Loading the `tasklist` skill first (per this skill's own description) already ran its
   `PENDING_REVIEW.md` sweep, which may have merged a follow-up into an existing task, split one into
   several, or created new ones (see "merge or split" in the `tasklist` skill / CLAUDE.md) — read
   `tasklist/OVERVIEW.md` fresh, after that sweep, not from earlier in the conversation. The task is
   the lowest `Prio` file in the highest non-empty group, in the fixed order `fixes`, `workflow`,
   `gui-ux`, `major`. Read that task file.
2. **Plan if needed.** If the file only has `Goal:`/`Open:` (just-in-time planning left it thin), fill
   in `Files:`/`Steps:` now, checked against the current code, before doing anything else.
3. **Blocking questions.** If `Open:` holds a decision that is not a "-", resolve it with
   `AskUserQuestion` before writing code; do not guess on something the task file itself flagged as
   undecided.
4. **Claim.** Follow "Claiming a task" in `CLAUDE.md`: check `git ls-remote --heads origin` and
   `gh pr list --state all --head <branch>` for the task's branch. If it is already claimed by a live
   branch, stop, say which task you skipped and why, and pick the next one down instead (back to
   step 1). Otherwise enter a worktree named after the task's slug and push the branch immediately,
   before writing any code.
5. **Session title.** Set the terminal title to `[<group>][P<prio>] <slug>` per "Session title" in
   `CLAUDE.md`.
6. **Implement.** Work through the task file's `Steps:` in the worktree. Use the Codex delegation
   rules from `CLAUDE.md` (simple/boilerplate to `gpt-5.6-luna`, non-trivial logic to
   `gpt-5.6-terra`, architecture/security decisions yourself) and run the review step for whichever
   party wrote the code.
7. **Finish the task file.** Per "A task is finished" (tasklist skill / CLAUDE.md): `git mv` it from
   `tasklist/open/<group>/` to `tasklist/done/`, rewrite its body to
   `Title`/`Completed`/`Commit`/`Result`, append a line for it to `tasklist/PENDING_REVIEW.md` (see
   "Pending release lists" in CLAUDE.md; the user has not tried the change yet), regenerate
   `tasklist/OVERVIEW.md`, all in the same commit range as the implementation.
8. **Ship.** Commit, push, open a normal (non-draft) PR into main, and merge it right away with
   `gh pr merge <branch> --merge` (never `--delete-branch`, see the worktree rule in `CLAUDE.md`).
   Then `git push origin --delete <branch>`, and remove the worktree (`ExitWorktree` with
   `action: "remove"`, or `git worktree remove` elsewhere).
9. **Report.** Summarize what changed and close with the "Workflow feedback" section from `CLAUDE.md`
   if anything got in the way, omitted entirely when there is nothing worth reporting.

If step 4 finds every task in every group already claimed by a live branch, say so instead of
inventing work or picking a done task.
