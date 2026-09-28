//! The bus wire envelope: typed events and commands.
//!
//! This crate owns the *contract*, not the traffic. It parses and emits frames;
//! it opens no socket and holds no state, because a wire type that also knows
//! how to connect stops being usable by the side that does not connect the same
//! way.
//!
//! Every type below is generated from `schema/envelope.schema.json` by
//! `make gen`. What is written directly here is only the thin edge the schema
//! cannot express: the parse entry point, the error taxonomy, and [`summary`].
//!
//! # Parsing
//!
//! ```
//! # use glassworks_envelope::{parse, Body};
//! let frame = r#"{"seq":1,"at":0,"body":{"direction":"Command","payload":{"kind":"Snapshot"}}}"#;
//! let envelope = parse(frame).expect("a well-formed frame");
//! assert!(matches!(envelope.body, Body::Command(_)));
//! ```
//!
//! # The two failure modes are kept apart on purpose
//!
//! [`EnvelopeError::Malformed`] means the bytes were not JSON;
//! [`EnvelopeError::SchemaViolation`] means they were JSON that this contract
//! does not describe. They call for different responses — the first is a
//! transport or framing fault, the second is a peer disagreeing with you about
//! the contract, most often a peer that is newer than you. Collapsing them into
//! one error would leave an operator unable to tell a corrupted frame from a
//! version skew, which are not remotely the same incident.

mod generated;

pub use generated::*;

/// Why a frame could not be read.
#[derive(Debug, thiserror::Error)]
pub enum EnvelopeError {
    /// The bytes are not JSON at all.
    #[error("frame is not valid JSON: {detail}")]
    Malformed {
        /// The underlying parser's description.
        detail: String,
    },

    /// The bytes are JSON, but not a frame this contract describes.
    #[error("frame does not match the envelope contract: {detail}")]
    SchemaViolation {
        /// The underlying parser's description, including the path it failed at.
        detail: String,
    },
}

/// Reads one frame.
///
/// The two error variants are separated by the parser's own classification of
/// the failure rather than by a second validation pass: a syntax fault is
/// [`EnvelopeError::Malformed`], and a well-formed document that does not fit
/// the types is an [`EnvelopeError::SchemaViolation`]. Running the document
/// through a JSON Schema validator first would be a second, divergent opinion
/// about the same bytes — and the generated types *are* the schema, so the only
/// thing a second opinion can add is a way for the two to disagree.
pub fn parse(text: &str) -> Result<Envelope, EnvelopeError> {
    serde_json::from_str(text).map_err(|e| {
        let detail = e.to_string();
        match e.classify() {
            serde_json::error::Category::Data => EnvelopeError::SchemaViolation { detail },
            _ => EnvelopeError::Malformed { detail },
        }
    })
}

/// Writes one frame.
///
/// # Panics
///
/// Does not panic in practice: every type in this crate is a plain data type
/// whose `Serialize` cannot fail, and the only documented failure of
/// `serde_json::to_string` for such a type is a map with non-string keys, which
/// this contract has none of.
#[must_use]
pub fn to_json(envelope: &Envelope) -> String {
    serde_json::to_string(envelope).expect("wire types serialize infallibly")
}

/// What a frame *is*, in two strings: its direction and its kind.
///
/// This exists for the conformance corpus, and it earns its place there. Two
/// bindings can both round-trip a frame byte-for-byte while disagreeing about
/// which variant they parsed it into — a discriminator read as the wrong arm of
/// a union re-emits identically if the payload happens to be shaped the same.
/// Asserting the discriminator each binding actually landed on closes that gap,
/// and the exhaustive match below means a kind added to the schema cannot pass
/// silently: this stops compiling until someone names it.
#[must_use]
pub fn summary(envelope: &Envelope) -> Summary {
    match &envelope.body {
        Body::Event(event) => Summary {
            direction: "Event",
            kind: event_kind_name(&event.kind),
        },
        Body::Command(command) => Summary {
            direction: "Command",
            kind: command_kind_name(command),
        },
    }
}

/// The discriminators a binding read out of a frame. See [`summary`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Summary {
    /// `"Event"` or `"Command"`.
    pub direction: &'static str,
    /// The event kind or command kind name.
    pub kind: &'static str,
}

fn event_kind_name(kind: &EventKind) -> &'static str {
    match kind {
        EventKind::AgentAppeared { .. } => "AgentAppeared",
        EventKind::AgentStatus(_) => "AgentStatus",
        EventKind::AgentView(_) => "AgentView",
        EventKind::AgentExited { .. } => "AgentExited",
        EventKind::AgentActivity { .. } => "AgentActivity",
        EventKind::GateRequested(_) => "GateRequested",
        EventKind::GateAnswered { .. } => "GateAnswered",
        EventKind::MailArrived { .. } => "MailArrived",
        EventKind::MemoryInjected { .. } => "MemoryInjected",
        EventKind::CurationProposed { .. } => "CurationProposed",
        EventKind::GateVoided { .. } => "GateVoided",
        EventKind::WorkflowStarted { .. } => "WorkflowStarted",
        EventKind::PhaseEntered { .. } => "PhaseEntered",
        EventKind::EvaluationVerdict { .. } => "EvaluationVerdict",
        EventKind::DeviationLogged { .. } => "DeviationLogged",
        EventKind::FanOutStarted { .. } => "FanOutStarted",
        EventKind::LegCompleted { .. } => "LegCompleted",
        EventKind::WorkflowCompleted => "WorkflowCompleted",
        EventKind::WorkflowFailed { .. } => "WorkflowFailed",
    }
}

fn command_kind_name(command: &BusCommand) -> &'static str {
    match command {
        BusCommand::Subscribe { .. } => "Subscribe",
        BusCommand::Snapshot => "Snapshot",
        BusCommand::SpawnAgent { .. } => "SpawnAgent",
        BusCommand::SendInput { .. } => "SendInput",
        BusCommand::SubmitLine { .. } => "SubmitLine",
        BusCommand::Focus { .. } => "Focus",
        BusCommand::Resize { .. } => "Resize",
        BusCommand::GateAnswer { .. } => "GateAnswer",
        BusCommand::Nudge { .. } => "Nudge",
        BusCommand::MailSend(_) => "MailSend",
        BusCommand::RequestFull { .. } => "RequestFull",
        BusCommand::ViewerFocus { .. } => "ViewerFocus",
        BusCommand::Quit { .. } => "Quit",
        BusCommand::Scroll { .. } => "Scroll",
        BusCommand::JumpMark { .. } => "JumpMark",
        BusCommand::Search { .. } => "Search",
    }
}
