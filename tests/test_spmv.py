from fractions import Fraction
import math
from pathlib import Path
import random
import tempfile
import unittest

from takum.ieee import BINARY128
from takum.spmv import (ABLATION, CSR, VARIANTS, count_instructions, log10_relative_error,
                        quantize_values, read_matrix_market, reference_spmv, relu, spmv_fast,
                        spmv_simulated)


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, float) and isinstance(b, float) and (a == b or math.isnan(a) and math.isnan(b))
    return a == b


def random_matrix(rng, rows, cols, density, spread):
    triplets = [(i, j, Fraction(rng.uniform(-1, 1)) * Fraction(2) ** rng.randint(-spread, spread))
                for i in range(rows) for j in range(cols) if rng.random() < density]
    return CSR.from_triplets(rows, cols, triplets)


class SpMVTests(unittest.TestCase):
    def test_simulator_and_fast_path_agree_bit_for_bit(self):
        rng = random.Random(2026)
        # Wide spread exercises IEEE overflow/underflow and Takum saturation;
        # 40 columns gives rows longer than VLMAX for every SEW.
        matrices = [random_matrix(rng, 9, 40, 0.5, 4), random_matrix(rng, 7, 7, 0.4, 20),
                    CSR.from_triplets(3, 3, [])]
        x_exact = [Fraction(rng.uniform(-2, 2)) for _ in range(40)]
        for A in matrices:
            x = x_exact[:A.n_cols]
            for variant in VARIANTS + ABLATION:
                for vlen in (128, 256):
                    a, _ = quantize_values(A.values, variant)
                    xq, _ = quantize_values(x, variant)
                    fast = spmv_fast(A, variant, a, xq, vlen)
                    simulated, machine = spmv_simulated(A, variant, x, vlen)
                    self.assertTrue(all(same(p, q) for p, q in zip(fast, simulated)), (variant.name, vlen))
                    counts = count_instructions(A.row_lengths(), variant, vlen)
                    self.assertEqual(counts["vector"], machine.vector_count(), variant.name)
                    self.assertEqual(counts["scalar"], machine.scalar_count(), variant.name)

    def test_grouped_kernels(self):
        rng = random.Random(17)
        matrices = (random_matrix(rng, 9, 45, 0.9, 1),
                    CSR.dense([[rng.randrange(-4, 5) for _ in range(45)] for _ in range(9)]))
        x = [Fraction((i % 7) - 3, 4) for i in range(45)]
        for dense, matrix in zip((False, True), matrices):
            for variant in VARIANTS:
                a, _ = quantize_values(matrix.values, variant)
                xq, _ = quantize_values(x, variant)
                for lmul in (2, 4, 8):
                    with self.subTest(dense=dense, variant=variant.name, lmul=lmul):
                        if lmul == 8 or (not dense and lmul == 4 and variant.sew == 8):
                            with self.assertRaises(ValueError):
                                spmv_simulated(matrix, variant, x, lmul=lmul, dense=dense)
                            with self.assertRaises(ValueError):
                                count_instructions(matrix.row_lengths(), variant, lmul=lmul, dense=dense)
                            with self.assertRaises(ValueError):
                                spmv_fast(matrix, variant, a, xq, lmul=lmul, dense=dense)
                            continue
                        fast = spmv_fast(matrix, variant, a, xq, lmul=lmul, dense=dense)
                        y, m = spmv_simulated(matrix, variant, x, lmul=lmul, dense=dense, relu=dense)
                        self.assertEqual(y, relu(fast, variant) if dense else fast)
                        counts = count_instructions(matrix.row_lengths(), variant, lmul=lmul,
                                                    dense=dense, relu=dense)
                        self.assertEqual((m.vector_count(), m.scalar_count()),
                                         (counts["vector"], counts["scalar"]))

    def test_vtdot_removes_instructions(self):
        lengths = [3, 17, 0, 40]
        takum = count_instructions(lengths, VARIANTS[0])["vector"]
        fp8 = count_instructions(lengths, VARIANTS[1])["vector"]
        self.assertLess(takum, fp8)
        self.assertEqual(count_instructions(lengths, VARIANTS[3])["strips"], 1 + 3 + 0 + 5)

    def test_reference_and_error(self):
        A = CSR.from_triplets(2, 2, [(0, 0, Fraction(1, 3)), (0, 1, Fraction(2, 3)), (1, 1, Fraction(5))])
        reference = reference_spmv(A)
        self.assertEqual(reference[1], 5)
        self.assertLess(abs(reference[0] - 1), Fraction(1, 2 ** 110))
        self.assertEqual(log10_relative_error(reference, reference), -math.inf)
        self.assertEqual(log10_relative_error([math.nan, Fraction(5)], reference), math.inf)
        self.assertEqual(log10_relative_error([None, Fraction(5)], reference), math.inf)
        self.assertIsNone(log10_relative_error([Fraction(0)], [Fraction(0)]))
        self.assertAlmostEqual(log10_relative_error([Fraction(11, 10)], [Fraction(1)]), -1)
        self.assertEqual(BINARY128.quantize(Fraction(5)), 5)

    def test_matrix_market_reader(self):
        text = ("%%MatrixMarket matrix coordinate real symmetric\n% comment\n"
                "3 3 3\n1 1 1.5e0\n3 1 -0.25\n2 2 7\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "m.mtx"
            path.write_text(text)
            A = read_matrix_market(path, "m")
            self.assertEqual((A.n_rows, A.nnz), (3, 4))
            self.assertEqual(A.row_ptr, [0, 2, 3, 4])
            self.assertEqual(A.values, [Fraction(3, 2), Fraction(-1, 4), Fraction(7), Fraction(-1, 4)])
            path.write_text("%%MatrixMarket matrix coordinate pattern skew-symmetric\n2 2 1\n2 1\n")
            self.assertEqual(read_matrix_market(path).values, [Fraction(-1), Fraction(1)])
            path.write_text("%%MatrixMarket matrix coordinate complex general\n1 1 1\n1 1 1 0\n")
            with self.assertRaises(ValueError):
                read_matrix_market(path)


if __name__ == "__main__":
    unittest.main()
