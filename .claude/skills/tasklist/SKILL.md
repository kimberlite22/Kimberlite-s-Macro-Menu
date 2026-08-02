---
name: tasklist
description: Work with tasklist/, this repo's task backlog (one file per task under tasklist/open/<group>/, done tasks under tasklist/done/, tasklist/INBOX.md for raw notes, tasklist/OVERVIEW.md for a generated summary, tasklist/PENDING_REVIEW.md and tasklist/PENDING_RELEASE.md for two-stage pre-release testing where the user writes "approved"/"ok"/a follow-up description directly into a change's own Review: line). Use whenever the user refers to a task without describing it ("mach die naechste task", "nimm den pin task", "was steht an", "what is next"), writes something into INBOX.md, asks to sort, prioritize, plan out or update the backlog, finishes a task that came from it, or is about to cut a release. Also invoke it any time a PENDING_REVIEW.md entry might have a filled-in Review: line, since every invocation sweeps and resolves those first.
---

# Tasklist

`tasklist/` is the backlog: one Markdown file per task, plus `INBOX.md` for raw notes and a generated
`OVERVIEW.md` for skimming. The rules live in the "Tasklist routine" section of `CLAUDE.md`, which is
the single source of truth for the file format, the routine steps and the claim protocol. This skill
only routes to the right action; do not restate the rules here when CLAUDE.md changes, fix them there.

## Every time this skill runs

Before doing whatever else was asked below, first sweep `tasklist/PENDING_REVIEW.md` for entries
with a filled-in `Review:` line and resolve them (see "Pending release lists" in CLAUDE.md for the
exact approval-word match, since "approved, but X" is NOT an approval): an exact approval word moves
the entry to `tasklist/PENDING_RELEASE.md`; anything else turns into work the same way an `INBOX.md`
line does (verbatim `Review:` text as `Title`, an English `Goal` naming the source slug it followed
up on) — a new task file under `tasklist/open/<group>/`, folded into an already-open task covering
the same ground, or split into several if it bundles more than one issue, whichever fits (see
"merge or split" below) — and the entry is then dropped from `PENDING_REVIEW.md`. Regenerate
`tasklist/OVERVIEW.md` if any task file was created or changed this way.

## The user names a task without describing it

Check `tasklist/OVERVIEW.md` for a matching entry, then read the linked file and treat it as the task
description. If the match is under `tasklist/done/`, say it is already done instead of starting it.
If the match is under `tasklist/open/`, claim it first (see "Before you start working on a task"
below) before anything else, including the just-in-time planning below: only once it is claimed, if
it only has `Goal:`/`Open:` (just-in-time planning, see CLAUDE.md), fill in `Files:`/`Steps:`, then
implement. If nothing matches, say which entries you checked before asking.

## The user asks what is next

The lowest-`Prio` file in the highest non-empty group is next, in the order fixes, workflow, gui-ux,
major. Answer with its `Goal:` plus its `Open:` questions, since those block the start.

## The user wrote something into INBOX.md, or asks to sort or update the backlog

`INBOX.md` is a scratchpad for raw, unfiltered thoughts, not something that has to already be
one-line-per-task or carefully worded: judge the substance, not the phrasing, and do the organizing
yourself. Turn every complete-enough INBOX line into a task file under `tasklist/open/<group>/`, then
regenerate `tasklist/OVERVIEW.md`. Keep the user's wording verbatim as `Title:`, in whatever language
they wrote it; everything else you add is English. Two things that go wrong if you skip them: check
whether the entry is already implemented before planning it out (the code moves on while entries sit
in the backlog), and leave half-finished INBOX lines in INBOX untouched instead of completing the
sentence for the user.

**Merge or split when it makes sense** (see step 1 of "Routine" in CLAUDE.md for the full rule): if a
line is really the same piece of work as an already-open task, fold it into that task file instead of
creating a near-duplicate; if a line actually bundles more than one distinct piece of work, split it
into multiple task files instead of forcing one oversized file. This applies the same way to
`PENDING_REVIEW.md` follow-ups (see "Every time this skill runs" above). Say what you merged or split
and why in the chat either way, so the user can correct a bad call.

## Before you start working on a task

Claim it, so a second agent does not start the same one, and do this before anything else about the
task, not right before implementing it: before filling in a thin task file's `Files:`/`Steps:`
(just-in-time planning) and before resolving an `Open:` question with the user, since both of those
can take real wall-clock time in which another session could still start the same task. Check
`git ls-remote --heads origin` and `gh pr list --state all --head <branch>` for a branch or PR
matching the task. If there is none, name your worktree after the task and push the branch
immediately, before doing anything else for it: that push is the claim. If there is one, take the
next task down and say which one you skipped, unless the branch is stale (already merged into main,
or no commits and no open PR), which means a dead session rather than an active claim.

This is a best-effort claim, not a lock: two sessions starting within seconds of each other can both
push the same branch and neither will notice. Details in "Claiming a task" in CLAUDE.md.

Also set the terminal window/tab title to `[<group>][P<prio>] <slug>` at this point, so multiple open
sessions stay distinguishable at a glance. See "Session title" in CLAUDE.md for the exact command per
shell; this cannot rename the session's entry in a job list or sidebar, only the terminal's own title.

## A task is finished

`git mv` its file from `tasklist/open/<group>/` to `tasklist/done/`, rewrite its body to
`Title`/`Completed`/`Commit`/`Result`, append its two-line entry (`- <slug> - <one-liner>` plus an
empty `Review:` line) to `tasklist/PENDING_REVIEW.md`, and regenerate `tasklist/OVERVIEW.md`, all in
the same PR as the work itself.

## The user is about to cut a release

See "Pending release lists" in CLAUDE.md: retest every unchecked entry left in
`tasklist/PENDING_RELEASE.md`, then clear the file once every entry is checked; `tasklist/done/`
itself is untouched either way. Approving a single change no longer needs asking for separately: the
user writes their verdict into the change's own `Review:` line in `tasklist/PENDING_REVIEW.md`, and
the "Every time this skill runs" sweep above resolves it on the next `/tasklist` invocation.
