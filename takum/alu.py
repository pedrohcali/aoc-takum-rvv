"""Scalar functional ALU; one final Takum rounding per arithmetic operation."""

from dataclasses import dataclass
from fractions import Fraction
import operator
from .codec import Quantized, TakumFormat


@dataclass(frozen=True)
class ALUResult:
    operation: str
    width: int
    a: int
    b: int
    exact: Fraction | None
    rounded: Quantized

    @property
    def bits(self) -> int:
        return self.rounded.bits

    @property
    def value(self) -> Fraction | None:
        return TakumFormat(self.width).decode(self.bits)


class TakumALU:
    """This models arithmetic semantics, not pipeline cycles or hardware cost.

    Status flags are diagnostic Python metadata, not architectural RISC-V CSRs.
    """

    def __init__(self, width: int):
        self.format = TakumFormat(width)

    def execute(self, operation: str, a: int, b: int) -> ALUResult:
        operations = {"add": operator.add, "sub": operator.sub, "mul": operator.mul}
        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")
        x, y = self.format.decode(a), self.format.decode(b)
        exact = None if x is None or y is None else operations[operation](x, y)
        return ALUResult(operation, self.format.width, a, b, exact,
                         self.format.quantize(exact))

    def add(self, a: int, b: int) -> int:
        return self.execute("add", a, b).bits

    def sub(self, a: int, b: int) -> int:
        return self.execute("sub", a, b).bits

    def mul(self, a: int, b: int) -> int:
        return self.execute("mul", a, b).bits
