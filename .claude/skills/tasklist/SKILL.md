---
name: tasklist
description: Work with tasklist.txt, this repo's task backlog. Use whenever the user refers to a task without describing it ("mach die naechste task", "nimm den pin task", "was steht an", "what is next"), writes something into the INBOX block of tasklist.txt, asks to sort, prioritize, plan out or update the tasklist, or finishes a task that came from it. Also use before starting any work that might already be listed there.
---

# Tasklist

`tasklist.txt` in the repo root is the backlog and the description of what a task means. The rules
live in the "Tasklist routine" section of `CLAUDE.md`, which is the single source of truth. This
skill only makes sure the routine actually runs. Read `tasklist.txt` first, then act by case.

## The user names a task without describing it

Find the entry in `tasklist.txt` and treat it as the task description. Do not ask the user what the
task is while an entry exists. If the entry is not planned out yet, plan it out first (below), then
implement it. If nothing in the file matches, say which entries you checked before asking.

## The user asks what is next

The top entry of the highest non-empty group is next, in the order FIXES, MAJOR, GUI & UX, WORKFLOW.
Answer with that entry plus its `Open:` questions, since those block the start.

## Before you start working on an entry

Claim it, so a second agent does not start the same task. Check `git ls-remote --heads origin` and
`gh pr list --state all --head <branch>` for a branch or PR matching the entry. If there is none,
name your worktree after the task and push the branch immediately, before writing code: that push is
the claim. If there is one, take the next entry down and say which one you skipped, unless the
branch is stale (already merged into main, or no commits and no open PR), which means a dead session
rather than an active claim.

This is a best-effort claim, not a lock: two sessions starting within seconds of each other can both
push the same branch and neither will notice. Details in "Claiming a task" in CLAUDE.md.

## The user wrote something into INBOX, or asks to sort or update the list

Clear INBOX of every entry that is complete enough to act on: classify it into a group, insert it at
its priority position, plan it out, then remove it from INBOX. Half-finished lines stay in INBOX
untouched. Keep the user's wording verbatim as the title, in whatever language they wrote it.
Everything you add is English. The four fields, nothing more:

    - <title, the user's own wording, kept verbatim>
      Goal:  what is true once this is done, in one or two sentences
      Files: the concrete files / functions / GUI windows the change touches
      Steps: the numbered implementation steps, small enough to act on directly
      Open:  decisions you cannot make alone, or "-" when there are none

Two things that go wrong if you skip them: check whether the entry is already implemented before
planning it out (the code moves on while entries sit in the file), and leave half-finished INBOX
lines in INBOX verbatim instead of completing the sentence for the user.

## A task is finished

Move its entry to the top of DONE with the date and a one-line result naming the commit, in the same
PR as the work itself. `tasklist.txt` is tracked in git, so it is edited in your worktree like any
other file.

Because every parallel session edits this same file, commit the tasklist change as its own last
commit and rebase onto the latest main (`git fetch origin`, `git rebase origin/main`) before
merging. On a conflict, keep every entry that only one side has: those are other sessions' tasks,
not competing versions of yours. Reconcile only the entries both sides changed. See "Parallel
sessions" in CLAUDE.md.
