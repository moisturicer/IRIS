"""Build-time patch of docling's formula model. Fails the build if it cannot apply.

docling hardcodes two numbers and drops a batch on out-of-memory:
  * max_new_tokens=2048  -> one malformed formula holds its whole batch for minutes
  * elements_batch_size=5 -> leaves the GPU mostly idle
  * an OOM batch is logged and returned EMPTY -> every formula in it vanishes
The last matters most once the GPU is capped: the fix is to split the batch and
retry it, so memory pressure costs a little time instead of data.

It also hooks iris_gpu_cap.apply() into docling-serve's create_app.

Usage: patch_docling.py MAX_NEW_TOKENS BATCH_SIZE
"""

import importlib.util
import sys
from pathlib import Path

max_tokens, batch = sys.argv[1], sys.argv[2]
spec = importlib.util.find_spec("docling.models.stages.code_formula.code_formula_vlm_model")
path = Path(spec.origin)
text = path.read_text(encoding="utf-8")

HELPER = '''

def _predict_halving_on_oom(engine, inputs):
    """IRIS patch: split and retry a batch that runs out of GPU memory."""
    try:
        return engine.predict_batch(inputs)
    except Exception as exc:
        if "out of memory" not in str(exc).lower():
            raise
        import torch
        from types import SimpleNamespace

        torch.cuda.empty_cache()
        if len(inputs) == 1:
            # Alone and still too big: lose this formula, not the whole batch.
            _log.error(f"Formula skipped, out of GPU memory even alone: {exc}")
            return [SimpleNamespace(text="")]
        mid = len(inputs) // 2
        return _predict_halving_on_oom(engine, inputs[:mid]) + _predict_halving_on_oom(
            engine, inputs[mid:]
        )

'''

swaps = [
    ("max_new_tokens=2048,", f"max_new_tokens={max_tokens},"),
    ("elements_batch_size = 5", f"elements_batch_size = {batch}"),
    (
        "batch_outputs = self.engine.predict_batch(engine_inputs)",
        "batch_outputs = _predict_halving_on_oom(self.engine, engine_inputs)",
    ),
]
for old, new in swaps:
    if text.count(old) != 1:
        sys.exit(f"patch_docling: expected exactly one {old!r} in {path}, found {text.count(old)}")
    text = text.replace(old, new)

marker = "\nclass "
at = text.index(marker)
text = text[:at] + HELPER + text[at:]
path.write_text(text, encoding="utf-8")
print(f"patch_docling: patched {path}")

app_path = Path(importlib.util.find_spec("docling_serve.app").origin)
app_text = app_path.read_text(encoding="utf-8")
hook_at = "def create_app():  # noqa: C901\n"
if app_text.count(hook_at) != 1:
    sys.exit(f"patch_docling: expected exactly one create_app in {app_path}")
app_text = app_text.replace(
    hook_at, hook_at + "    import iris_gpu_cap\n\n    iris_gpu_cap.apply()\n\n"
)
app_path.write_text(app_text, encoding="utf-8")
print(f"patch_docling: hooked the GPU cap into {app_path}")
