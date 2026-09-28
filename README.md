# glassworks-envelope

The wire envelope for an agent session bus: the frame every event and command travels in,
defined once as a JSON Schema and generated into Rust and Python bindings, with a
conformance corpus that proves the bindings agree.

**Status: 0.1, in use.** The reference client is [Ember](https://github.com/kingb/ember).
The reference producer is a session daemon that is not yet public. Changes follow
[`docs/GOVERNANCE.md`](docs/GOVERNANCE.md).

## What this is

A **schema-first contract repository**. `schema/envelope.schema.json` is normative: the
source of truth. Rust and Python types are generated from it and **committed**, so
consumers need no code-generation toolchain. `conformance/` holds a language-neutral
fixture corpus that every binding must execute identically.

The valid fixtures are not written by hand. Each one is the reference producer's own
serializer output, so the corpus asserts a chain: bytes a producer actually emits → the
schema accepts them → each binding parses them and re-emits the same document. See
[`conformance/README.md`](conformance/README.md).

## Layout

    schema/           envelope.schema.json, the source of truth
    bindings/rust/    the glassworks-envelope crate
    bindings/python/  the glassworks-envelope package
    conformance/      the shared fixture corpus and its validators
    docs/             governance

Files named `generated.rs` and `_generated.py` are produced by `make gen` and carry a
do-not-edit banner. Everything else is hand-written.

## Two conventions that are easy to get backwards

- **Unknown properties are ignored, never rejected.** A frame from a newer peer carrying a
  property you have never heard of is a valid frame. Nothing in the schema sets
  `additionalProperties: false`, and that is deliberate.
- **`required` means "the producer always writes it", not "it cannot be null".** Several
  properties are required *and* nullable (`name`, `tool`, `note`, `agents`, `resume`,
  `gap`): a producer writes them as null rather than leaving them out. Generated code drops
  an unrequired property when it re-emits, so the distinction decides whether a client's
  output still looks like a producer's.

## Usage

Reading a frame off the bus, in Rust:

```rust
use glassworks_envelope::{Body, EventKind, parse};

match parse(frame)?.body {
    Body::Event(event) => match event.kind {
        EventKind::GateRequested(gate) => present(gate),   // a human is needed
        _ => {}
    },
    Body::Command(_) => {}                                  // client -> bus
}
```

and in Python:

```python
from glassworks_envelope import parse, summary

envelope = parse(frame)
direction, kind = summary(envelope)
```

**Decode frame by frame, and skip a frame that fails.** The generated enums have no
catch-all variant, so a frame carrying a kind your version does not know fails to decode
as a `SchemaViolation` in both bindings. It does not decode to "unknown". A newer peer
is normal, so drop that one frame and keep reading the stream.

`parse` distinguishes its two failure modes on purpose. `Malformed` means the bytes were
not JSON. `SchemaViolation` means they were JSON this contract does not describe, which
usually means the peer is newer than you; report it as that, not as a corrupt frame.

## Development

    make gen           regenerate the bindings from the schema
    make check-gen     fail if the committed bindings are stale
    make check-schema  validate the schema and the corpus
    make test          everything

Use the `make` targets rather than running `conformance/validate_corpus.py` directly:
`make check-schema` supplies the `rfc3339-validator` package the corpus check needs, and a
bare `python` invocation does not.

### Verifying the `check-gen` freshness gate

`check-gen` depends on `gen`, so it regenerates the bindings before diffing. Drift appended
to a generated file in the working tree is overwritten before the diff runs, so the command
exits 0. That is not the gate working; it is the gate never seeing the change. The gate
guards **committed** generated code, so verification has to target that:

```bash
SAFE=$(git rev-parse HEAD)
make check-gen                    # baseline: exit 0
printf '\n// deliberate drift\n' >> bindings/rust/glassworks-envelope/src/generated.rs
git add -A && git commit -m "TEMP drift test"
make check-gen                    # MUST fail, non-zero
git reset --hard "$SAFE"          # discard the temporary commit
make check-gen                    # passes again
git status --short                # empty
```

## License

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or
[MIT license](LICENSE-MIT) at your option.
