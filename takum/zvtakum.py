"""Zvtakum: the five experimental Takum vector instructions of phase 2.

The instructions reuse the OP-V field layout (funct6 | vm | vs2 | vs1 |
funct3 | vd | opcode) under the custom-2 major opcode, which RISC-V reserves
for non-standard extensions, so they cannot collide with current or future
standard encodings. Each funct6 repeats the one of the IEEE counterpart, and
funct3 is OPFVV. SEW selects T8, T16 or T32, exactly as it selects the IEEE
width for the F/V instructions; no CSR state is added.
"""

from .alu import TakumALU
from .codec import TakumFormat
from .rvv import VectorMachine

OPCODE_CUSTOM2 = 0b1011011
FUNCT3_OPFVV = 0b001
VFUNARY0 = 0b010010
VNCVT_SELECTOR = 0b10100  # vs1 field of vfncvt.f.f.w in VFUNARY0

ENCODINGS = {
    # mnemonic: (funct6, fixed vs1 or None, IEEE counterpart)
    "vtadd.vv": (0b000000, None, "vfadd.vv"),
    "vtsub.vv": (0b000010, None, "vfsub.vv"),
    "vtmul.vv": (0b100100, None, "vfmul.vv"),
    "vtdot.vv": (0b111100, None, "vfwmul.vv + vfredosum.vs"),  # funct6 of vfwmacc
    "vncvt.t.t": (VFUNARY0, VNCVT_SELECTOR, "vfncvt.f.f.w"),
}


def encode(mnemonic: str, vd: int, vs2: int, vs1: int = 0, vm: bool = True) -> int:
    funct6, fixed_vs1, _ = ENCODINGS[mnemonic]
    if fixed_vs1 is not None:
        vs1 = fixed_vs1
    for register in (vd, vs2, vs1):
        if not 0 <= register < 32:
            raise ValueError("Register numbers must be between 0 and 31")
    return (funct6 << 26 | int(vm) << 25 | vs2 << 20 | vs1 << 15
            | FUNCT3_OPFVV << 12 | vd << 7 | OPCODE_CUSTOM2)


def decode(word: int) -> tuple[str, int, int, int, bool]:
    if word & 0x7f != OPCODE_CUSTOM2 or (word >> 12) & 7 != FUNCT3_OPFVV:
        raise ValueError("Not a Zvtakum instruction")
    funct6, vs1 = word >> 26, (word >> 15) & 31
    for mnemonic, (code, fixed_vs1, _) in ENCODINGS.items():
        if code == funct6 and (fixed_vs1 is None or fixed_vs1 == vs1):
            return mnemonic, (word >> 7) & 31, (word >> 20) & 31, vs1, bool(word >> 25 & 1)
    raise ValueError("Reserved Zvtakum encoding")


class TakumVectorMachine(VectorMachine):
    """VectorMachine with Zvtakum. vtdot_fused=False is the ablation mode."""

    def __init__(self, vlen: int = 128, trace: bool = False, vtdot_fused: bool = True):
        super().__init__(vlen, trace)
        self.vtdot_fused = vtdot_fused

    def _emit_takum(self, mnemonic: str, vd: int, vs2: int, vs1: int | None, vm: bool) -> None:
        operands = f"v{vd}, v{vs2}" + ("" if vs1 is None else f", v{vs1}") + self._mask_suffix(vm)
        word = encode(mnemonic, vd, vs2, vs1 or 0, vm)
        self.emit(mnemonic, f"{operands:<22} # 0x{word:08x}")

    def _check_sew(self) -> None:
        if self.sew not in (8, 16, 32):
            raise ValueError("Zvtakum requires SEW 8, 16 or 32")

    def _elementwise(self, operation: str, vd: int, vs2: int, vs1: int, vm: bool) -> None:
        self._check_sew()
        if not vm and vd == 0:
            raise ValueError("Masked vector destination overlaps v0")
        alu = TakumALU(self.sew)
        for register in (vd, vs2, vs1):
            self._group(register, self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                self.set(vd, i, self.sew, alu.execute(operation, self.get(vs2, i, self.sew),
                                                      self.get(vs1, i, self.sew)).bits)
        self._emit_takum(f"vt{operation}.vv", vd, vs2, vs1, vm)

    def vtadd_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        self._elementwise("add", vd, vs2, vs1, vm)

    def vtsub_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        self._elementwise("sub", vd, vs2, vs1, vm)

    def vtmul_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        self._elementwise("mul", vd, vs2, vs1, vm)

    def vtdot_vv(self, vd: int, vs2: int, vs1: int, vm: bool = True) -> None:
        """vd[0] (2*SEW) = round(vd[0] + sum of active vs2[i] * vs1[i]).

        The sum is exact and rounded once to the 2*SEW takum; any NaR operand
        gives NaR. With vtdot_fused=False every product and partial sum is
        rounded to 2*SEW separately.
        """
        self._check_sew()
        if not 0 <= vd < 32:
            raise ValueError("Invalid scalar reduction destination")
        self._group(vs2, self.sew)
        self._group(vs1, self.sew)
        source, accumulator = TakumFormat(self.sew), TakumFormat(2 * self.sew)
        if self.vl > 0:
            total = accumulator.decode(self.get(vd, 0, 2 * self.sew))
            for i in range(self.vl):
                if not self.active(i, vm) or total is None:
                    continue
                a = source.decode(self.get(vs2, i, self.sew))
                b = source.decode(self.get(vs1, i, self.sew))
                if a is None or b is None:
                    total = None
                elif self.vtdot_fused:
                    total += a * b
                else:
                    product = accumulator.decode(accumulator.encode(a * b))
                    total = accumulator.decode(accumulator.encode(total + product))
            self.set(vd, 0, 2 * self.sew, accumulator.encode(total))
        self._emit_takum("vtdot.vv", vd, vs2, vs1, vm)

    def vncvt_t_t(self, vd: int, vs2: int, vm: bool = True) -> None:
        """Narrowing conversion: vd[i] (SEW) = round(vs2[i] (2*SEW))."""
        self._check_sew()
        self._group(vd, self.sew)
        wide_group = self._group(vs2, 2 * self.sew)
        if vs2 < vd < vs2 + wide_group:
            raise ValueError("Narrowing destination overlaps the high part of the source")
        if not vm and vd == 0:
            raise ValueError("Masked vector destination overlaps v0")
        source = TakumFormat(2 * self.sew)
        for i in range(self.vl):
            if self.active(i, vm):
                self.set(vd, i, self.sew, source.convert(self.get(vs2, i, 2 * self.sew), self.sew))
        self._emit_takum("vncvt.t.t", vd, vs2, None, vm)
