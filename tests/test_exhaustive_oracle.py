"""Independent T8 oracle: enumerate T9 rounding boundaries and bisect.

The implementation under test constructs the encoding from a binary exponent.
This oracle instead searches a precomputed ordered table, with exact fractions
throughout; it does not call the production decoder or encoder for expectations.
"""
from bisect import bisect_left
from fractions import Fraction
import operator
import unittest
from takum import TakumALU


def value_from_definition(bits, width):
    if bits == 0:
        return Fraction(0)
    if bits == 1 << (width - 1):
        return None
    text = format(bits, f"0{width}b").ljust(12, "0")
    s, d = int(text[0]), int(text[1])
    regime = int(text[2:5], 2)
    r = regime if d else 7 - regime
    characteristic = int(text[5:5+r] or "0", 2)
    characteristic += 2**r - 1 if d else 1 - 2**(r+1)
    fraction = text[5+r:]
    f = Fraction(int(fraction or "0", 2), 2**len(fraction))
    exponent = (-1)**s * (characteristic + s)
    scale = Fraction(2**exponent) if exponent >= 0 else Fraction(1, 2**-exponent)
    return (1 - 3*s + f) * scale


VALUES = [value_from_definition(bits, 8) for bits in range(256)]
THRESHOLDS = [value_from_definition(2*bits + 1, 9) for bits in range(1, 127)]


def quantize_by_table(value):
    if value is None:
        return 128
    if value == 0:
        return 0
    magnitude = abs(value)
    index = bisect_left(THRESHOLDS, magnitude)
    bits = 1 + index
    if index < len(THRESHOLDS) and magnitude == THRESHOLDS[index] and bits % 2:
        bits += 1
    return bits if value > 0 else 256 - bits


class ExhaustiveOracleTests(unittest.TestCase):
    def test_all_t8_pairs_against_independent_exact_oracle(self):
        alu = TakumALU(8)
        for operation, function in (("add", operator.add), ("sub", operator.sub), ("mul", operator.mul)):
            for a, x in enumerate(VALUES):
                for b, y in enumerate(VALUES):
                    exact = None if x is None or y is None else function(x, y)
                    expected = quantize_by_table(exact)
                    self.assertEqual(alu.execute(operation, a, b).bits, expected,
                                     (operation, hex(a), hex(b), exact))
