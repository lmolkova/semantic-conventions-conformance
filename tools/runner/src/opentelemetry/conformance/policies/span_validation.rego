# Span invariants that hold for every set of semantic conventions.
#
# The registry validates per-attribute requirements for the signals it
# defines. These are cross-cutting rules it can't express, and none of them
# are about any one domain — they come from the trace API spec and from the
# general semconv guidance on `error.type`. A domain's own policies are loaded
# alongside these.
#
# Helpers are prefixed `_otel_` rather than shared with a domain's file: every
# policy file weaver loads lands in this one package, and two definitions of
# the same helper name would collide.

package live_check_advice

import rego.v1

# ─── Span status ────────────────────────────────────────────────────────────
#
# Instrumentation libraries MUST NOT set span status to OK — that value is
# reserved for application code that has explicitly verified the call
# succeeded. Leave it UNSET on success, ERROR on failure.
# https://opentelemetry.io/docs/specs/otel/trace/api/#set-status

deny contains _otel_span_finding(
	"span_status_ok_set_by_instrumentation",
	"violation",
	input.sample.span,
	{"status_code": input.sample.span.status.code},
	sprintf(
		"Span '%v' has status.code='ok'; instrumentations must leave status UNSET on success (OK is reserved for application code).",
		[input.sample.span.name],
	),
) if {
	input.sample.span
	input.sample.span.status.code == "ok"
}

# ─── error.type on failure ──────────────────────────────────────────────────
#
# Semconv requires `error.type` when an operation fails. The registry can't
# express this — it's conditional on span status — so check both directions.

deny contains _otel_span_finding(
	"error_type_missing_on_error",
	"violation",
	input.sample.span,
	{"status_code": input.sample.span.status.code},
	sprintf(
		"Span '%v' has status.code='error' but is missing 'error.type'; it MUST be set when the operation fails.",
		[input.sample.span.name],
	),
) if {
	input.sample.span
	input.sample.span.status.code == "error"
	not _otel_has_attr(input.sample.span, "error.type")
}

deny contains _otel_span_finding(
	"error_type_without_error_status",
	"violation",
	input.sample.span,
	{"status_code": input.sample.span.status.code},
	sprintf(
		"Span '%v' sets 'error.type'='%v' but status.code is '%v', not 'error'.",
		[input.sample.span.name, _otel_attr_value(input.sample.span, "error.type"), input.sample.span.status.code],
	),
) if {
	input.sample.span
	_otel_has_attr(input.sample.span, "error.type")
	input.sample.span.status.code != "error"
}

# ─── Helpers ────────────────────────────────────────────────────────────────
#
# Span attributes arrive as `[{"name": ..., "value": ..., "type": ...}]`.

_otel_has_attr(span, name) if {
	some attr in span.attributes
	attr.name == name
}

_otel_attr_value(span, name) := value if {
	some attr in span.attributes
	attr.name == name
	value := attr.value
}

# PolicyFinding format per
# https://github.com/open-telemetry/weaver/blob/main/crates/weaver_live_check/README.md#policyfinding
_otel_span_finding(id, level, span, context, message) := {
	"id":          id,
	"level":       level,
	"signal_type": "span",
	"signal_name": span.name,
	"context":     context,
	"message":     message,
}
