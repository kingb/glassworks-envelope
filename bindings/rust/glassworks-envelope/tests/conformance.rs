//! Executes the shared corpus in `conformance/envelope/`.
//! The Python binding runs the identical corpus; a disagreement fails CI.

use std::path::{Path, PathBuf};

use glassworks_envelope::{EnvelopeError, parse, summary, to_json};

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR = <repo>/bindings/rust/glassworks-envelope
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repo root")
        .to_path_buf()
}

fn corpus_root() -> PathBuf {
    repo_root().join("conformance/envelope")
}

fn inputs(dir: &Path) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = glob::glob(&format!("{}/*.json", dir.display()))
        .expect("glob")
        .filter_map(Result::ok)
        .filter(|p| {
            let name = p.file_name().unwrap_or_default().to_string_lossy();
            !name.ends_with(".expect.json")
                && !name.ends_with(".error.json")
                && !name.ends_with(".verdict.json")
        })
        .collect();
    out.sort();
    out
}

fn variant_name(err: &EnvelopeError) -> &'static str {
    match err {
        EnvelopeError::Malformed { .. } => "Malformed",
        EnvelopeError::SchemaViolation { .. } => "SchemaViolation",
    }
}

/// Parses every fixture in `dir` and checks it against its expectation file.
fn assert_parses_to_its_canonical_form(dir: &Path) {
    let cases = inputs(dir);
    assert!(!cases.is_empty(), "no fixtures found in {}", dir.display());

    for case in cases {
        let expect_path = case.with_extension("expect.json");
        let expected: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(&expect_path).expect("read expectation"),
        )
        .expect("expectation is JSON");

        let text = std::fs::read_to_string(&case).expect("read fixture");
        let envelope = parse(&text)
            .unwrap_or_else(|e| panic!("{}: expected it to parse, got {e}", case.display()));

        // Compared as parsed values, not as bytes. Property order is not
        // semantic in JSON and the two languages' generators order struct
        // fields differently, so a byte comparison would fail on a difference
        // that no consumer can observe.
        let re_emitted: serde_json::Value =
            serde_json::from_str(&to_json(&envelope)).expect("re-emission is JSON");
        assert_eq!(
            re_emitted,
            expected["canonical"],
            "{}: re-emission differs from the canonical form",
            case.display()
        );

        // Both bindings must have landed on the same arm of the union, not
        // merely produced the same bytes. See `summary`'s documentation.
        let got = summary(&envelope);
        assert_eq!(
            got.direction,
            expected["summary"]["direction"].as_str().unwrap_or_default(),
            "{}: direction",
            case.display()
        );
        assert_eq!(
            got.kind,
            expected["summary"]["kind"].as_str().unwrap_or_default(),
            "{}: kind",
            case.display()
        );
    }
}

#[test]
fn valid_fixtures_parse_and_re_emit_their_canonical_form() {
    assert_parses_to_its_canonical_form(&corpus_root().join("valid"));
}

