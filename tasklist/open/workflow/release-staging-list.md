Title: In overview.md soll ein neuer tab geaddet werden irgendwie so current changes die sollen bei
       einem neuen release gelöscht werden, die DONE changes bleiben erhalten wie gehabt auch mit
       denen die in current changes drin sind, die current changes sind nur damit ich testen kann
       für den release ob sie funktionieren. Ich sollte bei jeden current change etwas anklicken
       können das die zu release changes geaddet werden das heißt sie funktionieren und brauchen
       keine follow up changes. Dann bevor der release kommmt sollte ich alle releasen changes
       nochmal testen und dann werden die zu done gemoved alle. Wenn overview nicht von mir geditet
       werden soll wie es im moment ist kann es auch eine seperate file sein wenn du willst, sag mir
       was du denkst was am besten ist. Die task description sollte dann nur ein one liner sein, und
       nach kategorie wieder gesorted, damit ich direkt weiß was was ist. Wenn die zu done gemoved
       werden ist das nicht mehr nötig da das nur für die history ist und eigentlich nicht direkt
       benötigt.
Prio:  1

Goal:  A release-readiness stage exists between "merged" and "done": a task that just got merged
       lands in a pending-verification list instead of only tasklist/done/. The user marks each
       pending entry verified (works, no follow-up needed) as they test it in a real build; right
       before cutting a release, everything still unverified gets tested once more, then the whole
       list is cleared (the tasks themselves are already in tasklist/done/ from the normal "finish a
       task" step and stay there unchanged; this list only tracks the pending window between merge
       and release).
Files: tasklist/OVERVIEW.md and the "Regenerating OVERVIEW.md" section of CLAUDE.md (it is
       explicitly auto-generated and never hand-edited, which is why a hand-driven "click to mark
       verified" action does not fit inside it); a new hand-maintained file, tentatively
       tasklist/PENDING_RELEASE.md, since it needs one-off manual edits rather than regeneration
       from source files; the "A task is finished" and "Tasklist routine" sections of CLAUDE.md,
       which need a new step describing when an entry enters/leaves this list; tasklist/done/*.md
       (unchanged in shape, referenced by slug from the pending list).
Steps: 1. Resolve the open design question below (separate hand-maintained file vs. a field added to
          every tasklist/done/<slug>.md file plus a new OVERVIEW.md section) before writing anything
          else; it changes every later step.
       2. Recommended shape, pending that confirmation: add tasklist/PENDING_RELEASE.md, a short
          hand-maintained list, one line per task since its PR merged, sorted by group like
          OVERVIEW.md's own sections so the user can tell what is what at a glance:
          `- [ ] <slug> - <one-liner>` (unverified) vs `- [x] <slug> - <one-liner>` (verified in a
          real build, needs no follow-up). This sits ALONGSIDE the existing "move to tasklist/done/
          on finish" step, not instead of it: a task still moves to done the moment its PR merges,
          exactly as today.
       3. Update the "A task is finished" step in CLAUDE.md so finishing a task also appends its
          one-liner (unverified) to tasklist/PENDING_RELEASE.md.
       4. Add a "mark verified" action to the routine: checking a line (by the user directly, or by
          asking Claude to do it after testing) means that specific change was tested in a real
          build and needs no follow-up.
       5. Add a "cut a release" step: retest every still-unverified line one more time, then once
          every line is checked, clear tasklist/PENDING_RELEASE.md entirely. Nothing needs to move
          out of tasklist/done/ since the tasks were already recorded there when they finished; this
          file only ever tracked the pending window, never the historical record.
       6. Document the new stage in the "Tasklist routine" section of CLAUDE.md so every session
          picks it up.
Open:  Separate hand-maintained file, or a `Released: yes/no` field on each tasklist/done/<slug>.md
       plus a regenerated "PENDING RELEASE" section in OVERVIEW.md? Recommendation: the separate
       file, because OVERVIEW.md is explicitly auto-generated/never hand-edited (the user's own
       observation), while "mark this verified" is a one-off, hand-driven action that does not fit a
       regenerate-from-source-of-truth model. Needs the user's confirmation before implementing.
       Also: should the pending list ever hold anything besides freshly-finished tasks, e.g. can the
       user manually add or remove a line themselves if they want to re-flag something after all?
