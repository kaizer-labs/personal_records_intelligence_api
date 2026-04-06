# Diagram Sources

This folder stores the Mermaid source for the architecture diagrams.

## Why It Exists

Some Markdown viewers do not render Mermaid blocks. The docs therefore show local SVG fallback images first, while keeping the Mermaid source in the Markdown files and in these `.mmd` files.

## Source of Truth

- keep the Mermaid blocks in the Markdown docs aligned with these `.mmd` files
- update both when diagram structure changes
- keep the checked-in SVG fallbacks in `../assets/diagrams/` aligned with the same source

## Current Diagram Files

- `architecture-deployment-component.mmd`
- `architecture-ingestion-flow.mmd`
- `architecture-query-flow.mmd`
- `low-level-runtime-topology.mmd`
- `low-level-ingestion-job-state.mmd`
- `low-level-query-execution-pipeline.mmd`
- `low-level-table-relationship-map.mmd`

## Regeneration Note

If you want fully local SVG exports later, these `.mmd` files are the inputs to feed into a Mermaid CLI or another diagram renderer.
