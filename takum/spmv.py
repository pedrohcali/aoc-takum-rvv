"""CSR sparse matrix-vector product y = A x for Takum and IEEE formats.

Two implementations share one semantics:

* spmv_simulated runs the vector kernel instruction by instruction on the
  functional machine and counts every instruction;
* spmv_fast computes the same values directly, for the large benchmark.

Tests require bit-identical results from both on synthetic matrices, and
instruction counts from count_instructions equal to the simulated counts.

Every variant accumulates in 2*SEW: T8->T16, T16->T32, T32->T64 through
vtdot.vv; E4M3/E5M2 are widened to FP16, FP16->FP32 and FP32->FP64 through
vfwmul.vv and an ordered reduction. The result is narrowed back to SEW.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
import math

from .codec import TakumFormat
from .ieee import BINARY128, E4M3, E5M2, FP16, FP32, IEEEFormat, WIDENED, is_finite
from .zvtakum import TakumVectorMachine


@dataclass(frozen=True)
class Variant:
    name: str
    family: str  # "takum" or "ieee"
    sew: int
    fused: bool = True  # Takum only; False is the per-step rounding ablation

    @property
    def storage(self):
        return TakumFormat(self.sew) if self.family == "takum" else IEEE_BY_NAME[self.name]

    @property
    def accumulator(self):
        return TakumFormat(2 * self.sew) if self.family == "takum" else WIDENED[self.name]


IEEE_BY_NAME = {f.name: f for f in (E4M3, E5M2, FP16, FP32)}
VARIANTS = [Variant("T8", "takum", 8), Variant("E4M3", "ieee", 8), Variant("E5M2", "ieee", 8),
            Variant("T16", "takum", 16), Variant("FP16", "ieee", 16),
            Variant("T32", "takum", 32), Variant("FP32", "ieee", 32)]
ABLATION = [Variant(f"T{w}-stepwise", "takum", w, fused=False) for w in (8, 16, 32)]


@dataclass
class CSR:
    n_rows: int
    n_cols: int
    row_ptr: list[int]
    cols: list[int]
    values: list[Fraction]
    name: str = ""
    kind: str = field(default="")

    @classmethod
    def from_triplets(cls, n_rows, n_cols, triplets, name=""):
        merged: dict[tuple[int, int], Fraction] = {}
        for row, col, value in triplets:
            merged[row, col] = merged.get((row, col), Fraction(0)) + value
        row_ptr, cols, values = [0] * (n_rows + 1), [], []
        for (row, col), value in sorted(merged.items()):
            row_ptr[row + 1] += 1
            cols.append(col)
            values.append(value)
        for i in range(n_rows):
            row_ptr[i + 1] += row_ptr[i]
        return cls(n_rows, n_cols, row_ptr, cols, values, name)

    @property
    def nnz(self) -> int:
        return len(self.values)

    def row_lengths(self) -> list[int]:
        return [self.row_ptr[i + 1] - self.row_ptr[i] for i in range(self.n_rows)]


def read_matrix_market(path, name="") -> CSR:
    """Read a real or pattern coordinate Matrix Market file with exact values."""
    with open(path) as file:
        header = file.readline().split()
        if len(header) != 5 or header[0] != "%%MatrixMarket" or header[1].lower() != "matrix":
            raise ValueError("Not a Matrix Market matrix")
        layout, field_type, symmetry = (h.lower() for h in header[2:])
        if layout != "coordinate" or field_type not in ("real", "integer", "pattern"):
            raise ValueError(f"Unsupported Matrix Market type: {layout} {field_type}")
        line = file.readline()
        while line.startswith("%") or not line.strip():
            line = file.readline()
        n_rows, n_cols, entries = map(int, line.split())
        triplets = []
        for _ in range(entries):
            parts = file.readline().split()
            row, col = int(parts[0]) - 1, int(parts[1]) - 1
            value = Fraction(1) if field_type == "pattern" else Fraction(parts[2])
            triplets.append((row, col, value))
            if row != col and symmetry in ("symmetric", "hermitian"):
                triplets.append((col, row, value))
            elif row != col and symmetry == "skew-symmetric":
                triplets.append((col, row, -value))
    return CSR.from_triplets(n_rows, n_cols, triplets, name)


# Instruction counting. Kept next to the kernel; tests check both agree.
SCALAR_PER_ROW = 7    # lw, lw, sub, addi, beqz, addi, bne
SCALAR_PER_STRIP = 6  # sub, slli, add, slli, add, bnez
VECTOR_PER_ROW = 4    # vsetivli, vmv.s.x, vsetivli, vse
VECTOR_PER_CHUNK = 4  # vsetvli, vle, narrowing conversion, vse


def vector_per_strip(variant: Variant) -> int:
    if variant.family == "takum":
        return 5  # vsetvli, vle, vle32, vluxei32, vtdot.vv
    if variant.sew == 8:
        return 9  # ... vfwcvt x2, vsetvli, vfmul, vfredosum
    return 7      # ... vfwmul, vsetvli, vfredosum


def count_instructions(row_lengths, variant: Variant, vlen: int = 128, lmul: int = 1) -> dict:
    vlmax = vlen * lmul // variant.sew
    strips = sum(-(-n // vlmax) for n in row_lengths)
    rows = len(row_lengths)
    chunks = -(-rows // vlmax)
    vector = VECTOR_PER_ROW * rows + vector_per_strip(variant) * strips + VECTOR_PER_CHUNK * chunks
    scalar = SCALAR_PER_ROW * rows + SCALAR_PER_STRIP * (strips + chunks)
    return {"vector": vector, "scalar": scalar, "total": vector + scalar, "strips": strips}


def spmv_simulated(csr: CSR, variant: Variant, x=None, vlen: int = 128, lmul: int = 1,
                   trace: bool = False):
    """Run the vector kernel. Returns (y values, machine)."""
    machine = TakumVectorMachine(vlen, trace, vtdot_fused=variant.fused)
    s, size = variant.sew, variant.sew // 8
    storage = variant.storage
    if variant.family == "ieee" and s == 8:
        machine.fp8 = storage
    x = [Fraction(1)] * csr.n_cols if x is None else x
    vals = machine.alloc(max(1, csr.nnz) * size)
    offsets = machine.alloc(max(1, csr.nnz) * 4)
    x_address = machine.alloc(max(1, csr.n_cols) * size)
    y_wide = machine.alloc(max(1, csr.n_rows) * 2 * size)
    y_address = machine.alloc(max(1, csr.n_rows) * size)
    machine.store_array(vals, [storage.encode(v) for v in csr.values], s)
    machine.store_array(offsets, [c * size for c in csr.cols], 32)  # byte offsets, precomputed once
    machine.store_array(x_address, [storage.encode(v) for v in x], s)

    k = 0
    for i in range(csr.n_rows):
        n = csr.row_ptr[i + 1] - csr.row_ptr[i]
        for op, args in (("lw", "t0, 0(a0)"), ("lw", "t1, 4(a0)"), ("sub", "a5, t1, t0"), ("addi", "a0, a0, 4")):
            machine.scalar(op, args)
        machine.vsetvli(1, 2 * s, immediate=True)
        machine.vmv_s_x(2, 0)
        machine.scalar("beqz", "a5, 2f")
        while n > 0:
            vl = machine.vsetvli(n, s, lmul)
            machine.vle(4, vals + k * size, s)
            machine.vle(12, offsets + k * 4, 32, rs1="a2")
            machine.vluxei(5, x_address, 12, 32)
            if variant.family == "takum":
                machine.vtdot_vv(2, 4, 5)
            elif s == 8:
                machine.vfwcvt_f_f_v(6, 4)
                machine.vfwcvt_f_f_v(8, 5)
                machine.vsetvli(None, 16, 2 * lmul)
                machine.vfmul_vv(10, 6, 8)
                machine.vfredosum_vs(2, 10, 2)
            else:
                machine.vfwmul_vv(6, 4, 5)
                machine.vsetvli(None, 2 * s, 2 * lmul)
                machine.vfredosum_vs(2, 6, 2)
            for op, args in (("sub", "a5, a5, t0"), ("slli", "t1, t0, log2(sew/8)"), ("add", "a1, a1, t1"),
                             ("slli", "t2, t0, 2"), ("add", "a2, a2, t2"), ("bnez", "a5, 1b")):
                machine.scalar(op, args)
            k += vl
            n -= vl
        machine.vsetvli(1, 2 * s, immediate=True)
        machine.vse(2, y_wide + i * 2 * size, 2 * s)
        machine.scalar("addi", "a3, a3, 2*sew/8")
        machine.scalar("bne", "a0, a6, 0b")

    remaining, i = csr.n_rows, 0
    while remaining > 0:
        vl = machine.vsetvli(remaining, s, lmul)
        machine.vle(6, y_wide + i * 2 * size, 2 * s, rs1="a3")
        if variant.family == "takum":
            machine.vncvt_t_t(4, 6)
        else:
            machine.vfncvt_f_f_w(4, 6)
        machine.vse(4, y_address + i * size, s, rs1="a7")
        for op, args in (("sub", "a5, a5, t0"), ("slli", "t1, t0, log2(2*sew/8)"), ("add", "a3, a3, t1"),
                         ("slli", "t2, t0, log2(sew/8)"), ("add", "a7, a7, t2"), ("bnez", "a5, 3b")):
            machine.scalar(op, args)
        i += vl
        remaining -= vl
    y = [storage.decode(bits) for bits in machine.load_array(y_address, csr.n_rows, s)]
    return y, machine


@lru_cache(maxsize=None)
def _takum_table(width: int):
    fmt = TakumFormat(width)
    return [fmt.decode(bits) for bits in range(1 << width)] if width <= 16 else None


def takum_value(width: int, bits: int):
    table = _takum_table(width)
    return table[bits] if table is not None else TakumFormat(width).decode(bits)


@dataclass
class ConversionStats:
    inexact: int = 0
    saturated: int = 0       # Takum: magnitude clamped to the representable range
    overflow: int = 0        # IEEE: became infinity or NaN
    flushed_to_zero: int = 0  # IEEE: nonzero value became zero


def quantize_values(values, variant: Variant):
    """Convert exact values to the variant's storage format, with statistics."""
    stats, out, memo = ConversionStats(), [], {}
    fmt = variant.storage
    for value in values:
        if value not in memo:
            if variant.family == "takum":
                q = fmt.quantize(value)
                memo[value] = (takum_value(variant.sew, q.bits), q.inexact,
                               q.saturated_low or q.saturated_high, False, False)
            else:
                q = fmt.quantize(value)
                finite = is_finite(q)
                memo[value] = (q, q != value, False, not finite, finite and q == 0 and value != 0)
        q, inexact, saturated, overflow, flushed = memo[value]
        stats.inexact += inexact
        stats.saturated += saturated
        stats.overflow += overflow
        stats.flushed_to_zero += flushed
        out.append(q)
    return out, stats


