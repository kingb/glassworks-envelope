# Governance

## Scope

Wire types only: the envelope's enums, newtypes and serde derives, and the schema they are
generated from. The internal types of any producer or client are out of scope.

## Ownership

The reference producer's maintainers author and maintain the envelope. It describes what
that producer puts on the wire.

## Change control

A three-way contract between the reference client (Ember), the reference producer, and the
architect of the system the two belong to.

- Additive changes, such as a new event kind or a new optional field, flow freely.
- Breaking changes **to the wire** require the nod of all three parties. A change that is
  compatible on the wire needs no nod, even when it forces a breaking Cargo release (see
  Versioning).

**How a nod is recorded.** Every commit here carries one human authorship and reviews run
as the repository owner, so GitHub cannot tell the parties apart and refuses Approve as
self-approval. A party's nod is therefore recorded as a **pull-request comment**, never as
GitHub review state.

**Status.** The three-way agreement has been binding since 2026-09-09. It moved with the
envelope when the envelope got its own repository, unchanged.

## Versioning

Semver, as Cargo applies it. Two kinds of change are compatible on the wire, but only one
of them is compatible in the Rust API:

- **A new variant (a new event kind, command or view) is compatible.** Every generated
  enum is `#[non_exhaustive]`, so consumers already carry a wildcard arm and a new variant
  breaks no `match`. `make gen` adds the attribute, because the code generator does not
  emit it, and the freshness check in CI fails if a regeneration drops it.
- **A new field is compatible on the wire, not in the Rust API.** Structs and struct-like
  variants are deliberately *not* `#[non_exhaustive]`, because clients build commands
  with struct literals, and the attribute would forbid that outside this crate. A new
  field therefore breaks a struct literal or a pattern written without `..`. It still
  needs no nod, because it breaks no document on the wire, but it ships as a breaking
  **Cargo** release (`0.x.0` before 1.0).

Before 1.0, Cargo's compatibility rules shift one place to the right: a compatible,
additive change is a **patch** release (`0.1.x`), and a breaking change is a **minor**
release (`0.x.0`). From 1.0 on, the usual minor/major split applies.

**Deprecation before removal.** A type or variant is marked deprecated (`"deprecated": true`
in the schema, with the matching attribute in the bindings) in a compatible release that
names its replacement. It is removed only in a later breaking release, with the three-way
nod.

**Trace correlation.** The envelope carries a `trace` context (W3C `trace_id` and
`span_id`) so that one piece of work can be followed across every component that touches
it. The field was reserved before the first release, so adding correlation never required
a breaking change.

## Decisions taken while authoring v1

None of these reopens a decision about the wire itself: the modelled surface is exactly
what the reference producer emits. But each one binds future edits, so each is recorded
here rather than left in a diff.

**1. The schema describes what producers emit, not everything a reader will accept.** A
property is `required` exactly when the producer always writes it, which makes several
properties required *and* nullable. Marking them unrequired, because a reader tolerates
their absence, loses on the emit side: generated code drops an unrequired property when it
re-emits, so a generated client would stop writing a field that every producer writes. The
cost is a bounded asymmetry between the bindings on documents no producer sends: the Rust
binding accepts an absent one, the Python binding does not. That asymmetry is pinned by the
`conformance/envelope/divergent/` corpus, which records the schema's verdict and each
binding's, and fails if any of the three moves. A known divergence left untested becomes
an unknown one the moment someone regenerates with different flags.

**2. No object sets `additionalProperties: false`.** The producer's reader ignores unknown
properties everywhere, including inside tagged unions. A schema that rejected them would
refuse frames the bus itself accepts, which is the wrong direction for a contract whose
whole job is to survive one side being newer.

**3. `trace_id` and `span_id` are the one place the schema is stricter than the producer's
own types.** Both are unvalidated strings in the producer; the schema pins them to the W3C
hex shapes, all-zero excluded. This is honest rather than aspirational, because the
boundary that accepts a producer-supplied trace context already rejects a malformed one
instead of propagating it. The shape is enforced, so the contract says so.

**4. Identifier types carry no pattern.** `AgentRef` and its siblings are plain strings,
because the producer's identifier types are unvalidated strings and any pattern here would
reject ids the bus accepts. A document that stores ids as *keys* may constrain them, but
its pattern must stay a superset of every id the bus accepts.

Adding a kind or an optional property is compatible **on the wire**. Changing which properties are
required, tightening an identifier, or relaxing the trace shapes is breaking, and needs
the nod of all three parties.

## The dependency rule

This repository depends on nothing in the systems that use it. It sits at the base of the
stack; a dependency in the other direction would invert the layering. There are no
exceptions.
