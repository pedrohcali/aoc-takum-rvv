"""Linear Takum codec, Definition 8 of Hunhold (2024).

Values are exact fractions. None denotes NaR. Encodings are unsigned n-bit
integers; signed integer interpretation orders all finite values. Rounding is
nearest/even on the encoded bit stream, as in libtakum 2.0.0. For short formats
this is not necessarily rounding to the nearest real value.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from functools import cached_property, lru_cache
import math


Number = int | float | str | Decimal | Fraction | None
# T64 is the accumulator width of vtdot.vv for T32 sources (phase 2).
WIDTHS = (8, 16, 32, 64)


def power_of_two(exponent: int) -> Fraction:
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def floor_log2(value: Fraction) -> int:
    """Exact floor(log2(value)), without floating-point conversion."""
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    return exponent - (value < power_of_two(exponent))


def round_even(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    twice = 2 * remainder
    return quotient + (twice > value.denominator or
                       (twice == value.denominator and quotient % 2 == 1))


def as_fraction(value: Number) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().lower() in {"nar", "nan", "inf", "+inf", "-inf",
                                   "infinity", "+infinity", "-infinity"}:
            return None
        return Fraction(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    return Fraction(value)


@dataclass(frozen=True)
class Fields:
    bits: int
    width: int
    sign: int
    direction: int
    regime: int
    characteristic_width: int
    characteristic_bits: int
    characteristic: int
    fraction_width: int
    fraction_bits: int
    ghost_bits: int
    exponent: int
    special: str | None

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.fraction_bits, 1 << self.fraction_width)

    @property
    def value(self) -> Fraction | None:
        if self.special == "nar":
            return None
        if self.special == "zero":
            return Fraction(0)
        return (1 - 3 * self.sign + self.fraction) * power_of_two(self.exponent)


@dataclass(frozen=True)
class Quantized:
    bits: int
    inexact: bool = False
    saturated_low: bool = False
    saturated_high: bool = False
    invalid: bool = False


@dataclass(frozen=True)
class TakumFormat:
    width: int

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width not in WIDTHS:
            raise ValueError("Takum width must be 8, 16, 32 or 64")

    @property
    def mask(self) -> int:
        return (1 << self.width) - 1

    @property
    def nar(self) -> int:
        return 1 << (self.width - 1)

    def validate_bits(self, bits: int) -> None:
        if type(bits) is not int or not 0 <= bits <= self.mask:
            raise ValueError(f"Expected an unsigned {self.width}-bit integer")

    def fields(self, bits: int) -> Fields:
        self.validate_bits(bits)
        # Definition 8: append ghost zero bits to strings shorter than 12 bits.
        sign = bits >> (self.width - 1)
        direction = (bits >> (self.width - 2)) & 1
        regime = (bits >> (self.width - 5)) & 7
        r = regime if direction else 7 - regime
        # Only append the zeros needed to complete C. Appending additional
        # zeros to F is equivalent but obscures the stored precision.
        effective_width = max(5 + r, self.width)
        ghost = effective_width - self.width
        expanded = bits << ghost
        p = effective_width - 5 - r
        characteristic_bits = (expanded >> p) & ((1 << r) - 1)
        bias = (1 << r) - 1 if direction else 1 - (1 << (r + 1))
        c = bias + characteristic_bits
        fraction_bits = expanded & ((1 << p) - 1)
        special = "zero" if bits == 0 else "nar" if bits == self.nar else None
        return Fields(bits, self.width, sign, direction, regime, r,
                      characteristic_bits, c, p, fraction_bits, ghost,
                      (1 - 2 * sign) * (c + sign), special)

    def decode(self, bits: int) -> Fraction | None:
        # Validate before the cache: True and 1.0 hash like 1.
        self.validate_bits(bits)
        return self._decode_cached(bits)

    # Decoding is pure; the cache speeds up the phase 3 benchmark, where the
    # same patterns recur. Fractions are immutable, so sharing them is safe.
    @lru_cache(maxsize=1 << 18)
    def _decode_cached(self, bits: int) -> Fraction | None:
        return self.fields(bits).value

    @cached_property
    def min_positive(self) -> Fraction:
        return self.decode(1)

    @cached_property
    def max_positive(self) -> Fraction:
        return self.decode(self.nar - 1)

    def quantize(self, value: Number) -> Quantized:
        x = as_fraction(value)
        if x is None:
            return Quantized(self.nar, invalid=True)
        if x == 0:
            return Quantized(0)
        negative = x < 0
        magnitude = abs(x)
        low = magnitude < self.min_positive
        high = magnitude > self.max_positive
        if low:
            positive_bits = 1
        elif high:
            positive_bits = self.nar - 1
        else:
            # Encode positive magnitude, then use the exact two's-complement
            # negation property. Nearest/even bit rounding respects negation.
            c = floor_log2(magnitude)
            f = magnitude / power_of_two(c) - 1
            direction = int(c >= 0)
            r = (c + 1).bit_length() - 1 if direction else (-c).bit_length() - 1
            regime = r if direction else 7 - r
            bias = (1 << r) - 1 if direction else 1 - (1 << (r + 1))
            p = self.width - 5 - r  # May be negative in T8.
            prefix = ((direction << 3) | regime) << (self.width - 5)
            tail = (c - bias + f) * power_of_two(p)
            positive_bits = prefix + round_even(tail)
            # Rounding must never turn a finite nonzero input into zero or NaR.
            positive_bits = min(self.nar - 1, max(1, positive_bits))
        bits = (-positive_bits) & self.mask if negative else positive_bits
        return Quantized(bits, self.decode(bits) != x, low, high)

    def encode(self, value: Number) -> int:
        return self.quantize(value).bits

    def negate(self, bits: int) -> int:
        self.validate_bits(bits)
        return (-bits) & self.mask

    def convert(self, bits: int, target_width: int) -> int:
        return TakumFormat(target_width).encode(self.decode(bits))
