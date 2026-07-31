Title: Das macro soll mehrere games supporten die man in general auswählen kann. Sie haben seperate
       conifgs ausser disconnect support und das game window. Aber map placement und alles andere
       ist anders. Es soll auch game specific screens und components geben, bzw screens sind
       komplett game specific, nur manche components sind game specific die werde ich später noch
       angeben
Prio:  5

Goal:  The macro supports multiple different games, selectable from a setting in General. Each game
       has its own separate config (screens, map placement, presets, steps, etc.) except disconnect
       support and the game-window settings, which stay shared across every game. Screens are
       entirely game-specific; only some components are game-specific (which ones is left to a
       later, more detailed note from the user).
Open:  Large architecture change with several open decisions, do not plan Files:/Steps: until these
       are resolved and until [[global-screens]] has landed (this builds directly on that
       migration): how does per-game scoping interact with [[global-screens]] - does each game get
       its own global screen registry ("global per game" rather than one registry for the whole
       app)? Which components are shared vs. game-specific beyond the two named exceptions
       (disconnect support, game window) - the user said they will specify this later. Does game
       selection also scope which presets are available, or can any preset run against any game?
       Does this need a new top-level "Game" concept in config.ini (e.g. `[Game_<name>]` wrapping
       its own presets/screens), analogous to today's `[Preset_<name>]` sections?
