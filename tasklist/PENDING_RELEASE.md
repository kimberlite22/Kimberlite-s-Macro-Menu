HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes the user already approved once in PENDING_REVIEW.md, staged here for one more check right
before a release ships them. One line per change, grouped by task group in the fixed order fixes,
workflow, gui-ux, major:

    - [ ] <slug> - <one-liner>

Check a line off (`- [x]`) once it has been retested for the release. Once every entry is checked,
clear the file down to this header: the explanatory text above and the template line above stay,
every pending entry and now-empty group heading is removed.

## WORKFLOW

- [ ] release-staging-list - two-stage PENDING_REVIEW.md / PENDING_RELEASE.md testing before a
      release
