Title: add python to codex
Prio:  1

Goal:  Delegated Codex work can run the project's pytest suites itself, instead of ending every
       delegation with "tests could not run because Python is unavailable" and leaving the calling
       session to be the only thing that ever executes them. That gap already shipped a real bug
       this week (a Qt clicked-signal bool binding to a positional parameter, in
       map-advanced-reuse-step-editor), which one test run inside the delegation would have caught.

Files: tools/codex-delegate.mjs (the `codex` child's environment), CLAUDE.md (the Codex delegation
       section), plus a one-time per-machine permission setup that lives in the docs rather than in
       code.

Steps: 1. Diagnose properly first: it is NOT a missing interpreter and NOT a PATH problem. Codex
          runs its sandbox as a separate OS account (CodexSandboxOffline / CodexSandboxOnline, the
          same reason git needs safe.directory='*'), and the launching user's Python lives under
          their own profile, which that account cannot read. The Python directory is already on the
          inherited PATH; it just cannot be opened.
       2. Grant the two sandbox accounts read+execute on the Python installation directory only.
          Windows gives Everyone "bypass traverse checking", so the profile directories above it do
          NOT need to be opened up. The GUI test dependencies live in the same tree, so one grant
          covers interpreter and site-packages together.
       3. Second, separate failure once Python runs: TEMP is inherited from the launching user and
          points into their profile, so Python raises "No usable temporary directory found" (every
          fallback is unreadable too) and pytest dies before collecting anything. Create a temp
          directory outside any profile, grant the sandbox accounts write on it, and have
          tools/codex-delegate.mjs point the codex child's TEMP/TMP/TMPDIR at it.
       4. Keep that redirect best-effort: honor a CODEX_DELEGATE_TMPDIR override and pass the
          environment through untouched when the directory does not exist, so the wrapper still
          works unchanged on a machine that never ran the setup.
       5. Document the whole setup in CLAUDE.md, since it is per-machine and cannot be committed:
          what to run, why each step is needed, and that "Python is unavailable" from a delegation
          means the setup is missing rather than that the tests cannot run.
       6. Verify by asking a read-only delegation to run the gui suite and comparing its count
          against a local run.

Open:  -
