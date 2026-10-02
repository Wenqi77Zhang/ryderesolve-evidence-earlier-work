# Project working rules

Read `docs/PROJECT_BASELINE.md`, `docs/INTEGRATION.md`, and `docs/SOURCE_AUDIT.md` before changing behavior. Preserve established team interfaces and keep this repository private.

- Scope is Evidence/Data + read-only tools. Do not claim the full multi-agent product is implemented or tested.
- Never feed `evaluation/` annotations or editorial expected outcomes into runtime case inputs.
- Keep official raw JSON unchanged. New organizer revisions are new source snapshots with a documented provenance update.
- Clearly label synthetic cases and team-authored policies; never relabel them as organizer data.
- Preserve claims as attributed statements, and treat historical profiles as context rather than proof of responsibility.
- Keep arithmetic and reference resolution deterministic. Do not silently infer a no-show policy clock or mutate conflicting records.
- Frozen names: case_id, evidence_id, evidence_refs, policy_refs, decision. Keep the agreed nesting; preserve policy_id for resolving policy_refs. Optional extension fields are compatible.
- Run meaningful unit/contract/HTTP tests after relevant changes. Inspect the UI when its behavior changes.
- Use a project-local .venv. Runtime dependencies are currently standard-library only.
- No credentials, real passenger records, private emails, or participant WhatsApp invite links in commits.
- Record implementation, local verification, team-model integration, and competition compliance as separate statuses.
- User communication: call the user 琪琪, explain unfamiliar terms briefly, and end replies with 喵~. Do not invent mentor endorsement or team contributions.
