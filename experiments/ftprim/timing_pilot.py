import sys, time, json
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))

def one(args):
    code_name, strat, k, p, ratio, shots = args
    from ftqc_delivery.ftprim import patterns as pat
    from ftqc_delivery.ftprim.sampling import decode_errors
    code = pat.code_by_name(code_name)
    c = pat.memory_pair(code, p, k) if strat == "MEM" else pat.build(code, strat, p, ratio * p, k).circuit
    t0 = time.perf_counter()
    e = decode_errors(c, shots, 1)
    dt = time.perf_counter() - t0
    return f"{code_name} {strat:4s} k={k:2d} p={p:g} r={ratio:g} dets={c.num_detectors:5d} errs={e:3d}/{shots} ms/shot={1e3*dt/shots:8.2f}"

jobs = []
for code, shots in [("SC3", 3000), ("SC5", 600), ("SC7", 150)]:
    for strat, k in [("R", 1), ("R", 2), ("R", 4), ("T", 1), ("T", 2), ("T", 4), ("T_rt", 1), ("T_rt", 2), ("MEM", 12)]:
        jobs.append((code, strat, k, 1e-3, 10, shots))
jobs.append(("[[18,4,4]] BB", "R", 1, 1e-3, 10, 150))
jobs.append(("[[18,4,4]] BB", "T", 1, 1e-3, 10, 150))
with ProcessPoolExecutor(4) as pool:
    for line in pool.map(one, jobs):
        print(line, flush=True)
