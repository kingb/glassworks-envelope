# Conformance corpus

Every language binding executes this corpus. A binding that disagrees with it fails CI.
The corpus is what makes "schema-first" testable rather than aspirational — code
generation alone produces two type definitions that merely *claim* to match.

The corpus lives in `envelope/`.

## Layout — `envelope/`

- `envelope/valid/<name>.json` — must parse
- `envelope/valid/<name>.expect.json` — `{"canonical": <the document a binding re-emits>, "summary": {"direction": ..., "kind": ...}}`
- `envelope/invalid/<name>.json` — must be rejected
- `envelope/invalid/<name>.error.json` — `{"error": "<VariantName>"}`

### Error variants

`Malformed` · `SchemaViolation`

Only two, and that says something real about the contract. A
frame arrives as bytes someone handed you, so it can be neither absent (`NotFound`) nor
stamped with a version to dispatch on (`UnsupportedVersion`) — the envelope carries no
version field at all. Compatibility rides on the semver of the published packages and on
kinds being additive, which is why an unrecognized kind is an ordinary
`SchemaViolation` and not a category of its own.

### Where the valid fixtures came from

They are not written by hand against a reading of the schema — that would only test
whether the schema and the fixtures share an author's misconception. Each one is the
reference producer's own serializer output for a value built out of its wire types, and
each was round-tripped through that producer before being written out. So the chain the
corpus asserts is: **bytes a producer actually emits → the schema accepts them → each
binding parses them and re-emits the canonical form → both bindings report the same
discriminators.**

### `canonical` — and why it is compared as values, not bytes

`canonical` is what a conforming binding re-emits after parsing the input. For all but
two fixtures it is identical to the input.

It is compared as a parsed value. Property order is not semantic in JSON, and the two
generators order fields differently — Rust's alphabetically, Python's in schema order —
so a byte comparison would fail on a difference no consumer can observe.

The two fixtures where `canonical` differs from the input are the interesting ones:

- `extra-fields` — an input carrying properties from a newer peer. They are ignored, not
  rejected, and they do not survive re-emission. This pins the "unknown properties are
  ignored" rule in both directions.
- `unit-kind-explicit-null-data` — a kind with no payload, sent with an explicit
  `"data": null`. Accepted, and re-emitted without the redundant property.

### `summary` — why a round-trip alone is not enough

Two bindings can both round-trip a frame perfectly while disagreeing about which branch
of a union they parsed it into: a discriminator read as the wrong arm re-emits
identically whenever the payload happens to be shaped the same. `summary` records the
direction and kind each binding actually landed on, read off the validated model rather
than off the input file — reading the input back would assert only that the file says
what it says.

### Coverage is asserted, not hoped for

Both bindings check that every `EventKind` and every `BusCommand` branch in the schema is
exercised by some fixture. A contract whose corpus covers two thirds of its vocabulary is
two thirds tested, and the untested third is exactly where a generator change goes
unnoticed.

## `envelope/divergent/` — where the bindings disagree, pinned

Most fixtures belong in `valid/` or `invalid/` because one verdict is true of everything
that reads them. A `divergent/` fixture is one where that is not so: the schema, the Rust
binding and the Python binding do not all agree, so filing it under either heading would
require asserting something false.

- `envelope/divergent/<name>.json` — the input
- `envelope/divergent/<name>.verdict.json` —
  `{"property": ..., "schema": "accepts"|"rejects", "bindings": {"rust": ..., "python": ...}, "canonical": <present when some binding accepts>}`

Each verdict is asserted where it can be: the schema's by `validate_corpus.py`, each
binding's by that binding's own suite. Where a binding accepts, it must also normalize to
`canonical` — accepting is only half the claim, and without the second half "accepts"
could be hiding a silent misread rather than recording a tolerance. `validate_corpus.py`
additionally refuses a fixture whose recorded bindings *agree*, since that one is not
divergent and belongs in `valid/` or `invalid/` where it gets asserted far more
thoroughly.

### The one divergence there today

Every fixture in `divergent/` omits a property this contract marks
required-and-nullable — `name`, `tool`, `note`, `agents`, `resume`, `gap`; the complete
set, not a sample, because the divergence is a property of the rule rather than of any one
field. The schema rejects the omission. The Rust binding accepts it and reads the property
back as the null a producer would have written, because serde defaults an absent optional.
The Python binding rejects it, because pydantic treats a required field as required.

None of this is reachable from a frame any producer emits — producers always write these
properties — which is why it is recorded rather than resolved.

The root cause constrains future edits, so it is worth stating plainly: **marking one of
these properties unrequired would not fix the asymmetry, it would move it.** Generated
code drops an unrequired property when re-emitting, so a generated client would stop
writing a field that every producer writes. Requiring it confines the disagreement to
documents nobody sends. That is the trade.

### Why these are tested and not merely written down

A documented divergence becomes an *undocumented* one the moment someone regenerates the
bindings with different flags, and nothing else in the suite would notice — these inputs
are deliberately absent from `valid/` and `invalid/`, so no other test reads them. Pinning
all three verdicts means a shift in any one of them fails loudly and has to be re-recorded
deliberately. The same instinct as the `--strict-types int` fixture below: the way to keep
a known quirk from rotting into an unknown one is to make something fail when it moves.

## A divergence that was fixed rather than pinned

**Numeric-string coercion.** pydantic's default lax mode reads `"4210"` into an integer
field. The Rust binding and the schema both reject it. This one *is* fixed rather than
documented: the Python bindings are generated with `--strict-types int`, and the
`mail-id-not-integer` fixture fails loudly if that flag is ever dropped. Note that
whole-model `strict=True` is not the same remedy and is wrong here — it also refuses to
read a plain string into a generated enum, which rejects most of the corpus.

## Adding a case

Add the input and its expectation file together. `validate_corpus.py` fails on any
fixture missing its pair, so an unpaired file cannot slip through. For an envelope
fixture, prefer generating the input from the reference producer over writing it out by
hand; if you must write one directly, a fixture that the producer would never emit
belongs in `invalid/`, not `valid/`.

## Running the corpus

`format: "date-time"` is annotation-only under JSON Schema 2020-12. `jsonschema` checks it
only when the validator is built with `format_checker=jsonschema.FormatChecker()`, which
`validate_corpus.py` does, and even then only when the optional `rfc3339-validator` package
is installed. Without that package, a malformed value such as `"last tuesday"` is silently
accepted. The envelope has no `date-time` field today. The package is installed anyway, so
that the first such field is actually checked, not just annotated.

```bash
uv run --with jsonschema --with referencing --with rfc3339-validator python conformance/validate_corpus.py
```

Expected output:

```
OK: envelope: 49 valid + 30 invalid + 6 divergent
```
