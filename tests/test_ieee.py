from fractions import Fraction
import math
import random
import struct
import unittest

from takum.codec import power_of_two
from takum.ieee import BINARY128, E4M3, E5M2, FP16, FP32, FP64, INF, NAN, is_finite


def struct_round(value, code):
    """Round a Python float through struct; None on overflow."""
    try:
        return struct.unpack("<" + code, struct.pack("<" + code, value))[0]
    except OverflowError:
        return None


def same(a, b):
    if not is_finite(a):
        return not isinstance(b, Fraction) and (math.isnan(a) and math.isnan(b) or a == b)
    return a == b


class IEEEFormatTests(unittest.TestCase):
    def test_fp16_decode_is_exhaustive_against_struct(self):
        for bits in range(1 << 16):
            expected = struct.unpack("<e", bits.to_bytes(2, "little"))[0]
            actual = FP16.decode(bits)
            if math.isnan(expected):
                self.assertTrue(math.isnan(actual), hex(bits))
            elif math.isinf(expected):
                self.assertEqual(actual, expected, hex(bits))
            else:
                self.assertEqual(actual, Fraction(expected), hex(bits))
                self.assertEqual(FP16.encode(actual) & 0x7fff, bits & 0x7fff, hex(bits))

    def test_rounding_against_struct_and_float(self):
        rng = random.Random(754)
        for _ in range(20000):
            value = math.ldexp(rng.uniform(-2, 2), rng.randint(-160, 140))
            for fmt, code in ((FP16, "e"), (FP32, "f")):
                expected = struct_round(value, code)
                actual = fmt.quantize(Fraction(value))
                if expected is None:
                    self.assertTrue(math.isinf(actual), (fmt.name, value))
                else:
                    self.assertEqual(actual, Fraction(expected), (fmt.name, value))
            # Products and sums of doubles are rounded exactly once by FP64.
            other = math.ldexp(rng.uniform(-2, 2), rng.randint(-60, 60))
            self.assertEqual(FP64.mul(Fraction(value), Fraction(other)), Fraction(value * other))
            self.assertEqual(FP64.add(Fraction(value), Fraction(other)), Fraction(value + other))

    def test_fp32_ties_and_subnormals(self):
        one_ulp = power_of_two(-23)
        self.assertEqual(FP32.quantize(1 + one_ulp / 2), 1)
        self.assertEqual(FP32.quantize(1 + 3 * one_ulp / 2), 1 + 2 * one_ulp)
        self.assertEqual(FP32.min_subnormal, power_of_two(-149))
        self.assertEqual(FP32.quantize(power_of_two(-150)), 0)
        self.assertEqual(FP32.quantize(3 * power_of_two(-151)), power_of_two(-149))
        self.assertEqual(FP32.max_finite, Fraction(struct.unpack("<f", b"\xff\xff\x7f\x7f")[0]))

    def test_ofp8_e4m3_table(self):
        # OCP OFP8 specification, E4M3: bias 7, no infinities, NaN = S.1111.111.
        self.assertEqual(E4M3.max_finite, 448)
        self.assertEqual(E4M3.decode(0x7e), 448)
        self.assertEqual(E4M3.decode(0x08), power_of_two(-6))
        self.assertEqual(E4M3.decode(0x01), power_of_two(-9))
        self.assertEqual(E4M3.decode(0x78), 256)
        self.assertTrue(math.isnan(E4M3.decode(0x7f)))
        self.assertTrue(math.isnan(E4M3.decode(0xff)))
        finite = [E4M3.decode(b) for b in range(0x7f)]
        self.assertEqual(finite, sorted(finite))
        for bits in range(256):
            value = E4M3.decode(bits)
            if is_finite(value) and value != 0:
                self.assertEqual(E4M3.encode(value), bits)
        self.assertEqual(E4M3.quantize(Fraction(464)), 448)  # tie to even mantissa 110
        self.assertTrue(math.isnan(E4M3.quantize(Fraction(465))))  # non-saturating
        self.assertTrue(math.isnan(E4M3.quantize(INF)))

    def test_ofp8_e5m2_is_truncated_fp16(self):
        self.assertEqual(E5M2.max_finite, 57344)
        self.assertEqual(E5M2.decode(0x7c), INF)
        self.assertEqual(E5M2.decode(0x01), power_of_two(-16))
        for bits in range(256):
            self.assertTrue(same(E5M2.decode(bits), FP16.decode(bits << 8)), hex(bits))
            value = E5M2.decode(bits)
            if is_finite(value):
                self.assertEqual(E5M2.quantize(value), value)

    def test_binary128_parameters(self):
        self.assertEqual(BINARY128.width, 128)
        self.assertEqual(BINARY128.emax, 16383)
        self.assertEqual(BINARY128.min_subnormal, power_of_two(-16494))
        value = Fraction(1, 3)
        error = abs(BINARY128.quantize(value) - value) / value
        self.assertLessEqual(error, power_of_two(-113))

    def test_special_arithmetic(self):
        for fmt in (FP16, FP32, BINARY128):
            self.assertTrue(math.isnan(fmt.add(INF, -INF)))
            self.assertTrue(math.isnan(fmt.mul(INF, Fraction(0))))
            self.assertTrue(math.isnan(fmt.add(NAN, Fraction(1))))
            self.assertEqual(fmt.mul(-INF, Fraction(-2)), INF)
            self.assertEqual(fmt.add(fmt.max_finite, fmt.max_finite), INF)
            # Huge finite operands must not go through float().
            self.assertEqual(fmt.add(Fraction(10) ** 400, -INF), -INF)
        self.assertTrue(math.isnan(E4M3.add(E4M3.max_finite, E4M3.max_finite)))


if __name__ == "__main__":
    unittest.main()
