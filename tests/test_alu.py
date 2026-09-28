from fractions import Fraction
import random
import unittest
from takum import TakumALU, TakumFormat


class ALUTests(unittest.TestCase):
    def test_known_arithmetic(self):
        for width in (8, 16, 32):
            alu, fmt = TakumALU(width), TakumFormat(width)
            for op, a, b, expected in (("add", "1.5", "2", "3.5"),
                                        ("sub", "1", "1.5", "-0.5"),
                                        ("mul", "1.5", "-2", "-3"),
                                        ("add", "-1", "1", "0")):
                result = alu.execute(op, fmt.encode(a), fmt.encode(b))
                self.assertEqual(result.bits, fmt.encode(expected))
                self.assertFalse(result.rounded.inexact)

    def test_identities_and_specials(self):
        rng = random.Random(42)
        for width in (8, 16, 32):
            alu, fmt = TakumALU(width), TakumFormat(width)
            patterns = range(256) if width == 8 else [rng.getrandbits(width) for _ in range(2000)]
            for bits in patterns:
                self.assertEqual(alu.add(bits, 0), bits)
                self.assertEqual(alu.mul(bits, fmt.encode(1)), bits)
                self.assertEqual(alu.sub(bits, bits), fmt.nar if bits == fmt.nar else 0)
                self.assertEqual(alu.mul(bits, 0), fmt.nar if bits == fmt.nar else 0)
                for op in ("add", "sub", "mul"):
                    self.assertEqual(alu.execute(op, bits, fmt.nar).bits, fmt.nar)
                    self.assertEqual(alu.execute(op, fmt.nar, bits).bits, fmt.nar)

    def test_round_once_and_status(self):
        alu, fmt = TakumALU(8), TakumFormat(8)
        result = alu.execute("mul", fmt.encode("1.125"), fmt.encode("1.125"))
        self.assertEqual(result.exact, Fraction(81, 64))
        self.assertEqual(result.value, Fraction(5, 4))
        self.assertTrue(result.rounded.inexact)
        self.assertTrue(alu.execute("mul", 1, 1).rounded.saturated_low)
        self.assertTrue(alu.execute("mul", 127, 127).rounded.saturated_high)
        self.assertTrue(alu.execute("mul", fmt.nar, 0).rounded.invalid)

    def test_exhaustive_t8_algebraic_properties(self):
        alu, fmt = TakumALU(8), TakumFormat(8)
        for a in range(256):
            for b in range(256):
                self.assertEqual(alu.add(a, b), alu.add(b, a))
                self.assertEqual(alu.mul(a, b), alu.mul(b, a))
                self.assertEqual(alu.sub(a, b), alu.add(a, fmt.negate(b)))

    def test_invalid_operation_and_bits(self):
        alu = TakumALU(8)
        with self.assertRaises(ValueError):
            alu.execute("div", 0, 0)
        with self.assertRaises(ValueError):
            alu.add(-1, 0)
