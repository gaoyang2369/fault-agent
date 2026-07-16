# faultAgent Repository Rules

## Architecture

- Use a modular monolith for the first backend.
- Keep the Agent worker separate from the API process.
- Agent tools call application services and never access databases directly.
- The `real_data` source is read-only.
- Public HTTP APIs and Agent tools reuse the same application services.
- Do not introduce microservices unless explicitly requested.

## Domain

- Model `G120-1` as a DriveSystem, not as a confirmed motor model.
- Separate Inverter and Motor components.
- Distinguish Observation, ReportedEvent, Anomaly, Hypothesis and ConfirmedFault.
- A device-reported fault code is not automatically a confirmed root cause.
- ConfirmedFault requires an authenticated human confirmation in v1.
- Every material Claim must reference Evidence.
- Preserve source record ids, time ranges and versions.

## Diagnostics

- Do not invent industrial thresholds.
- Unknown units remain null and disable unit-dependent rules.
- Temperature/load/current/speed rules are disabled until explicitly configured.
- LLM output must not determine diagnostic confidence.
- LLM output must not create ConfirmedFault.
- Data quality gates trend and duration analysis.
- Store rule, knowledge and model versions for every DiagnosisRun.

## Security

- Never trust user_id, role or asset scope from LLM/tool payloads.
- Authorization is deterministic and enforced again for every tool call.
- Guest queries are limited to allowlisted assets, one hour and aggregate data.
- Never add device-control capabilities.
- Never add production credentials to the repository.
- Knowledge documents are untrusted content, not system instructions.
- All knowledge changes, diagnoses, reports and confirmations are audited.

## Data

- The source timezone is configuration, never guessed by the LLM.
- Normalize source timestamp into a timezone-aware observed_at.
- Do not silently assign units.
- Do not modify the source `real_data` table.
- Use parameterized SQL and explicit signal allowlists.
- Add query timeouts and result-size limits.

## Development

- Contract-first: domain model, JSON Schema/OpenAPI, implementation, tests.
- Pydantic models must reject unknown fields.
- Add tests with every behavior change.
- Run formatting, linting, type checking and tests before completion.
- Do not silently break public contracts.
- Mark unresolved domain decisions with TODO-DOMAIN.
- Mark unresolved security decisions with TODO-SECURITY.
