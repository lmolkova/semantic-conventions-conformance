#!/usr/bin/env bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
#
# Resolve a semantic-convention registry into the model a coverage reduction
# reads: per span type, event and metric, the requirement level of every
# attribute it declares. Weaver does the work — see the filter in
# weaver-templates/coverage-model/weaver.yaml.
#
# A session runs this when the model a pin needs isn't there yet. Run it by
# hand to see what weaver resolved.
#
# Usage: collect-coverage-model.sh <registry> <output.json>

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $(basename "$0") <registry> <output.json>" >&2
  exit 2
fi

command -v weaver >/dev/null || {
  echo "weaver not found on PATH — install it from" \
       "https://github.com/open-telemetry/weaver/releases" >&2
  exit 1
}

registry=$1
output=$2
here=$(cd "$(dirname "$0")" && pwd)

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
