"""Text demonstration of the Zvtakum instructions and the SpMV kernel."""
from fractions import Fraction

from .codec import TakumFormat
from .spmv import CSR, Variant, count_instructions, reference_spmv, spmv_simulated
from .zvtakum import TakumVectorMachine


def show(values):
    return "[" + ", ".join("NaR" if v is None else str(v) for v in values) + "]"


def instructions_demo() -> None:
    fmt, wide = TakumFormat(16), TakumFormat(32)
    m = TakumVectorMachine(128, trace=True)
    a = [Fraction(v) for v in ("1.5", "-2", "0.1", "1000")]
    b = [Fraction(v) for v in ("2.25", "0.5", "3", "1e-3")]
    vl = m.vsetvli(len(a), 16)
    for i in range(vl):
        m.set(4, i, 16, fmt.encode(a[i]))
        m.set(5, i, 16, fmt.encode(b[i]))
    print("== Zvtakum, SEW=16 (T16), VLEN=128 ==")
    print("v4 =", show(fmt.decode(m.get(4, i, 16)) for i in range(vl)))
    print("v5 =", show(fmt.decode(m.get(5, i, 16)) for i in range(vl)))
    for name in ("vtadd_vv", "vtsub_vv", "vtmul_vv"):
        getattr(m, name)(6, 4, 5)
        print(f"{m.trace[-1]}\n    v6 = {show(fmt.decode(m.get(6, i, 16)) for i in range(vl))}")
    m.vsetvli(1, 32, immediate=True)
    m.vmv_s_x(2, 0)
    m.vsetvli(vl, 16)
    m.vtdot_vv(2, 4, 5)
    exact = sum(fmt.decode(m.get(4, i, 16)) * fmt.decode(m.get(5, i, 16)) for i in range(vl))
    print(f"{m.trace[-1]}\n    v2[0] (T32) = {wide.decode(m.get(2, 0, 32))}"
          f"   exact sum = {exact} ~ {float(exact):.10g}")
    for i in range(vl):
        m.set(6, i, 32, wide.encode(a[i] / 3))
    m.vncvt_t_t(8, 6)
    print(f"{m.trace[-1]}\n    T32 {show(wide.decode(m.get(6, i, 32)) for i in range(vl))}"
          f"\n    T16 {show(fmt.decode(m.get(8, i, 16)) for i in range(vl))}")


def spmv_demo() -> None:
    A = CSR.from_triplets(4, 4, [(0, 0, Fraction(4)), (0, 1, Fraction(-1, 3)), (1, 1, Fraction(4)),
                                 (1, 2, Fraction(1, 10)), (2, 2, Fraction(5, 2)), (3, 0, Fraction(1000)),
                                 (3, 3, Fraction(-1, 1000))])
    reference = reference_spmv(A)
    print("\n== SpMV y = A x, x = ones, 4x4 CSR ==")
    print("binary128 reference y ~", [f"{float(v):.10g}" for v in reference])
    y, machine = spmv_simulated(A, Variant("T16", "takum", 16), trace=True)
    print("\nkernel trace for row 0, T16:")
    for line in machine.trace[:16]:
        print("   ", line)
    for variant in (Variant("T16", "takum", 16), Variant("FP16", "ieee", 16)):
        y, machine = spmv_simulated(A, variant)
        counts = count_instructions(A.row_lengths(), variant)
        print(f"{variant.name:>5}: y ~ {[f'{float(v):.6g}' for v in y]}"
              f"  vector={machine.vector_count()} scalar={machine.scalar_count()}"
              f" (formula total {counts['total']})")


def main() -> None:
    instructions_demo()
    spmv_demo()
