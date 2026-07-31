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
Completed: 2026-07-31
Commit:    -

Result: Two hand-maintained files stage a finished change through two rounds of testing before a
release: tasklist/PENDING_REVIEW.md (a Claude session just finished it, user has not tried it yet)
and tasklist/PENDING_RELEASE.md (user approved it once, one more check before a release). Finishing a
task now also appends its one-liner to PENDING_REVIEW.md; approving a change moves its line to
PENDING_RELEASE.md; cutting a release means rechecking every line there, then clearing the file
entirely. tasklist/done/ itself is unchanged and remains the permanent history. Documented in the new
"Pending release lists" section of CLAUDE.md and mirrored in .claude/skills/tasklist/SKILL.md.
