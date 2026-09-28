# Approvals record

This repository was rebuilt with fresh history on 2026-09-28, before it became public. The
content of its first commit is exactly the content the three governing parties reviewed and
approved; only the history was replaced. This file records those approvals, which were
originally posted as pull-request comments on the pre-rebuild repository (see
[`GOVERNANCE.md`](GOVERNANCE.md), "How a nod is recorded").

## 0.1.0: the import

The schema, bindings and conformance corpus moved into this repository unchanged, apart from
publish metadata and the fixes below.

| Date (UTC)       | Party              | Nod                                                                                   |
|------------------|--------------------|---------------------------------------------------------------------------------------|
| 2026-09-28 02:16 | Reference client   | Conditional: the `#[non_exhaustive]` claim in `GOVERNANCE.md` did not match the bindings. |
| 2026-09-28 02:22 | Reference client   | Re-confirmed once every generated enum was marked `#[non_exhaustive]`.                 |
| 2026-09-28 03:27 | Reference producer | Conditional: "breaking" was used in two senses (wire versus Cargo).                   |
| 2026-09-28 03:45 | Reference client   | Nod stands through the wording fix and the move of the schema `$id` to this repository. |
| 2026-09-28 10:53 | Reference producer | Unconditional.                                                                        |

The architect's own review posts on the same pull request recorded the fixes each condition
asked for.

## 0.1.1: the delta view, the events lane and the viewer commands

| Date (UTC)       | Party              | Nod                                                                                   |
|------------------|--------------------|---------------------------------------------------------------------------------------|
| 2026-09-28       | Reference producer | Author of the change.                                                                 |
| 2026-09-28 11:03 | Reference client   | Nod: the reference client's real encoder output validates against 0.1.1, its decoder handles the new producer fixtures, and the change is purely additive. |

Additive changes need no three-way nod under [`GOVERNANCE.md`](GOVERNANCE.md); the reference
client reviewed this one because it generates its bindings from this schema.
