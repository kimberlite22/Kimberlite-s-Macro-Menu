---
name: tasklist
description: Work with tasklist/, this repo's task backlog (one file per task under tasklist/open/<group>/, done tasks under tasklist/done/, tasklist/INBOX.md for raw notes, tasklist/OVERVIEW.md for a generated summary). Use whenever the user refers to a task without describing it ("mach die naechste task", "nimm den pin task", "was steht an", "what is next"), writes something into INBOX.md, asks to sort, prioritize, plan out or update the backlog, or finishes a task that came from it. Also use before starting any work that might already be listed there.
---

# Tasklist

`tasklist/` is the backlog: one Markdown file per task, plus `INBOX.md` for raw notes and a generated
`OVERVIEW.md` for skimming. The rules live in the "Tasklist routine" section of `CLAUDE.md`, which is
the single source of truth for the file format, the routine steps and the claim protocol. This skill
only routes to the right action; do not restate the rules here when CLAUDE.md changes, fix them there.

## The user names a task without describing it

Check `tasklist/OVERVIEW.md` for a matching entry, then read the linked file and treat it as the task
description. If the match is under `tasklist/done/`, say it is already done instead of starting it.
If the match is under `tasklist/open/` and only has `Goal:`/`Open:` (just-in-time planning, see
CLAUDE.md), fill in `Files:`/`Steps:` first, then implement. If nothing matches, say which entries
you checked before asking.

## The user asks what is next

The lowest-`Prio` file in the highest non-empty group is next, in the order fixes, workflow, gui-ux,
major. Answer with its `Goal:` plus its `Open:` questions, since those block the start.

## The user wrote something into INBOX.md, or asks to sort or update the backlog

Turn every complete-enough INBOX line into a task file under `tasklist/open/<group>/`, then
regenerate `tasklist/OVERVIEW.md`. Keep the user's wording verbatim as `Title:`, in whatever language
they wrote it; everything else you add is English. Two things that go wrong if you skip them: check
whether the entry is already implemented before planning it out (the code moves on while entries sit
in the backlog), and leave half-finished INBOX lines in INBOX untouched instead of completing the
sentence for the user.

## Before you start working on a task

Claim it, so a second agent does not start the same one. Check `git ls-remote --heads origin` and
`gh pr list --state all --head <branch>` for a branch or PR matching the task. If there is none, name
your worktree after the task and push the branch immediately, before writing code: that push is the
claim. If there is one, take the next task down and say which one you skipped, unless the branch is
stale (already merged into main, or no commits and no open PR), which means a dead session rather
than an active claim.

This is a best-effort claim, not a lock: two sessions starting within seconds of each other can both
push the same branch and neither will notice. Details in "Claiming a task" in CLAUDE.md.

## A task is finished

`git mv` its file from `tasklist/open/<group>/` to `tasklist/done/`, rewrite its body to
`Title`/`Completed`/`Commit`/`Result`, and regenerate `tasklist/OVERVIEW.md`, all in the same PR as
the work itself.
