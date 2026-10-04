# Execution Plans

- Execution plans live under `./plans/<status>/`.
- Allowed statuses: `proposed`, `active`, `blocked`, `done`, `dropped`. A plan awaiting user review is `proposed`.
- Use folder status as source of truth; do not use frontmatter for status or title.
- Use filename for plan identity.
- Move files between status folders to change status.

Plan body is not strict-schema validated. Use the shape that best fits the task, but keep the plan self-contained enough that another agent can continue from it.

Plans should cover, under clear headings when relevant:

- Goal.
- Intention.
- Scope & Constraints.
- Work Plan.
- Validation.
- Progress.
- Surprises & Discoveries.
- Decisions. Record rejected alternatives with their reason; later sessions cite them to keep settled decisions settled.
- Outcomes & Retrospective.

During implementation, update progress only for real checkpoints.

Close the plan in the commit that lands or abandons the work: fill Outcomes & Retrospective, then move it to `done/` or `dropped/`. A reverted feature's plan moves to `dropped/` with the reason.
