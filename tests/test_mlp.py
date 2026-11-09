from fractions import Fraction
import math
import unittest

from takum.codec import TakumFormat
from takum.ieee import E4M3, FP16, INF, NAN, is_finite
from takum.mlp import mlp_fast, mlp_instructions, mlp_simulated, network, reference_mlp, scaled
from takum.spmv import (ABLATION, CSR, VARIANTS, Variant, count_instructions, relu, spmv_simulated,
                        vector_per_strip)
from takum.zvtakum import TakumVectorMachine


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, float) and isinstance(b, float) and (a == b or math.isnan(a) and math.isnan(b))
    return a == b


class DenseLayerTests(unittest.TestCase):
    def test_simulator_and_fast_path_agree_bit_for_bit(self):
        # 20 inputs give rows longer than VLMAX at SEW=8 (16 with VLEN=128);
        # scales 2^-16 and 2^16 make the IEEE formats underflow and overflow.
        weights, x = network(7, sizes=(20, 12, 5))
        for k in (-16, 0, 16):
            xs = scaled(x, k)
            for variant in VARIANTS + ABLATION:
                fast, _ = mlp_fast(weights, xs, variant)
                simulated, machines = mlp_simulated(weights, xs, variant)
                self.assertTrue(all(same(p, q) for p, q in zip(fast, simulated)), (variant.name, k))
                counts = mlp_instructions(weights, variant)
                self.assertEqual(counts["vector"], sum(m.vector_count() for m in machines), variant.name)
                self.assertEqual(counts["scalar"], sum(m.scalar_count() for m in machines), variant.name)

    def test_dense_kernel_uses_contiguous_loads_and_relu(self):
        W = CSR.dense([[1, -2, 3], [-1, -1, -1]])
        for variant, relu_name in ((Variant("T16", "takum", 16), "vmax.vx"), (Variant("FP16", "ieee", 16), "vfmax.vf")):
            y, machine = spmv_simulated(W, variant, [Fraction(1)] * 3, dense=True, relu=True)
            self.assertEqual(y, [Fraction(2), Fraction(0)])
            self.assertEqual(machine.counts[relu_name], 1)
            self.assertNotIn("vluxei32.v", machine.counts)
            self.assertEqual(vector_per_strip(variant, dense=True), vector_per_strip(variant) - 1)
        with self.assertRaises(ValueError):
            spmv_simulated(CSR.from_triplets(2, 2, [(0, 0, Fraction(1))]), variant, dense=True)

    def test_sparse_counts_unchanged(self):
        # T8, VLMAX 16: strips 1 + 2 + 0 + 3; one narrowing chunk.
        lengths = [3, 17, 0, 40]
        self.assertEqual(count_instructions(lengths, VARIANTS[0]),
                         {"vector": 4 * 4 + 5 * 6 + 4 * 1, "scalar": 7 * 4 + 6 * 6 + 6 * 1,
                          "total": 50 + 70, "strips": 6})

    def test_takum_relu_is_signed_integer_max(self):
        fmt = TakumFormat(8)
        m = TakumVectorMachine(128)
        m.vsetvli(16, 8)
        for start in range(0, 256, 16):
            for i in range(16):
                m.set(4, i, 8, start + i)
            m.vmax_vx(6, 4)
            expected = relu([fmt.decode(start + i) for i in range(16)], Variant("T8", "takum", 8))
            self.assertEqual([fmt.decode(m.get(6, i, 8)) for i in range(16)], expected)

    def test_ieee_relu_follows_fmax(self):
        variant = Variant("FP16", "ieee", 16)
        self.assertEqual(relu([NAN, -INF, INF, Fraction(-3), Fraction(5)], variant),
                         [0, 0, INF, 0, 5])
        self.assertEqual(relu([None, Fraction(-1), Fraction(2)], Variant("T8", "takum", 8)), [0, 0, 2])
        m = TakumVectorMachine(128)
        m.fp8 = E4M3
        m.vsetvli(16, 8)
        for start in range(0, 256, 16):
            for i in range(16):
                m.set(4, i, 8, start + i)
            m.vfmax_vf(6, 4)
            for i in range(16):
                value = E4M3.decode(m.get(6, i, 8))
                self.assertTrue(is_finite(value) and value >= 0, hex(start + i))
        m.vsetvli(1, 16)
        m.set(4, 0, 16, FP16.encode(INF))
        m.vfmax_vf(6, 4)
        self.assertEqual(FP16.decode(m.get(6, 0, 16)), INF)

    def test_network_is_homogeneous(self):
        weights, x = network(3, sizes=(16, 8, 4))
        base = reference_mlp(weights, x)
        for k in (-8, 8):
            self.assertEqual(reference_mlp(weights, scaled(x, k)), scaled(base, k))


if __name__ == "__main__":
    unittest.main()
