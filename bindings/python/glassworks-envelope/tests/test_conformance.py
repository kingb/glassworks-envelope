"""Executes the shared corpus in conformance/envelope/.

The Rust binding runs the identical corpus; a disagreement fails CI.
"""

import json
import pathlib

import pytest

from glassworks_envelope import EnvelopeError, parse, summary, to_dict

REPO = pathlib.Path(__file__).resolve().parents[4]
CORPUS = REPO / "conformance" / "envelope"


def inputs(directory: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        p for p in directory.glob("*.json")
        if not p.name.endswith((".expect.json", ".error.json", ".verdict.json"))
    )


VALID = inputs(CORPUS / "valid")
INVALID = inputs(CORPUS / "invalid")
DIVERGENT = inputs(CORPUS / "divergent")


def test_corpus_is_present():
    assert VALID, f"no valid fixtures in {CORPUS / 'valid'}"
    assert INVALID, f"no invalid fixtures in {CORPUS / 'invalid'}"


@pytest.mark.parametrize("case", VALID, ids=lambda p: p.stem)
def test_valid_fixture_parses_and_re_emits_its_canonical_form(case: pathlib.Path):
    expected = json.loads(case.with_suffix(".expect.json").read_text())
    envelope = parse(case.read_text())

    # Compared as parsed values, not as bytes. Property order is not semantic in
    # JSON and the two languages' generators order fields differently, so a byte
    # comparison would fail on a difference no consumer can observe.
    assert to_dict(envelope) == expected["canonical"], "re-emission"

    # Both bindings must have landed on the same branch of the union, not merely
    # produced the same bytes. See `summary`'s docstring.
    got = summary(envelope)
    assert got.direction == expected["summary"]["direction"], "direction"
    assert got.kind == expected["summary"]["kind"], "kind"


@pytest.mark.parametrize("case", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_is_rejected_with_the_declared_variant(case: pathlib.Path):
    declared = json.loads(case.with_suffix(".error.json").read_text())["error"]
    with pytest.raises(EnvelopeError) as caught:
        parse(case.read_text())
    assert caught.value.variant == declared


@pytest.mark.parametrize("case", DIVERGENT, ids=lambda p: p.stem)
def test_divergent_fixture_matches_this_bindings_recorded_verdict(case: pathlib.Path):
    """Pins the one place the two bindings disagree.

    Every fixture here omits a property the contract marks required-and-nullable.
    The schema rejects it; the Rust binding accepts it and reads the property back
    as the null a producer would have written, because serde defaults an absent
    optional; this binding rejects it, because pydantic treats a required field as
    required. None of it is reachable from a frame any producer emits, and the
    asymmetry is not fixable in a useful direction — see conformance/README.md.

    What this test adds over the write-up is drift protection. A documented
    divergence becomes an *undocumented* one the moment someone regenerates with
    different flags, and nothing else in the suite would notice: these inputs are
    in neither valid/ nor invalid/ precisely because no single verdict is true of
    both bindings. Each verdict file states all three verdicts and each is
    asserted where it can be — the schema's in validate_corpus.py, Rust's in its
    own suite, this one here.
    """
    verdict = json.loads(case.with_suffix(".verdict.json").read_text())
    recorded = verdict["bindings"]["python"]

    if recorded == "rejects":
        with pytest.raises(EnvelopeError):
            parse(case.read_text())
        return

    assert recorded == "accepts", f"unknown verdict {recorded!r}"
    # Accepting is only half the claim: the value accepted must be the one a
    # producer would have sent, or "accepts" hides a silent misread.
    envelope = parse(case.read_text())
    assert to_dict(envelope) == verdict["canonical"], (
        "accepted, but did not normalize to the recorded form"
    )


@pytest.mark.parametrize(
    "directory,suffix",
    [("valid", ".expect.json"), ("invalid", ".error.json"), ("divergent", ".verdict.json")],
)
def test_every_fixture_is_paired_with_its_expectation(directory: str, suffix: str):
    """An unpaired fixture is how a corpus quietly stops asserting anything: the
    case looks present in the directory listing and is skipped by every runner.
    """
    for case in inputs(CORPUS / directory):
        paired = case.with_suffix(suffix)
        assert paired.exists(), f"{case.name} has no {paired.name}"


def test_the_corpus_covers_every_kind_in_the_contract():
    """A wire contract whose corpus covers two thirds of its vocabulary is two
    thirds tested, and the untested third is exactly where a generator change
    goes unnoticed.
    """
    schema = json.loads((REPO / "schema" / "envelope.schema.json").read_text())
    seen = {summary(parse(case.read_text())).kind for case in VALID}

    for definition in ("EventKind", "BusCommand"):
        declared = {
            branch["properties"]["kind"]["const"]
            for branch in schema["$defs"][definition]["oneOf"]
        }
        missing = declared - seen
        assert not missing, f"{definition}: no fixture exercises {sorted(missing)}"
