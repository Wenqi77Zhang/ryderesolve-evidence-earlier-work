# RydeResolve — Earlier Evidence/Data + Tools Development

This repository preserves **Wenqi Zhang's earlier development work on the Evidence/Data + tools module** for RydeResolve, a team project for Tencent Cloud Hackathon Singapore 2026. It contains the implemented standalone module, tests, source audits and handoff documentation created before integration into the shared team repository.

After this module was handed over, the team lead integrated it with the other members' work in **[Maple-0102/ryderesolve](https://github.com/Maple-0102/ryderesolve)**. Ongoing integrated development and the team's current deliverables are maintained there. This repository is retained to make the earlier module work and its original commit history traceable.

**Record:** standalone module v0.2.0, developed on 2 October 2026. Repository context updated on 16 October 2026; the original implementation, data and tests are retained.

## Relationship to the team project

| Repository | Role |
| --- | --- |
| [Wenqi77Zhang/ryderesolve-evidence-earlier-work](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work) | Original Evidence/Data + tools development, validation and handoff record. |
| [Maple-0102/ryderesolve](https://github.com/Maple-0102/ryderesolve) | Shared team project integrating Evidence, Rider/Driver Advocates, Judge, orchestration and the application UI. |

The team baseline imported the module under [`vendor/ryderesolve-evidence-tools/`](https://github.com/Maple-0102/ryderesolve/tree/2e6bea725e19febf119de81ddf17c60cc6d54661/vendor/ryderesolve-evidence-tools). Its core Python package, case data, contracts and tests match the corresponding files at this repository's original [`64b072a`](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work/commit/64b072abe4596d74e3809701753d99d76aa04f90) baseline. The standalone inspector UI and repository-level setup were not all carried into that import.

The import appears in the team repository under the integrator's commit. The original development commits remain here under `Wenqi77Zhang`; the links below document that history across the two repositories. This record attributes the Evidence/Data + tools component to Wenqi's assigned work, while the integrated product remains a team project.

## Development and integration history

Dates below use Singapore time (UTC+8).

| Date | Record | Scope |
| --- | --- | --- |
| 2 October 2026 | [`58f05ae`](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work/commit/58f05aee25239d66dd14af6e2708930097913bc8) | Implemented the traceable evidence module for the agreed dispute cases. |
| 2 October 2026 | [`333c5ad`](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work/commit/333c5adb0193717c239724b8e1f4fa6264cceb5d) | Documented the repository synchronization workaround. |
| 2 October 2026 | [`64b072a`](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work/commit/64b072abe4596d74e3809701753d99d76aa04f90) | Hardened evidence snapshots, schema validation and trip-window calculations. |
| 13 October 2026 | [Team integration commit `2e6bea7`](https://github.com/Maple-0102/ryderesolve/commit/2e6bea725e19febf119de81ddf17c60cc6d54661) | The team lead integrated the Evidence, Advocate and Judge baseline in the shared repository. |
| 16 October 2026 | [Team PR #2, merged](https://github.com/Maple-0102/ryderesolve/pull/2) | Wenqi's subsequent official-dataset and Ryde Policy v2.1 integration was merged into the team project. That later implementation is maintained there. |

## Module scope and authorship

Wenqi was responsible for the team's **Evidence/Data + tools** workstream: interpreting the supplied data, applying the agreed interfaces, and delivering a traceable evidence module for integration. Development, documentation and tests were assisted by Codex under Wenqi's direction. Teammates supplied the initial workflow and Advocate/Judge interface drafts and were responsible for the other assigned components. Organizer data and policy material retain their original provenance.

The work retained here includes:

- Deterministic conversion of case records into an Evidence Pack, with stable evidence and policy IDs and source lookups.
- One organizer sample, **DISP-002 / No-Show Charge**, and one explicitly labeled synthetic integration case, **SYN-ROUTE-001 / Route Deviation**.
- Read-only Python, CLI and HTTP tools for loading cases, inspecting evidence, auditing inconsistencies and validating references.
- Versioned snapshots binding source data, normalization version, source mappings and provenance; JSON Schema validation for the agreed contracts.
- A standalone local evidence inspector, unit/contract/HTTP tests, an isolated package-installation check and integration documentation.

Advocate model calls, Judge reasoning, multi-agent orchestration and the team's final evaluation UI are outside this standalone module's implementation scope. Those parts should be reviewed in the team repository with their respective contribution history.

## Historical baseline and limitations

This v0.2.0 snapshot predates the later official DISP-001 and DISP-003 integration and standalone Policy v2.1 support. For that work and the current policy interpretation, read the team's [Evidence integration guide](https://github.com/Maple-0102/ryderesolve/blob/main/docs/EVIDENCE-INTEGRATION.md).

- The original no-show sample retains distinct order, App and scheduled-pickup clocks: 480, 470 and 360 seconds. This snapshot does not choose a billing basis without a supporting policy.
- Synthetic route records and rules are integration fixtures. Polyline calculations do not establish an optimal road route or an official Ryde policy.
- Expected outcomes in `evaluation/` are separated from runtime inputs. Reference validation checks structure and identifier resolution; it does not prove that an argument or ruling is correct.
- The dated [validation record](docs/VALIDATION.md) reports checks performed for the original module. Current CI results are available in [Actions](https://github.com/Wenqi77Zhang/ryderesolve-evidence-earlier-work/actions); historical results do not establish current model quality or end-to-end product performance.

## Run the original module

Python 3.12+ is required. From this repository in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ryderesolve_evidence serve --port 8765
```

Open <http://127.0.0.1:8765> to inspect cases, evidence and policy references, audit flags and downloadable snapshots. Use `Ctrl+C` to stop the server. On macOS/Linux, use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

CLI inspection does not require the server or a model API key:

```powershell
.\.venv\Scripts\python.exe -m ryderesolve_evidence pack DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence prepare DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence audit DISP-002
.\.venv\Scripts\python.exe -m ryderesolve_evidence route SYN-ROUTE-001
```

The shared names `case_id`, `evidence_id`, `evidence_refs`, `policy_refs` and `decision` are preserved. Evidence Pack keeps `case_id / dispute_type / facts / policy`; each fact requires `evidence_id / fact / source`. Source excerpts, audit metadata and snapshot information are available through separate read-only queries.

```python
from ryderesolve_evidence import EvidenceTools

tools = EvidenceTools()
snapshot = tools.prepare_case("DISP-002")
pack = snapshot["evidence_pack"]
source = tools.get_evidence(
    "DISP-002", "E-002", expected_snapshot_id=snapshot["snapshot_id"]
)
```

## Original development documents

These dated documents, originally written in Chinese, are retained as records of this module's earlier development stage. Their pending items and completion statements describe that stage; use the team repository for subsequent decisions and updates.

- [Integration guide](docs/INTEGRATION.md): Python/HTTP interfaces, JSON fields and reference rules.
- [Project baseline](docs/PROJECT_BASELINE.md): original scope, team contracts and open questions.
- [Source audit](docs/SOURCE_AUDIT.md): timing discrepancies, statement attribution and data boundaries.
- [Validation record](docs/VALIDATION.md): original checks and integration limitations.
- [Hardening review](docs/HARDENING_REVIEW.md): reproduced issues, fixes and remaining questions.
- [Provenance and attribution](docs/PROVENANCE.md): source ownership and human/team/AI-assisted contribution boundaries.

Both repositories are private. Their links require repository access. Preserve source ownership and keep credentials, private communications and real passenger records out of commits.
