"""Exact IEEE 754 style binary formats used as the phase 3 baseline.

Finite values are exact fractions; infinities and NaN are the float constants
INF, -INF and NAN. Rounding is round to nearest, ties to even, with gradual
underflow. Signed zero is not tracked: it has no effect on the error norms
measured in this project.

E4M3 follows the OCP 8-bit floating point specification (OFP8): no
infinities, a single NaN magnitude (S.1111.111) and a maximum of 448. We use
the non-saturating conversion mode, so overflow produces NaN for E4M3 and an
infinity for the other formats.
"""

from dataclasses import dataclass
from fractions import Fraction
import math

from .codec import floor_log2, power_of_two, round_even

INF = math.inf
NAN = math.nan
Value = Fraction | float


def is_finite(value: Value) -> bool:
    return isinstance(value, Fraction)


def _is_nan(value: Value) -> bool:
    return not is_finite(value) and math.isnan(value)


@dataclass(frozen=True)
class IEEEFormat:
    name: str
    exp_bits: int
    man_bits: int
    ofp8_e4m3: bool = False

    @property
    def width(self) -> int:
        return 1 + self.exp_bits + self.man_bits

    @property
    def bias(self) -> int:
        return (1 << (self.exp_bits - 1)) - 1

    @property
    def emin(self) -> int:
        return 1 - self.bias

    @property
    def emax(self) -> int:
        # E4M3 uses the all-ones exponent for finite values.
        return self.bias + 1 if self.ofp8_e4m3 else self.bias

    @property
    def max_finite(self) -> Fraction:
        steps = (1 << (self.man_bits + 1)) - (2 if self.ofp8_e4m3 else 1)
        return steps * power_of_two(self.emax - self.man_bits)

    @property
    def min_subnormal(self) -> Fraction:
        return power_of_two(self.emin - self.man_bits)

    def quantize(self, value: Value) -> Value:
        """Round an exact value (or a special float) to this format."""
        if not is_finite(value):
            if math.isnan(value) or self.ofp8_e4m3:
                return NAN
            return value
        if value == 0:
            return Fraction(0)
        magnitude = abs(value)
        exponent = max(floor_log2(magnitude), self.emin)
        quantum = power_of_two(exponent - self.man_bits)
        rounded = round_even(magnitude / quantum) * quantum
        if rounded > self.max_finite:
            return NAN if self.ofp8_e4m3 else (INF if value > 0 else -INF)
        return rounded if value > 0 else -rounded

    # Special operands are resolved without float(), which would overflow or
    # underflow for finite binary128 values.
    def add(self, a: Value, b: Value) -> Value:
        if is_finite(a) and is_finite(b):
            return self.quantize(a + b)
        if _is_nan(a) or _is_nan(b):
            return NAN
        if not is_finite(a) and not is_finite(b) and a != b:
            return NAN  # inf - inf
        return self.quantize(b if is_finite(a) else a)

    def mul(self, a: Value, b: Value) -> Value:
        if is_finite(a) and is_finite(b):
            return self.quantize(a * b)
        if _is_nan(a) or _is_nan(b) or a == 0 or b == 0:
            return NAN  # NaN operand or infinity times zero
        return self.quantize(INF if (a > 0) == (b > 0) else -INF)

    def decode(self, bits: int) -> Value:
        if type(bits) is not int or not 0 <= bits < 1 << self.width:
            raise ValueError(f"Expected an unsigned {self.width}-bit integer")
        sign = -1 if bits >> (self.width - 1) else 1
        exponent_field = (bits >> self.man_bits) & ((1 << self.exp_bits) - 1)
        mantissa = bits & ((1 << self.man_bits) - 1)
        top = (1 << self.exp_bits) - 1
        if self.ofp8_e4m3:
            if exponent_field == top and mantissa == (1 << self.man_bits) - 1:
                return NAN
        elif exponent_field == top:
            return NAN if mantissa else sign * INF
        if exponent_field == 0:
            magnitude = mantissa * self.min_subnormal
        else:
            significand = (1 << self.man_bits) + mantissa
            magnitude = significand * power_of_two(exponent_field - self.bias - self.man_bits)
        return sign * magnitude

    def encode(self, value: Value) -> int:
        """Bit pattern of quantize(value); NaN uses the positive quiet NaN."""
        q = self.quantize(value)
        top = (1 << self.exp_bits) - 1
        if not is_finite(q):
            if math.isnan(q):
                if self.ofp8_e4m3:
                    return (top << self.man_bits) | ((1 << self.man_bits) - 1)
                return (top << self.man_bits) | (1 << (self.man_bits - 1))
            return ((q < 0) << (self.width - 1)) | (top << self.man_bits)
        sign = int(q < 0) << (self.width - 1)
        magnitude = abs(q)
        if magnitude == 0:
            return 0
        if magnitude < power_of_two(self.emin):
            return sign | int(magnitude / self.min_subnormal)
        exponent = floor_log2(magnitude)
        mantissa = int(magnitude / power_of_two(exponent - self.man_bits)) - (1 << self.man_bits)
        return sign | ((exponent + self.bias) << self.man_bits) | mantissa


E4M3 = IEEEFormat("E4M3", 4, 3, ofp8_e4m3=True)
E5M2 = IEEEFormat("E5M2", 5, 2)
FP16 = IEEEFormat("FP16", 5, 10)
FP32 = IEEEFormat("FP32", 8, 23)
FP64 = IEEEFormat("FP64", 11, 52)
BINARY128 = IEEEFormat("binary128", 15, 112)

# Accumulator format of each baseline storage format (2*SEW).
WIDENED = {"E4M3": FP16, "E5M2": FP16, "FP16": FP32, "FP32": FP64}