def spmv_fast(csr: CSR, variant: Variant, a_values, x_values, vlen: int = 128, lmul: int = 1):
    """Same arithmetic as spmv_simulated on already quantized A and x values."""
    y = []
    if variant.family == "takum":
        acc_fmt, s = TakumFormat(2 * variant.sew), variant.sew
        vlmax = vlen * lmul // s
        for i in range(csr.n_rows):
            start, end = csr.row_ptr[i], csr.row_ptr[i + 1]
            total = Fraction(0)
            for strip in range(start, end, vlmax):
                pairs = [(a_values[k], x_values[csr.cols[k]]) for k in range(strip, min(end, strip + vlmax))]
                if total is None or any(a is None or b is None for a, b in pairs):
                    total = None
                    continue
                if variant.fused:
                    total = takum_value(2 * s, acc_fmt.encode(total + sum(a * b for a, b in pairs)))
                else:
                    for a, b in pairs:
                        product = takum_value(2 * s, acc_fmt.encode(a * b))
                        total = takum_value(2 * s, acc_fmt.encode(total + product))
            y.append(takum_value(s, acc_fmt.convert(acc_fmt.encode(total), s)))
        return y
    storage, acc_fmt = variant.storage, variant.accumulator
    for i in range(csr.n_rows):
        total = Fraction(0)
        for k in range(csr.row_ptr[i], csr.row_ptr[i + 1]):
            a, b = a_values[k], x_values[csr.cols[k]]
            if variant.sew == 8:
                # vfwcvt is exact into FP16; the product is rounded in FP16.
                product = acc_fmt.mul(acc_fmt.quantize(a), acc_fmt.quantize(b))
            else:
                product = acc_fmt.mul(a, b)
            total = acc_fmt.add(total, product)
        y.append(storage.quantize(total))
    return y


