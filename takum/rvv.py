"""Functional model of the RISC-V vector state used by the phase 2 kernels.

This is an instruction-level functional model: it executes each instruction's
architectural effect and counts it, but it models no pipeline, latency or
memory hierarchy. Only the RVV 1.0 subset needed by the SpMV kernels is
present: vsetvli, unit-stride and indexed-unordered loads/stores, vmv.s.x,
the signed integer maximum vmax.vx (used as ReLU on takums) and the IEEE
floating-point baseline (vfwcvt, vfmul, vfwmul, vfredosum, vfncvt, vfmax).

Policies: LMUL >= 1, tail and inactive elements undisturbed, element widths
from 8 to 64 bits. Scalar instructions are not executed; the kernels report
them through scalar() so that the instruction count stays complete.
"""

from collections import Counter
from fractions import Fraction
import math

from .ieee import E4M3, FP16, FP32, FP64, IEEEFormat, is_finite

WIDTHS = (8, 16, 32, 64)


class VectorMachine:
    def __init__(self, vlen: int = 128, trace: bool = False):
        if vlen < 64 or vlen & (vlen - 1):
            raise ValueError("VLEN must be a power of two of at least 64 bits")
        self.vlen = vlen
        self.vlenb = vlen // 8
        self.vregs = bytearray(32 * self.vlenb)
        self.memory = bytearray()
        self.vl = 0
        self.sew = 8
        self.lmul = 1
        # The ratified RVV has no FP8 arithmetic; the 8-bit baseline format is
        # selected here, in the role that vtype.altfmt plays in FP8 proposals.
        self.fp8: IEEEFormat = E4M3
        self.counts: Counter = Counter()
        self.trace: list[str] | None = [] if trace else None

    # Memory and bookkeeping (not instructions)

    def alloc(self, nbytes: int, align: int = 8) -> int:
        address = -len(self.memory) % align + len(self.memory)
        self.memory.extend(bytes(address + nbytes - len(self.memory)))
        return address

    def store_array(self, address: int, values, eew: int) -> None:
        size = eew // 8
        for i, value in enumerate(values):
            self.memory[address + i * size:address + (i + 1) * size] = value.to_bytes(size, "little")

    def load_array(self, address: int, count: int, eew: int) -> list[int]:
        size = eew // 8
        return [int.from_bytes(self.memory[address + i * size:address + (i + 1) * size], "little")
                for i in range(count)]

    def emit(self, mnemonic: str, operands: str = "") -> None:
        self.counts[mnemonic] += 1
        if self.trace is not None:
            self.trace.append(f"{mnemonic} {operands}".rstrip())

    def scalar(self, mnemonic: str, operands: str = "") -> None:
        """Account for a scalar RV64 instruction of the kernel loop."""
        self.emit(mnemonic, operands)

    def vector_count(self) -> int:
        return sum(n for name, n in self.counts.items() if name.startswith("v"))

    def scalar_count(self) -> int:
        return sum(n for name, n in self.counts.items() if not name.startswith("v"))

    # Register file

    def vlmax(self, sew: int | None = None, lmul: int | None = None) -> int:
        return self.vlen * (lmul or self.lmul) // (sew or self.sew)

    def _group(self, reg: int, eew: int) -> int:
        """Check alignment of a register group of element width eew."""
        emul = max(1, eew * self.lmul // self.sew)
        if reg < 0 or emul > 8 or reg % emul or reg + emul > 32:
            raise ValueError(f"Invalid register group v{reg} for EEW={eew}, EMUL={emul}")
        return emul

    def get(self, reg: int, index: int, eew: int) -> int:
        size = eew // 8
        start = reg * self.vlenb + index * size
        return int.from_bytes(self.vregs[start:start + size], "little")

    def set(self, reg: int, index: int, eew: int, value: int) -> None:
        size = eew // 8
        start = reg * self.vlenb + index * size
        self.vregs[start:start + size] = (value & ((1 << eew) - 1)).to_bytes(size, "little")

    def active(self, index: int, vm: bool) -> bool:
        return vm or bool(self.vregs[index // 8] >> (index % 8) & 1)

    @staticmethod
    def _mask_suffix(vm: bool) -> str:
        return "" if vm else ", v0.t"

    # Configuration

    def vsetvli(self, avl: int | None, sew: int, lmul: int = 1, immediate: bool = False) -> int:
        """avl=None keeps the current vl (vsetvli zero, zero, ...)."""
        if sew not in WIDTHS or lmul not in (1, 2, 4, 8):
            raise ValueError("Unsupported SEW or LMUL")
        new_max = self.vlmax(sew, lmul)
        if avl is None:
            if immediate or new_max != self.vlmax():
                raise ValueError("Keeping vl requires vsetvli and an unchanged VLMAX")
            dest, source = "zero", "zero"
        else:
            if avl < 0 or (immediate and avl > 31):
                raise ValueError("Invalid AVL for the selected instruction")
            dest, source = "t0", str(avl) if immediate else "a5"
            self.vl = min(avl, new_max)
        self.sew, self.lmul = sew, lmul
        self.emit("vsetivli" if immediate else "vsetvli", f"{dest}, {source}, e{sew}, m{lmul}, tu, mu")
        return self.vl

    # Loads, stores and moves

    def vle(self, vd: int, address: int, eew: int, vm: bool = True, rs1: str = "a1") -> None:
        self._group(vd, eew)
        for i in range(self.vl):
            if self.active(i, vm):
                self.set(vd, i, eew, int.from_bytes(self.memory[address + i * eew // 8:address + (i + 1) * eew // 8], "little"))
        self.emit(f"vle{eew}.v", f"v{vd}, ({rs1}){self._mask_suffix(vm)}")

    def vse(self, vs3: int, address: int, eew: int, vm: bool = True, rs1: str = "a3") -> None:
        self._group(vs3, eew)
        size = eew // 8
        for i in range(self.vl):
            if self.active(i, vm):
                self.memory[address + i * size:address + (i + 1) * size] = self.get(vs3, i, eew).to_bytes(size, "little")
        self.emit(f"vse{eew}.v", f"v{vs3}, ({rs1}){self._mask_suffix(vm)}")

    def vluxei(self, vd: int, base: int, vs2: int, index_eew: int, vm: bool = True) -> None:
        """Indexed load: element i comes from base + vs2[i] (byte offsets)."""
        self._group(vd, self.sew)
        self._group(vs2, index_eew)
        size = self.sew // 8
        for i in range(self.vl):
            if self.active(i, vm):
                address = base + self.get(vs2, i, index_eew)
                self.set(vd, i, self.sew, int.from_bytes(self.memory[address:address + size], "little"))
        self.emit(f"vluxei{index_eew}.v", f"v{vd}, (a4), v{vs2}{self._mask_suffix(vm)}")

    def vmv_s_x(self, vd: int, value: int) -> None:
        if self.vl > 0:
            self.set(vd, 0, self.sew, value)
        self.emit("vmv.s.x", f"v{vd}, zero" if value == 0 else f"v{vd}, t1")

    def vmax_vx(self, vd: int, vs2: int, value: int = 0, vm: bool = True) -> None:
        """Signed integer maximum with a scalar. Takums are ordered like
        two's complement integers, so vmax.vx with x0 is a takum ReLU."""
        half = 1 << (self.sew - 1)
        for i in range(self.vl):
            if self.active(i, vm):
                element = self.get(vs2, i, self.sew)
                signed = element - (element & half) * 2
                self.set(vd, i, self.sew, max(signed, value))
        self.emit("vmax.vx", f"v{vd}, v{vs2}, zero{self._mask_suffix(vm)}" if value == 0
                  else f"v{vd}, v{vs2}, t1{self._mask_suffix(vm)}")

    # IEEE 754 baseline (RVV F/V subset; FP8 selected by self.fp8)

    def fp_format(self, sew: int) -> IEEEFormat:
        return {8: self.fp8, 16: FP16, 32: FP32, 64: FP64}[sew]

    def vfwcvt_f_f_v(self, vd: int, vs2: int, vm: bool = True) -> None:
        source, target = self.fp_format(self.sew), self.fp_format(2 * self.sew)
        self._group(vd, 2 * self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                self.set(vd, i, 2 * self.sew, target.encode(source.decode(self.get(vs2, i, self.sew))))
        self.emit("vfwcvt.f.f.v", f"v{vd}, v{vs2}{self._mask_suffix(vm)}")

    def vfncvt_f_f_w(self, vd: int, vs2: int, vm: bool = True) -> None:
        source, target = self.fp_format(2 * self.sew), self.fp_format(self.sew)
        self._group(vs2, 2 * self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                self.set(vd, i, self.sew, target.encode(source.decode(self.get(vs2, i, 2 * self.sew))))
        self.emit("vfncvt.f.f.w", f"v{vd}, v{vs2}{self._mask_suffix(vm)}")

    def vfmul_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        fmt = self.fp_format(self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                product = fmt.mul(fmt.decode(self.get(vs2, i, self.sew)), fmt.decode(self.get(vs1, i, self.sew)))
                self.set(vd, i, self.sew, fmt.encode(product))
        self.emit("vfmul.vv", f"v{vd}, v{vs2}, v{vs1}{self._mask_suffix(vm)}")

    def vfwmul_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        source, target = self.fp_format(self.sew), self.fp_format(2 * self.sew)
        self._group(vd, 2 * self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                product = target.mul(source.decode(self.get(vs2, i, self.sew)),
                                     source.decode(self.get(vs1, i, self.sew)))
                self.set(vd, i, 2 * self.sew, target.encode(product))
        self.emit("vfwmul.vv", f"v{vd}, v{vs2}, v{vs1}{self._mask_suffix(vm)}")

    def vfredosum_vs(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        """Ordered sum: vd[0] = (((vs1[0] + vs2[0]) + vs2[1]) + ...)."""
        fmt = self.fp_format(self.sew)
        if self.vl > 0:
            total = fmt.decode(self.get(vs1, 0, self.sew))
            for i in range(self.vl):
                if self.active(i, vm):
                    total = fmt.add(total, fmt.decode(self.get(vs2, i, self.sew)))
            self.set(vd, 0, self.sew, fmt.encode(total))
        self.emit("vfredosum.vs", f"v{vd}, v{vs2}, v{vs1}{self._mask_suffix(vm)}")

    def vfmax_vf(self, vd: int, vs2: int, scalar=0, vm: bool = True) -> None:
        """IEEE 754-2019 maximumNumber, as RISC-V fmax: a NaN operand yields the
        other operand. With f0 = 0 this is the IEEE ReLU."""
        fmt = self.fp_format(self.sew)
        scalar = Fraction(scalar)
        for i in range(self.vl):
            if self.active(i, vm):
                x = fmt.decode(self.get(vs2, i, self.sew))
                if not is_finite(x) and math.isnan(x):
                    result = scalar
                else:
                    result = x if x > scalar else scalar
                self.set(vd, i, self.sew, fmt.encode(result))
        self.emit("vfmax.vf", f"v{vd}, v{vs2}, f0{self._mask_suffix(vm)}")
