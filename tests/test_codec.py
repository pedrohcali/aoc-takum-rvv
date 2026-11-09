from decimal import Decimal
from fractions import Fraction
import random
import unittest
from takum import TakumFormat
from takum.codec import power_of_two


class CodecTests(unittest.TestCase):
    def test_known_bit_patterns(self):
        vectors = {0x00: 0, 0x01: power_of_two(-239), 0x20: power_of_two(-15),
                   0x38: Fraction(1, 2), 0x40: 1, 0x41: Fraction(9, 8),
                   0x44: Fraction(3, 2), 0x48: 2, 0x50: 8,
                   0x7f: power_of_two(239), 0x80: None, 0x81: -power_of_two(239),
                   0xb8: -2, 0xc0: -1, 0xc1: -Fraction(15, 16),
                   0xff: -power_of_two(-239)}
        for width in (8, 16, 32):
            fmt = TakumFormat(width)
            for bits8, value in vectors.items():
                bits = bits8 << (width - 8)
                self.assertEqual(fmt.decode(bits), value, (width, bits))
                self.assertEqual(fmt.encode(value), bits, (width, value))

    def test_exhaustive_t8_t16_roundtrip(self):
        for width in (8, 16):
            fmt = TakumFormat(width)
            for bits in range(1 << width):
                self.assertEqual(fmt.encode(fmt.decode(bits)), bits)

    def test_t32_roundtrip_boundaries_and_random(self):
        fmt = TakumFormat(32)
        rng = random.Random(20260928)
        patterns = [rng.getrandbits(32) for _ in range(10000)]
        for dr in range(16):
            boundary = dr << 27
            patterns += [(boundary + offset) & fmt.mask for offset in (-1, 0, 1)]
        for bits in patterns:
            self.assertEqual(fmt.encode(fmt.decode(bits)), bits)

    def test_signed_order_and_negation(self):
        fmt = TakumFormat(8)
        values = [fmt.decode(i & fmt.mask) for i in range(-127, 128)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        for bits in range(256):
            value = fmt.decode(bits)
            self.assertEqual(fmt.decode(fmt.negate(bits)), None if value is None else -value)

    def test_fields_and_ghost_bits(self):
        fmt = TakumFormat(8)
        a = fmt.fields(0x44)
        self.assertEqual((a.sign, a.direction, a.regime, a.characteristic_width,
                          a.fraction_width, a.fraction_bits, a.ghost_bits),
                         (0, 1, 0, 0, 3, 4, 0))
        b = fmt.fields(0x01)
        self.assertEqual((b.characteristic_width, b.characteristic_bits,
                          b.characteristic, b.ghost_bits, b.fraction_width),
                         (7, 16, -239, 4, 0))
        for width in (8, 16, 32):
            for dr in range(16):
                f = TakumFormat(width).fields(dr << (width - 5))
                self.assertEqual(f.characteristic_width,
                                 f.regime if f.direction else 7 - f.regime)

    def test_ties_even_and_sticky_bit(self):
        for width in (8, 16, 32):
            fmt = TakumFormat(width)
            one = 1 << (width - 2)
            step = power_of_two(-(width - 5))
            epsilon = power_of_two(-200)
            midpoint = 1 + step / 2
            self.assertEqual(fmt.encode(midpoint), one)
            self.assertEqual(fmt.encode(midpoint - epsilon), one)
            self.assertEqual(fmt.encode(midpoint + epsilon), one + 1)
            self.assertEqual(fmt.encode(1 + 3 * step / 2), one + 2)
            self.assertEqual(fmt.encode(-midpoint), (-one) & fmt.mask)
            self.assertEqual(fmt.encode(-midpoint - epsilon), (-one - 1) & fmt.mask)

    def test_characteristic_rounding_is_not_nearest_real(self):
        fmt = TakumFormat(8)
        # 0x60 = 2^15, 0x61 = 2^17. The encoding midpoint is 2^16,
        # whereas the arithmetic midpoint of the real values is 81920.
        self.assertEqual(fmt.encode(65536), 0x60)
        self.assertEqual(fmt.encode(65537), 0x61)
        self.assertEqual(fmt.encode(-65537), 0x9f)

    def test_saturation_nonfinite_and_zero(self):
        for width in (8, 16, 32):
            fmt = TakumFormat(width)
            for sign in (-1, 1):
                q = fmt.quantize(sign * fmt.min_positive / 2)
                self.assertTrue(q.saturated_low and q.inexact)
                self.assertEqual(fmt.decode(q.bits), sign * fmt.min_positive)
                q = fmt.quantize(sign * fmt.max_positive * 2)
                self.assertTrue(q.saturated_high and q.inexact)
                self.assertEqual(fmt.decode(q.bits), sign * fmt.max_positive)
            for v in (None, "NaR", float("nan"), float("inf"), float("-inf"), Decimal("NaN")):
                self.assertEqual(fmt.encode(v), fmt.nar)
            for v in (0, -0.0, "-0", Decimal("0")):
                self.assertEqual(fmt.encode(v), 0)

    def test_width_conversion(self):
        for bits in range(256):
            for target in (16, 32):
                self.assertEqual(TakumFormat(8).convert(bits, target), bits << (target - 8))
                self.assertEqual(TakumFormat(target).convert(bits << (target - 8), 8), bits)

    def test_t64_extension_and_roundtrip(self):
        # T64 is the vtdot.vv accumulator for T32. Takums are invariant under
        # zero extension, so every shorter pattern shifted left keeps its value.
        rng = random.Random(64)
        t64 = TakumFormat(64)
        for width in (8, 16, 32):
            fmt = TakumFormat(width)
            patterns = range(1 << width) if width == 8 else [rng.getrandbits(width) for _ in range(2000)]
            for bits in patterns:
                self.assertEqual(t64.decode(bits << (64 - width)), fmt.decode(bits))
                self.assertEqual(fmt.convert(bits, 64), bits << (64 - width))
        for bits in [rng.getrandbits(64) for _ in range(5000)] + [1, t64.nar - 1, t64.nar + 1, t64.mask]:
            self.assertEqual(t64.encode(t64.decode(bits)), bits)
        self.assertEqual(t64.encode(1), 1 << 62)
        self.assertEqual(t64.fields(1 << 62).fraction_width, 59)
        self.assertLess(t64.min_positive, TakumFormat(32).min_positive)

    def test_decimal_input_is_exact(self):
        fmt = TakumFormat(32)
        self.assertEqual(fmt.encode("0.1"), fmt.encode(Fraction(1, 10)))
        self.assertEqual(fmt.encode(Decimal("0.1")), fmt.encode(Fraction(1, 10)))

    def test_invalid_input(self):
        for width in (0, 7, 128, 8.0, True):
            with self.assertRaises(ValueError):
                TakumFormat(width)
        for bits in (-1, 256, 1.5, True):
            with self.assertRaises(ValueError):
                TakumFormat(8).decode(bits)
        with self.assertRaises(ValueError):
            TakumFormat(8).encode("invalid")
