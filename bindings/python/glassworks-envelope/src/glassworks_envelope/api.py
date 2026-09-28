"""The bus wire envelope: typed events and commands.

This package owns the *contract*, not the traffic. It parses and emits frames; it
opens no socket and holds no state, because a wire type that also knows how to
connect stops being usable by the side that does not connect the same way.

Every model is generated from `schema/envelope.schema.json` by `make gen`. What
is written directly here is only the thin edge the schema cannot express: the
parse entry point, the error taxonomy, and `summary`.

The two failure modes are kept apart on purpose. `Malformed` means the bytes were
not JSON; `SchemaViolation` means they were JSON that this contract does not
describe. They call for different responses — the first is a transport or framing
fault, the second is a peer disagreeing with you about the contract, most often a
peer that is newer than you. Collapsing them would leave an operator unable to
tell a corrupted frame from a version skew, which are not remotely the same
incident.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

import pydantic

from ._generated import Envelope


class EnvelopeError(Exception):
    """Base class for every frame read failure."""

    variant: str = "EnvelopeError"


class Malformed(EnvelopeError):
    """The bytes are not JSON at all."""

    variant = "Malformed"


class SchemaViolation(EnvelopeError):
    """The bytes are JSON, but not a frame this contract describes."""

    variant = "SchemaViolation"


def _reject_non_standard_constant(constant: str) -> float:
    """Rejects `NaN` / `Infinity` / `-Infinity`.

    Python's `json` module accepts these by default; the Rust binding's parser
    treats them as malformed, and JSON itself has no such literals. Matching the
    stricter reading here keeps the two bindings' accept/reject boundary
    identical, which is the whole point of running one corpus in two languages.
    """
    raise ValueError(f"non-standard JSON literal is not allowed: {constant}")


def parse(text: str | bytes) -> Envelope:
    """Reads one frame.

    Malformed-versus-violating is decided the same way as in the Rust binding:
    whether the bytes parse as JSON at all. Validating a second time against the
    schema document would be a second, divergent opinion about the same bytes —
    and the generated models *are* the schema, so the only thing a second opinion
    can add is a way for the two to disagree.
    """
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Malformed(f"frame is not valid UTF-8: {exc}") from exc

    try:
        raw = json.loads(text, parse_constant=_reject_non_standard_constant)
    except ValueError as exc:
        # json.JSONDecodeError (malformed JSON) is a ValueError subclass; a
        # rejected NaN/Infinity literal is a plain ValueError. Both are Malformed.
        raise Malformed(f"frame is not valid JSON: {exc}") from exc

    try:
        return Envelope.model_validate(raw)
    except pydantic.ValidationError as exc:
        raise SchemaViolation(f"frame does not match the envelope contract: {exc}") from exc


def to_dict(envelope: Envelope) -> dict[str, Any]:
    """Writes one frame as a plain dictionary.

    `exclude_unset` is what makes this agree with the Rust binding rather than
    merely resemble it. A property this contract leaves *unrequired* — `trace`,
    `parent_span_id` — is one a producer omits entirely, and the generated Rust
    type skips it when serialising; pydantic would otherwise write it as an
    explicit null and the two bindings would emit different bytes for the same
    value. A required-but-nullable property was necessarily set during
    validation, so it survives this and is written as the null a producer writes.

    `by_alias` is equally load-bearing, for a duller reason: `MailArrived.from` is
    a Python keyword, so the generated model calls the attribute `from_` and
    carries the wire name as an alias. Dumping without the alias would put
    `from_` on the wire — accepted by nothing, and visible only as one failing
    fixture out of fifty.
    """
    return envelope.model_dump(mode="json", exclude_unset=True, by_alias=True)


def to_json(envelope: Envelope) -> str:
    """Writes one frame."""
    return json.dumps(to_dict(envelope), separators=(",", ":"))


class Summary(NamedTuple):
    """The discriminators a binding read out of a frame. See `summary`."""

    direction: str
    kind: str


def summary(envelope: Envelope) -> Summary:
    """What a frame *is*, in two strings: its direction and its kind.

    This exists for the conformance corpus, and it earns its place there. Two
    bindings can both round-trip a frame byte-for-byte while disagreeing about
    which branch of a union they parsed it into — a discriminator read as the
    wrong arm re-emits identically if the payload happens to be shaped the same.
    Asserting the discriminator each binding actually landed on closes that gap.

    Read off the validated models rather than off the input dictionary: reading
    the raw JSON would assert only that the corpus file says what it says, which
    is not a test of anything.
    """
    body = envelope.body.root
    if body.direction == "Event":
        return Summary("Event", body.payload.kind.root.kind)
    return Summary("Command", body.payload.root.kind)
