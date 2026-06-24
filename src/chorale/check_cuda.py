from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Print Project 1 PyTorch/CUDA runtime information.")
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()

    print(f"Python executable: {sys.executable}")
    try:
        import torch
    except Exception as exc:
        print(f"torch import failed: {exc}")
        if args.require_cuda:
            raise SystemExit(2)
        return

    print(f"torch version: {torch.__version__}")
    available = torch.cuda.is_available()
    print(f"torch.cuda.is_available(): {available}")
    if available:
        index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        print(f"CUDA device name: {torch.cuda.get_device_name(index)}")
        print(f"CUDA device memory: {props.total_memory / (1024 ** 3):.2f} GiB")
    else:
        print("CUDA device name: NONE")
        print("CUDA device memory: NONE")
        if args.require_cuda:
            print(
                "Full RTX experiment requires CUDA. Use scripts/smoke_project1.ps1 for CPU smoke, "
                "or pass -CpuDebug only for explicit debugging."
            )
            raise SystemExit(2)


if __name__ == "__main__":
    main()
