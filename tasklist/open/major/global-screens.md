Title: bei dem neuen screen overhaul die screens sollen global sein alle für jedes preset gleich.
       Nimmm das preset challenges als vorlage für die migration welche screens global sein sollen.
Prio:  1

Goal:  Screens (their name, identity and entry detection, per [[screen-detection-overhaul]]) are
       defined once globally instead of being duplicated inside every preset's
       `[Preset_<name>]` section. Every preset recognizes the same set of screens; only the
       step-sequence run on each screen stays preset-specific. The "Challenges" preset's current
       3 screens (Before Map Detection / Ingame / Round End) are the template for the migration:
       they become the global screen set every other preset is migrated onto.
Files: macro/tower_defense_macro_gui.ahk: GetPresetScreenNames/ScreenIndexByName (4766-4782),
       BuildScreenStepsFromIni/...ByName (4785-4818), ReadScreenDetectionFromIni/
       WriteScreenDetectionToIni (4821-4872), LoadPresetScreens/RefreshScreenDdlItems/
       LoadScreenSteps/SaveScreenToIni (4876-4919+), New/Rename/Delete/Move Screen GUI actions,
       CreatePreset's default single-screen seeding (5820-5870), InitPresets' first-run
       "Challenges" seed (5508-5556), the old-format preset migration (5578-5647) and
       MigrateScreenDetectionSchema (898-929) as the closest precedent for a one-time schema
       migration, preset export/import (5881-5919, currently dumps the whole `[Preset_<name>]`
       section verbatim, comment already notes map profiles are shared but screens are not).
       gui/ipc/config_reader.py: ScreenConfig (82-91), PresetConfig.screens (113-120),
       _read_preset (228-250). gui/ipc/protocol.py: screen_payload/new_screen_payload etc.
       (358-377), all currently keyed by presetName. gui/app/edit_preset_window.py: screen_list
       and its New/Rename/Delete/Move buttons (operates on one in-memory PresetConfig today).
       config.ini (user-local, gitignored): needs the new global `[Screens]`-style section plus
       a one-time migration, same shape as MigrateScreenDetectionSchema.
Steps: 1. Confirm the open scope question below before touching code: this plan assumes only
          screen identity + entry detection become global, and each preset keeps its own step
          sequence per screen (a preset just runs different actions on the same recognized
          screen). Sharing the step sequence itself is a different, much bigger change and is
          NOT what these steps implement.
       2. Add a global screen registry to config.ini (e.g. `[Screens]` listing screen names, plus
          one `[Screen_<name>]` section per screen holding DetectionType/X/Y/EndX/EndY/Text/
          DefaultScreen), read/written independently of any preset.
       3. Write a one-time migration (mirroring MigrateScreenDetectionSchema's pattern): seed the
          global registry from the "Challenges" preset's 3 screens if that preset exists, else
          from the first preset found. For every other preset, match its existing screens onto
          the global set by exact name; a preset screen whose name has no global match is not
          silently dropped, it is logged for manual review (see open question on this below).
          Every preset's own step sequences are preserved unchanged, only the DetectionType/X/Y/
          EndX/EndY/Text/DefaultScreen fields move out of the preset section.
       4. Update MainLoop's per-tick screen-detection evaluation to read detection config from
          the global registry instead of `Screen{i}Detection*` inside the active preset.
       5. Update the screen editor GUI (AHK): New/Rename/Delete/Move Screen now edit the global
          registry (visible identically from every preset), while step editing still only
          touches the currently open preset's own steps for that screen.
       6. Mirror the split in gui/ipc/config_reader.py, protocol.py and edit_preset_window.py:
          read the global registry once, keep per-preset screens as a reference to it plus that
          preset's steps; update the SAVE_PRESET / local_bridge round-trip so it stops writing
          detection fields into the per-preset section.
       7. Decide and implement what preset export/import (5881-5919) carries: exporting a preset
          alone leaves its referenced global screens undefined on import into a fresh config, so
          either bundle a snapshot of the referenced global screens with the export, or document
          that a global-screen export is a separate, second step.
       8. Update gui/tests (fixtures currently have "Lobby"/"Battle" and "Alt Screen" presets with
          non-Challenges screen names, exercising the exact same-name-mismatch path from step 3)
          and any AHK-side tests for the new schema.
Open:  Does "global" mean only the screen's identity/entry-detection is shared (this plan's
       assumption: same recognized screen, different actions per preset), or should the full
       step sequence on a screen also become identical across every preset? The latter would mean
       two presets can no longer do different things on the same screen, which seems to defeat
       the purpose of having separate presets, so confirm before starting.
       For a preset whose current screens don't match the Challenges names at all (the test
       fixture presets "Lobby"/"Battle"/"Alt Screen" are a real example, and any existing user
       preset not named like Challenges), what should the migration do: create empty/default step
       sequences for the missing global screens and let the user fill them in, try a fuzzy name
       match, or require manual reconciliation per preset before that preset runs again?
