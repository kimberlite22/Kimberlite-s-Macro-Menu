HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes the user already approved once in PENDING_REVIEW.md, staged here for one more check right
before a release ships them. One line per change, grouped by task group in the fixed order fixes,
workflow, gui-ux, major:

    - [ ] <slug> - <one-liner>

Check a line off (`- [x]`) once it has been retested for the release. Once every entry is checked,
clear the file down to this header: the explanatory text above and the template line above stay,
every pending entry and now-empty group heading is removed.

## FIXES

- [ ] bugfix-batch-2026-07-31 - combined bugfix release note covering five approved fixes:
      config-load-failure-permanent, tower-loadout-slot-choices, config-read-race-on-save,
      refresh-game-processes-stuck-busy, pin-one-shot-move (see tasklist/done/ for each one's full
      description)

## WORKFLOW

- [ ] release-staging-list - two-stage PENDING_REVIEW.md / PENDING_RELEASE.md testing before a
      release
