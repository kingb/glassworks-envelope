"""Prove each schema actually discriminates: every valid/ fixture validates,
every invalid/ fixture fails, and every fixture has its expectation file.

This is language-neutral. It checks the SCHEMAS, not any binding. Bindings run
the same corpus in their own tests; a disagreement fails CI.
"""

import json
import pathlib
import sys

import jsonschema

ROOT = pathlib.Path(__file__).parent
SCHEMA_DIR = ROOT.parent / "schema"

# Per-corpus configuration. `errors` is the closed set of error variants the
# bindings may declare, and `expect_keys` the keys every expectation file must
# carry. Kept as a table so that a second contract can be added beside this one
# without restructuring the checks.
CORPORA = {
    "envelope": {
        "schema": "envelope.schema.json",
        "errors": {"Malformed", "SchemaViolation"},
        "expect_keys": ("canonical", "summary"),
        "pre_schema_errors": {"Malformed"},
        # Inputs that live in neither valid/ nor invalid/ because no single
        # verdict is true of every binding. Each fixture records all three
        # verdicts; the schema's is asserted here, each binding's in its own
        # suite. See conformance/README.md.
        "divergent": True,
    },
}


def inputs(directory: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        p for p in directory.glob("*.json")
        if not p.name.endswith((".expect.json", ".error.json", ".verdict.json"))
    )


def check_corpus(name: str, config: dict) -> tuple[list[str], int, int]:
    failures: list[str] = []
    schema = json.loads((SCHEMA_DIR / config["schema"]).read_text())
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())

    valid_dir = ROOT / name / "valid"
    invalid_dir = ROOT / name / "invalid"
    valid_inputs = inputs(valid_dir)
    invalid_inputs = inputs(invalid_dir)

    if not valid_inputs:
        failures.append(f"{name}: no fixtures in valid/")
    if not invalid_inputs:
        failures.append(f"{name}: no fixtures in invalid/")

    for path in valid_inputs:
        expect = path.with_suffix(".expect.json")
        if not expect.exists():
            failures.append(f"{name}/{path.name}: missing {expect.name}")
            continue
        payload = json.loads(expect.read_text())
        missing = [k for k in config["expect_keys"] if k not in payload]
        if missing:
            failures.append(f"{name}/{expect.name}: needs {', '.join(missing)}")
        try:
            validator.validate(json.loads(path.read_text()))
        except jsonschema.exceptions.ValidationError as exc:
            failures.append(
                f"{name}/{path.name}: expected valid, schema rejected it: {exc.message}"
            )

    for path in invalid_inputs:
        errfile = path.with_suffix(".error.json")
        if not errfile.exists():
            failures.append(f"{name}/{path.name}: missing {errfile.name}")
            continue
        declared = json.loads(errfile.read_text()).get("error")
        if declared not in config["errors"]:
            failures.append(f"{name}/{errfile.name}: unknown error variant {declared!r}")
            continue
        if declared in config["pre_schema_errors"]:
            # Declared to fail before schema validation is reached. Still check
            # the claim is honest: a fixture declared Malformed that happens to
            # parse as JSON is mislabelled, and would leave the schema untested
            # for whatever it actually contains.
            if declared == "Malformed":
                try:
                    json.loads(path.read_text())
                except ValueError:
                    continue
                failures.append(
                    f"{name}/{path.name}: declared Malformed but parses as JSON"
                )
            continue
        try:
            raw = json.loads(path.read_text())
        except ValueError:
            failures.append(
                f"{name}/{path.name}: declared {declared} but is not parseable JSON"
            )
            continue
        try:
            validator.validate(raw)
            failures.append(
                f"{name}/{path.name}: expected schema to reject it, but it validated"
            )
        except jsonschema.exceptions.ValidationError:
            pass

    if config.get("divergent"):
        failures.extend(check_divergent(name, validator))

    return failures, len(valid_inputs), len(invalid_inputs)


def check_divergent(name: str, validator) -> list[str]:
    """Assert the schema's own verdict on each divergent fixture.

    A divergent fixture is one the bindings disagree about, so it cannot be filed
    as valid or invalid. The schema still has an opinion, and that opinion is the
    stable one — it is what makes the disagreement legible rather than a puzzle.
    Recording it and checking it here means a schema change that silently starts
    accepting these inputs fails loudly, instead of leaving two bindings
    disagreeing about a document the contract now considers ordinary.
    """
    failures: list[str] = []
    directory = ROOT / name / "divergent"
    if not directory.is_dir():
        return [f"{name}: divergent/ is declared but missing"]

    fixtures = inputs(directory)
    if not fixtures:
        return [f"{name}: no fixtures in divergent/"]

    for path in fixtures:
        verdict_path = path.with_suffix(".verdict.json")
        if not verdict_path.exists():
            failures.append(f"{name}/divergent/{path.name}: missing {verdict_path.name}")
            continue
        verdict = json.loads(verdict_path.read_text())

        for key in ("property", "schema", "bindings"):
            if key not in verdict:
                failures.append(f"{name}/divergent/{verdict_path.name}: needs {key}")
        recorded = verdict.get("schema")
        if recorded not in {"accepts", "rejects"}:
            failures.append(
                f"{name}/divergent/{verdict_path.name}: unknown schema verdict {recorded!r}"
            )
            continue

        # A fixture every binding agrees on is not divergent and should not be
        # filed here — it belongs in valid/ or invalid/, where it gets asserted
        # much more thoroughly.
        recorded_bindings = set(verdict.get("bindings", {}).values())
        if len(recorded_bindings) < 2:
            failures.append(
                f"{name}/divergent/{verdict_path.name}: bindings agree "
                f"({recorded_bindings}); this belongs in valid/ or invalid/"
            )

        try:
            validator.validate(json.loads(path.read_text()))
            observed = "accepts"
        except jsonschema.exceptions.ValidationError:
            observed = "rejects"
        except ValueError:
            failures.append(f"{name}/divergent/{path.name}: not parseable JSON")
            continue

        if observed != recorded:
            failures.append(
                f"{name}/divergent/{path.name}: schema {observed} it, "
                f"but the verdict records {recorded}. The divergence has moved — "
                f"re-record it deliberately."
            )

    return failures


def main() -> int:
    failures: list[str] = []
    counts: list[str] = []

    present = {p.name for p in ROOT.iterdir() if p.is_dir()}
    for unlisted in sorted(present - set(CORPORA)):
        failures.append(f"{unlisted}/ is a corpus directory but is not checked here")

    for name, config in CORPORA.items():
        corpus_failures, n_valid, n_invalid = check_corpus(name, config)
        failures.extend(corpus_failures)
        n_div = len(inputs(ROOT / name / "divergent")) if config.get("divergent") else 0
        tail = f" + {n_div} divergent" if n_div else ""
        counts.append(f"{name}: {n_valid} valid + {n_invalid} invalid{tail}")

    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        return 1
    print("OK: " + "; ".join(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
