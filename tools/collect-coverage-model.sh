#!/usr/bin/env bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
#
# Resolve the pinned GenAI registry into the model the coverage reduction
# reads: per span type, event and metric, the requirement level of every
# attribute it declares. Weaver does the work — see the filter in
# weaver-templates/coverage-model/weaver.yaml.
#
# A conformance session runs this on start when the model it needs isn't
# there yet, which is every first run and every run after versions.env moves
# the pin. Run it by hand to refresh one, or to see what weaver resolved.
#
# Usage: tools/collect-coverage-model.sh [output.json]
#
# Both paths default to what the installed package says, which needs the
# registry provisioned; the session passes them in instead ($SEMCONV_REGISTRY,
# $COVERAGE_MODEL), so it never depends on which python3 is on PATH.

set -euo pipefail

command -v weaver >/dev/null || { echo "weaver not found on PATH" >&2; exit 1; }

here=$(cd "$(dirname "$0")" && pwd)
registry=${SEMCONV_REGISTRY:-$(python3 -c \
  'from genai_conformance._registry import semconv_registry; print(semconv_registry())')}
output=${1:-${COVERAGE_MODEL:-$(python3 -c \
  'from genai_conformance._coverage import coverage_model_file; print(coverage_model_file())')}}

generated=$(mktemp -d)
trap 'rm -rf "$generated"' EXIT

weaver registry generate \
  --quiet \
  --v2 \
  --registry "$registry" \
  --templates "$here/weaver-templates" \
  coverage-model \
  "$generated"

mv "$generated/coverage-model.json" "$output"
echo "$output"
