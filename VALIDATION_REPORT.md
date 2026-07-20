# TECH TREE 100 — VALIDATION REPORT

Generated: 2026-07-19T03:20:31.363835Z

## Automated checks

- **PASS** — TECH_TREE contains exactly 100 technologies
- **PASS** — All technology IDs are unique
- **PASS** — Era 1 contains exactly 20 technologies
- **PASS** — Era 2 contains exactly 20 technologies
- **PASS** — Era 3 contains exactly 20 technologies
- **PASS** — Era 4 contains exactly 20 technologies
- **PASS** — Era 5 contains exactly 20 technologies
- **PASS** — All 75 legacy technology IDs were preserved
- **PASS** — Exactly 25 new technology IDs were added
- **PASS** — Prerequisite graph is acyclic
- **PASS** — Every prerequisite points to an existing technology
- **PASS** — Built-in quote IDs exactly match technology IDs
- **PASS** — tech_quotes.json contains 100 unique entries
- **PASS** — Building catalogue still contains 200 buildings
- **PASS** — Every building technology requirement exists
- **PASS** — All 25 artillery types have valid technology requirements
- **PASS** — All 75 wonders have valid technology requirements
- **PASS** — Every fleet technology requirement exists
- **PASS** — Every technology unlocks at least one real content item or resource effect
- **PASS** — Lua file contains the same 100 top-level technology IDs
- **PASS** — Lua braces are balanced
- **PASS** — roma_technology_overhaul.py compiles
- **PASS** — roma_buildings.py compiles
- **PASS** — roma_resources.py compiles
- **PASS** — roma_aeterna.py compiles
- **PASS** — install_technology_overhaul.py compiles
- **PASS** — Patched main imports with 100 technologies and 100 quotes
- **PASS** — Fleet integration adds and gates the late Roman dromon wing
- **PASS** — Artillery requirements are applied after legacy data
- **PASS** — Wonder requirements are applied after legacy data
- **PASS** — Full self-test correctly reports missing unrelated project modules in isolated test directory

## Integration scope

- `roma_aeterna.py`: tree override, era/branch metadata, 100 quotes, unlock cards, artillery/wonder requirements, fleet technology gating, late Roman dromon squadron, resource-context bridge.
- `roma_buildings.py`: 155 building requirement entries remapped to the new tree while the catalogue remains at 200 buildings.
- `roma_resources.py`: researched technologies now modify primary output and derived-material capacity.
- `technologies.lua`: 100-node Lua mirror for installations with `lupa`.
- `tech_quotes.json`: 100 entries; the previous 75 IDs are retained and 25 new technologies receive source-labelled quotations.

## Save compatibility

- All 75 previous technology IDs are preserved.
- Existing researched IDs remain valid.
- The 25 added nodes begin as unresearched.
- The misleading technical ID `counterweight_engines` remains only for save compatibility; its player-facing technology is now the historically late-Roman torsion onager, not a medieval counterweight trebuchet.

## Full game self-test limitation

The package was tested in an isolated installation directory. Python compilation, module import, tree validation and installer validation passed. The game's complete `--self-test` cannot pass in that isolated directory because unrelated project modules such as `roma_economy.py`, `roma_city_events.py`, `roma_army_groups.py` and others were not supplied in this task. Run the final self-test inside the complete project after installation.