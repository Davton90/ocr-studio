"""Benchmark PP-OCRv6 model variants (tiny / small / medium) on this machine."""
import time

from rapidocr import RapidOCR
from rapidocr.utils.typings import ModelType, OCRVersion

IMG = "samples/smoke_test.png"


def run(label: str, params: dict) -> None:
    try:
        t0 = time.perf_counter()
        eng = RapidOCR(params=params)
        load = time.perf_counter() - t0

        eng(IMG)  # warm-up
        times = []
        res = None
        for _ in range(2):
            t = time.perf_counter()
            res = eng(IMG)
            times.append((time.perf_counter() - t) * 1000)

        txts = () if res.txts is None else tuple(res.txts)
        avg = sum(times) / len(times)
        print(f"\n[{label}] load={load:.2f}s  infer={avg:.0f} ms  lines={len(txts)}")
        for t in txts:
            print(f"    - {t}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[{label}] FAILED: {type(exc).__name__}: {exc}")


def variant(mt: ModelType, det_side: int = 736) -> dict:
    return {
        "Global.log_level": "error",
        "Global.use_cls": False,
        "Det.ocr_version": OCRVersion.PPOCRV6,
        "Det.model_type": mt,
        "Det.limit_side_len": det_side,
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.model_type": mt,
    }


if __name__ == "__main__":
    run("v6-tiny", variant(ModelType.TINY))
    run("v6-small", variant(ModelType.SMALL))
    run("v6-medium", variant(ModelType.MEDIUM))
    run("v6-small@640", variant(ModelType.SMALL, 640))
    run("v6-tiny@640", variant(ModelType.TINY, 640))
