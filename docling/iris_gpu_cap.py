"""Cap this process's GPU memory. Called from docling-serve's create_app (patched in).

Docker cannot limit VRAM and docling-serve has no setting for it, so it is done
inside each serving process. create_app is the right hook because uvicorn starts
extra worker processes by spawning them, and a spawned process inherits no state
from its parent -- only code that runs in the child itself reaches it.

DOCLING_GPU_MEMORY_GB  total cap in GB across all server processes, default 8;
                       0 or negative means no cap.
UVICORN_WORKERS        server processes; each gets an equal share of the cap.
The cap limits tensor memory; each process's CUDA context adds about 0.5 GB.
With no GPU visible this logs once and the server runs on CPU.
"""

import os

_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    _applied = True

    import torch

    if not torch.cuda.is_available():
        print("docling-gpu-cap: no GPU visible, running on CPU", flush=True)
        return

    processes = max(1, int(os.environ.get("UVICORN_WORKERS", "1") or 1))
    total_cap_gb = float(os.environ.get("DOCLING_GPU_MEMORY_GB", "8"))
    props = torch.cuda.get_device_properties(0)
    card_gb = props.total_memory / 2**30
    if total_cap_gb <= 0 or total_cap_gb >= card_gb:
        print(f"docling-gpu-cap: {props.name}, {card_gb:.1f} GB, no cap", flush=True)
        return

    share_gb = total_cap_gb / processes
    torch.cuda.set_per_process_memory_fraction(share_gb / card_gb)
    print(
        f"docling-gpu-cap: {props.name}, {card_gb:.1f} GB card, "
        f"{share_gb:g} GB for this process ({processes} process(es), {total_cap_gb:g} GB total)",
        flush=True,
    )