def reference_spmv(csr: CSR, x_values=None):
    """binary128 reference: inputs, products and sums rounded to binary128."""
    a = [BINARY128.quantize(v) for v in csr.values]
    x = [BINARY128.quantize(v) for v in x_values] if x_values else [Fraction(1)] * csr.n_cols
    y = []
    for i in range(csr.n_rows):
        total = Fraction(0)
        for k in range(csr.row_ptr[i], csr.row_ptr[i + 1]):
            total = BINARY128.add(total, BINARY128.mul(a[k], x[csr.cols[k]]))
        y.append(total)
    return y


def log10_relative_error(approx, exact) -> float | None:
    """log10(||approx - exact||_2 / ||exact||_2), computed exactly.

    Returns +inf when approx has a non-finite entry (NaN, infinity or NaR),
    -inf for an exact result and None when ||exact|| is zero or not finite.
    Values are scaled to integers by a common denominator, which cancels in
    the ratio; this is exact and much faster than summing Fractions.
    """
    if any(not isinstance(e, Fraction) for e in exact):
        return None
    if any(a is None or not isinstance(a, Fraction) for a in approx):
        return math.inf if any(e != 0 for e in exact) else None
    scale = 1
    for d in {v.denominator for v in approx} | {v.denominator for v in exact}:
        scale = math.lcm(scale, d)
        if scale.bit_length() > 1 << 16:  # unrelated denominators: plain Fractions
            break
    if scale.bit_length() <= 1 << 16:
        a_int = [v.numerator * (scale // v.denominator) for v in approx]
        e_int = [v.numerator * (scale // v.denominator) for v in exact]
    else:
        a_int, e_int = approx, exact
    denominator = sum(e * e for e in e_int)
    if denominator == 0:
        return None
    numerator = sum((a - e) * (a - e) for a, e in zip(a_int, e_int))
    if numerator == 0:
        return -math.inf
    ratio = Fraction(numerator) / Fraction(denominator)
    return 0.5 * (math.log10(ratio.numerator) - math.log10(ratio.denominator))
