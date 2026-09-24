# Extends the upstream docling-serve image to prefetch the CodeFormula
# model at build time (IR-290). The base image ships layout, table
# structure, OCR and figure-classification models only -- confirmed by
# inspecting its model cache directly -- so `do_formula_enrichment` is sent
# and accepted by docling-serve's own API but silently produces zero
# formula elements with nothing to recognize against. See
# docs/testing/TRACEABILITY.md's IR-313 row for how the gap was found.
#
# Runs as the base image's own non-root user and writes into its existing
# cache path, same as every other prefetched model.
FROM quay.io/docling-project/docling-serve:latest

RUN docling-tools models download code_formula