/// The `divergent/` corpus pins the one place the two bindings disagree.
///
/// Every fixture there omits a property this contract marks required-and-nullable.
/// The schema rejects it; the Rust binding accepts it and reads the property back
/// as the null a producer would have written, because serde defaults an absent
/// `Option` rather than refusing it; the Python binding rejects it, because
/// pydantic treats a required field as required.
///
/// None of that is reachable from a frame any producer emits, and the asymmetry
/// is not fixable in a useful direction — marking those properties unrequired
/// makes generated code *drop* them when re-emitting, so a generated client would
/// stop writing fields every producer writes. See `conformance/README.md`.
///
/// What this test adds over the write-up is drift protection. A documented
/// divergence becomes an *undocumented* one the moment someone regenerates with
/// different flags, and nothing else in the suite would notice: these inputs are
/// in neither `valid/` nor `invalid/` precisely because no single verdict is true
/// of both bindings. Each fixture's verdict file states all three verdicts, and
/// each one is asserted where it can be — the schema's by `validate_corpus.py`,
/// Python's by its own suite, Rust's here.
#[test]
fn divergent_fixtures_match_this_binding_s_recorded_verdict() {
    let dir = corpus_root().join("divergent");
    let cases = inputs(&dir);
    assert!(
        !cases.is_empty(),
        "no divergent fixtures found in {}",
        dir.display()
    );

    for case in cases {
        let verdict: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(case.with_extension("verdict.json"))
                .expect("read verdict"),
        )
        .expect("verdict is JSON");

        let recorded = verdict["bindings"]["rust"]
            .as_str()
            .expect("a recorded rust verdict");
        let text = std::fs::read_to_string(&case).expect("read fixture");

        match (recorded, parse(&text)) {
            ("accepts", Ok(envelope)) => {
                // Accepting is only half the claim. The value it accepted must be
                // the one a producer would have sent, or "accepts" would be
                // hiding a silent misread rather than recording a tolerance.
                let re_emitted: serde_json::Value =
                    serde_json::from_str(&to_json(&envelope)).expect("re-emission is JSON");
                assert_eq!(
                    re_emitted,
                    verdict["canonical"],
                    "{}: accepted, but did not normalize to the recorded form",
                    case.display()
                );
            }
            ("rejects", Err(_)) => {}
            ("accepts", Err(err)) => panic!(
                "{}: recorded as accepted by this binding, but it was rejected ({err}). \
                 The divergence has moved — re-record it deliberately.",
                case.display()
            ),
            ("rejects", Ok(_)) => panic!(
                "{}: recorded as rejected by this binding, but it parsed. \
                 The divergence has moved — re-record it deliberately.",
                case.display()
            ),
            (other, _) => panic!("{}: unknown verdict {other:?}", case.display()),
        }
    }
}

#[test]
fn invalid_fixtures_are_rejected_with_the_declared_variant() {
    let dir = corpus_root().join("invalid");
    let cases = inputs(&dir);
    assert!(
        !cases.is_empty(),
        "no invalid fixtures found in {}",
        dir.display()
    );

    for case in cases {
        let errfile = case.with_extension("error.json");
        let declared: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&errfile).expect("read error file"))
                .expect("error file is JSON");
        let declared = declared["error"].as_str().expect("error variant name");

        let text = std::fs::read_to_string(&case).expect("read fixture");
        match parse(&text) {
            Ok(_) => panic!("{}: expected rejection, it parsed", case.display()),
            Err(err) => assert_eq!(
                variant_name(&err),
                declared,
                "{}: wrong error variant ({err})",
                case.display()
            ),
        }
    }
}

/// Every fixture must carry its expectation file. An unpaired fixture is how a
/// corpus quietly stops asserting anything: the case looks present in the
/// directory listing and is skipped by every runner.
#[test]
fn every_fixture_is_paired_with_its_expectation() {
    for (dir, suffix) in [
        ("valid", "expect.json"),
        ("invalid", "error.json"),
        ("divergent", "verdict.json"),
    ] {
        let dir = corpus_root().join(dir);
        for case in inputs(&dir) {
            let paired = case.with_extension(suffix);
            assert!(
                paired.exists(),
                "{} has no {}",
                case.display(),
                paired.display()
            );
        }
    }
}

/// The corpus must exercise every event kind and every command kind. A wire
/// contract whose corpus covers two thirds of its vocabulary is a contract that
/// is two thirds tested, and the untested third is exactly where a generator
/// change goes unnoticed.
#[test]
fn the_corpus_covers_every_kind_in_the_contract() {
    let schema: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(repo_root().join("schema/envelope.schema.json"))
            .expect("read schema"),
    )
    .expect("schema is JSON");

    let declared = |def: &str| -> Vec<String> {
        schema["$defs"][def]["oneOf"]
            .as_array()
            .expect("a oneOf")
            .iter()
            .filter_map(|branch| branch["properties"]["kind"]["const"].as_str())
            .map(str::to_owned)
            .collect()
    };

    let mut seen: Vec<String> = inputs(&corpus_root().join("valid"))
        .iter()
        .map(|case| {
            let text = std::fs::read_to_string(case).expect("read fixture");
            let envelope = parse(&text).expect("fixture parses");
            summary(&envelope).kind.to_owned()
        })
        .collect();
    seen.sort();
    seen.dedup();

    for def in ["EventKind", "BusCommand"] {
        for kind in declared(def) {
            assert!(
                seen.contains(&kind),
                "{def}::{kind} is in the schema but no fixture exercises it"
            );
        }
    }
}
