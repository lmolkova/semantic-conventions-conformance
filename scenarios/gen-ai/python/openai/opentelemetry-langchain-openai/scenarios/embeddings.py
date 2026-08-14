# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: OpenAI embeddings, through langchain."""

from langchain_openai import OpenAIEmbeddings

OpenAIEmbeddings(
    model="text-embedding-3-small", dimensions=256
).embed_documents(["Say this is a test", "And this is another one"])
