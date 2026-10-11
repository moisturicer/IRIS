# Extends a pinned docling-serve image: prefetches the CodeFormula model (IR-290),
# caps formula generation, and caps GPU memory per server process.
#
# DOCLING_BASE picks the runtime. docling/compose.yml builds the GPU variant on
# the cu128 image and the CPU variant on the CPU image; the same code runs on
# either and falls back to CPU by itself when no GPU is visible.
#
# Pinned because `:latest` once dropped the "default" CodeFormula preset and
# failed every extraction.
ARG DOCLING_BASE=quay.io/docling-project/docling-serve-cu128:v1.36.0
FROM ${DOCLING_BASE}

ARG FORMULA_MAX_NEW_TOKENS=768
ARG FORMULA_BATCH_SIZE=16

USER 0
# See patch_docling.py: caps formula generation, raises the batch size, retries an
# out-of-memory batch in halves instead of dropping it, and hooks the GPU cap in.
# The script fails the build if a docling upgrade moves what it patches.
COPY patch_docling.py /tmp/patch_docling.py
RUN python /tmp/patch_docling.py "${FORMULA_MAX_NEW_TOKENS}" "${FORMULA_BATCH_SIZE}" && rm /tmp/patch_docling.py
COPY iris_gpu_cap.py /opt/app-root/lib/python3.12/site-packages/iris_gpu_cap.py
USER 1001

RUN docling-tools models download code_formula

# Less fragmentation when several workers share one capped allocator.
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
