"""
bench_infer.py — a repeatable "job" to measure: runs exactly N inferences.

Two workloads:
  --model yolo    real object detection with Ultralytics YOLO (pip install ultralytics).
                  Uses one test image over and over so every inference does the same work.
  --model matmul  no dependencies beyond numpy: a fixed stack of matrix multiplies,
                  roughly the arithmetic of a small neural network. Use it to test the
                  measurement pipeline before installing anything heavy.

Model loading happens BEFORE the timed loop. The loop is bracketed by
JOB_START / JOB_END markers so measure_energy.py integrates power over the
inference loop only, not over Python start-up and model loading.

    python3 measure/bench_infer.py --model matmul --n 200
    python3 measure/bench_infer.py --model yolo --n 100 --image test.jpg
"""

import argparse
import time


def mark(tag: str) -> float:
    """Print a timestamp marker. time.monotonic() is the same clock in every process
    on Linux, so measure_energy.py can line these up with its power samples and
    count ONLY the inference loop, not Python start-up or model loading."""
    t = time.monotonic()
    print(f"{tag} {t:.6f}", flush=True)
    return t


def run_matmul(n: int, size: int):
    import numpy as np

    rng = np.random.default_rng(0)
    x = rng.standard_normal((size, size), dtype=np.float32)
    weights = [rng.standard_normal((size, size), dtype=np.float32) for _ in range(4)]
    t0 = mark("JOB_START")
    for _ in range(n):
        h = x
        for w in weights:
            h = np.maximum(h @ w, 0.0)  # linear layer + ReLU
    return mark("JOB_END") - t0


def run_yolo(n: int, image: str, weights: str, imgsz: int):
    import cv2
    from ultralytics import YOLO
    from ultralytics.utils import ASSETS

    # Load the image into memory once, so disk and network reads aren't counted.
    frame = cv2.imread(str(image or ASSETS / "bus.jpg"))
    if frame is None:
        raise SystemExit(f"could not read image {image!r}")
    image = frame
    model = YOLO(weights)
    model.predict(image, imgsz=imgsz, verbose=False)  # warm-up: first call is always slow
    t0 = mark("JOB_START")
    for _ in range(n):
        model.predict(image, imgsz=imgsz, verbose=False)
    return mark("JOB_END") - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["matmul", "yolo"], default="matmul")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--size", type=int, default=256, help="matmul matrix size")
    ap.add_argument("--image", default=None, help="local image (default: the bus.jpg shipped with ultralytics)")
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    if args.model == "matmul":
        elapsed = run_matmul(args.n, args.size)
    else:
        elapsed = run_yolo(args.n, args.image, args.weights, args.imgsz)
    print(f"{args.n} inferences in {elapsed:.2f} s -> {elapsed / args.n * 1000:.1f} ms each")


if __name__ == "__main__":
    main()
