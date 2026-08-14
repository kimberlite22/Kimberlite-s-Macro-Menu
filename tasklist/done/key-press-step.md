Title:     add einen neuen step, einen key press. Es soll ein paar optionen dazu geben:
           1. Hold duration
           2. Go to next step while holding
           3. Hold Until: "ein step im screen" (Das heisst wie lange gehalten wird wird bestimmt
           bei welchem step gerade anfaengt also wenn bei der auswahl sagen wir step "click button"
           ausgewaehlt ist wird der key solagen gehalten bis der step click button fertig ist.
Completed: 2026-08-14
Commit:    -

Result: New "Key Press" step type with a Key field plus all three requested options (Hold, Go to
next step while holding, Hold Until a step of the same screen). The held-key registry and its
release rules were split into macro/held_keys.ahk with 40 tests in macro/tests/test_held_keys.ahk,
so the "a key must never stay down" guarantee is structural (RunSteps' finally, the pause loop, the
emergency stop, OnExit) rather than per code path.
