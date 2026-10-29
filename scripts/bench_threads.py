"""Compare onnxruntime thread settings for latency stability."""
import statistics
import time

from rapidocr import RapidOCR
from rapidocr.utils.typings import ModelType

IMG = "samples/smoke_test.png"


def bench(label: str, threads: int, runs: int = 3) -> None:
    params = {
        "Global.log_level": "error",
        "Global.use_cls": False,
        "Det.model_type": ModelType.TINY,
        "Rec.model_type": ModelType.TINY,
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.enable_cpu_mem_arena": True,
    }
    eng = RapidOCR(params=params)
    eng(IMG)
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        eng(IMG)
        times.append((time.perf_counter() - t) * 1000)
    print(f"{label:>18} threads={threads}: "
          f"med={statistics.median(times):7.0f} ms  "
          f"min={min(times):7.0f}  max={max(times):7.0f}  all={[round(x) for x in times]}")


if __name__ == "__main__":
    bench("1 thread", 1)
    bench("2 threads", 2)
    bench("default(-1)", -1)
