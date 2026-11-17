from fractions import Fraction
import math
import random
import unittest

from takum import TakumALU, TakumFormat
from takum.ieee import FP16, FP32
from takum.rvv import VectorMachine
from takum.zvtakum import ENCODINGS, TakumVectorMachine, decode, encode


def load(machine, reg, eew, values):
    for i, value in enumerate(values):
        machine.set(reg, i, eew, value)


class VectorMachineTests(unittest.TestCase):
    def test_vsetvli_and_vlmax(self):
        m = VectorMachine(128)
        self.assertEqual(m.vsetvli(100, 8), 16)
        self.assertEqual(m.vsetvli(100, 32, 2), 8)
        self.assertEqual(m.vsetvli(3, 16), 3)
        m.vsetvli(None, 32, 2)  # vsetvli zero, zero keeps vl
        self.assertEqual(m.vl, 3)
        with self.assertRaises(ValueError):
            m.vsetvli(4, 12)

    def test_keep_vl_trace_and_rejected_configurations(self):
        m = VectorMachine(128, trace=True)
        m.vsetvli(3, 16)
        self.assertEqual(m.vsetvli(None, 32, 2), 3)
        self.assertEqual(m.trace[-1], "vsetvli zero, zero, e32, m2, tu, mu")
        for avl, sew, lmul, immediate in ((None, 32, 1, False), (None, 8, 1, False),
                                          (None, 32, 2, True), (-1, 16, 1, False),
                                          (32, 16, 1, True)):
            with self.subTest(avl=avl, sew=sew, lmul=lmul, immediate=immediate):
                with self.assertRaises(ValueError):
                    m.vsetvli(avl, sew, lmul, immediate)
                self.assertEqual((m.vl, m.sew, m.lmul, len(m.trace)), (3, 32, 2, 2))

    def test_loads_stores_gather_and_masks(self):
        m = VectorMachine(128)
        data = m.alloc(64)
        m.store_array(data, list(range(10, 26)), 16)
        m.vsetvli(8, 16)
        m.vle(4, data, 16)
        self.assertEqual([m.get(4, i, 16) for i in range(8)], list(range(10, 18)))
        offsets = m.alloc(32)
        m.store_array(offsets, [14, 0, 2, 30], 32)
        m.vsetvli(4, 16)
        m.vle(8, offsets, 32)
        m.vluxei(6, data, 8, 32)
        self.assertEqual([m.get(6, i, 16) for i in range(4)], [17, 10, 11, 25])
        # Mask 0b0101 and tail: inactive and tail elements stay undisturbed.
        load(m, 10, 16, [99] * 8)
        m.vregs[0] = 0b0101
        m.vle(10, data, 16, vm=False)
        self.assertEqual([m.get(10, i, 16) for i in range(8)], [10, 99, 12, 99, 99, 99, 99, 99])
        with self.assertRaises(ValueError):
            m.vsetvli(4, 8)
            m.vle(13, offsets, 32)  # EMUL 4 group must be aligned

    def test_ieee_baseline_instructions(self):
        m = VectorMachine(128)
        m.vsetvli(3, 16)
        load(m, 4, 16, [FP16.encode(Fraction(v)) for v in ("1.5", "-2", "1e-3")])
        load(m, 5, 16, [FP16.encode(Fraction(v)) for v in ("2", "0.25", "3")])
        m.vfwmul_vv(6, 4, 5)
        products = [FP32.decode(m.get(6, i, 32)) for i in range(3)]
        exact = [FP16.decode(m.get(4, i, 16)) * FP16.decode(m.get(5, i, 16)) for i in range(3)]
        self.assertEqual(products, exact)  # FP16 x FP16 is exact in FP32
        m.vsetvli(None, 32, 2)
        m.set(2, 0, 32, FP32.encode(Fraction(10)))
        m.vfredosum_vs(2, 6, 2)
        expected = Fraction(10)
        for p in products:
            expected = FP32.add(expected, p)
        self.assertEqual(FP32.decode(m.get(2, 0, 32)), expected)
        m.vsetvli(3, 16)
        m.vfncvt_f_f_w(8, 6)
        self.assertEqual([FP16.decode(m.get(8, i, 16)) for i in range(3)],
                         [FP16.quantize(p) for p in products])


class ZvtakumTests(unittest.TestCase):
    def test_encoding_roundtrip_and_fields(self):
        for mnemonic in ENCODINGS:
            for vd, vs2, vs1, vm in ((1, 2, 3, True), (31, 0, 17, False)):
                word = encode(mnemonic, vd, vs2, vs1, vm)
                name, d, s2, s1, mask = decode(word)
                self.assertEqual((name, d, s2, mask), (mnemonic, vd, vs2, vm))
                self.assertEqual(word & 0x7f, 0b1011011)  # custom-2
                if mnemonic != "vncvt.t.t":
                    self.assertEqual(s1, vs1)
        self.assertEqual(len({ENCODINGS[m][:2] for m in ENCODINGS}), 5)
        with self.assertRaises(ValueError):
            decode(0x00000057)  # an OP-V word is not Zvtakum

    def test_elementwise_matches_scalar_alu(self):
        rng = random.Random(5)
        for sew in (8, 16, 32):
            m, alu = TakumVectorMachine(128), TakumALU(sew)
            vl = m.vsetvli(64, sew)
            a = [rng.getrandbits(sew) for _ in range(vl)]
            b = [rng.getrandbits(sew) for _ in range(vl)]
            a[0], b[1] = TakumFormat(sew).nar, 0
            load(m, 4, sew, a)
            load(m, 5, sew, b)
            for name in ("add", "sub", "mul"):
                getattr(m, f"vt{name}_vv")(6, 4, 5)
                self.assertEqual([m.get(6, i, sew) for i in range(vl)],
                                 [alu.execute(name, x, y).bits for x, y in zip(a, b)], (sew, name))

    def test_masked_elementwise_and_vl_zero(self):
        m = TakumVectorMachine(128)
        fmt = TakumFormat(8)
        m.vsetvli(4, 8)
        load(m, 4, 8, [fmt.encode(1)] * 16)
        load(m, 6, 8, [0x11] * 16)
        m.vregs[0] = 0b1010
        m.vtadd_vv(6, 4, 4, vm=False)
        two = fmt.encode(2)
        self.assertEqual([m.get(6, i, 8) for i in range(6)], [0x11, two, 0x11, two, 0x11, 0x11])
        before = m.get(6, 0, 16)
        m.vsetvli(0, 8)
        m.vtdot_vv(6, 4, 4)  # vl = 0: no element is written
        self.assertEqual(m.get(6, 0, 16), before)

    def test_vtdot_is_exact_then_rounded_once(self):
        rng = random.Random(9)
        for sew in (8, 16, 32):
            source, acc = TakumFormat(sew), TakumFormat(2 * sew)
            for fused in (True, False):
                m = TakumVectorMachine(128, vtdot_fused=fused)
                vl = m.vsetvli(64, sew)
                a = [source.encode(Fraction(rng.uniform(-4, 4))) for _ in range(vl)]
                b = [source.encode(Fraction(rng.uniform(-4, 4))) for _ in range(vl)]
                load(m, 4, sew, a)
                load(m, 5, sew, b)
                start = acc.encode(Fraction(1, 3))
                m.set(2, 0, 2 * sew, start)
                m.vtdot_vv(2, 4, 5)
                products = [source.decode(x) * source.decode(y) for x, y in zip(a, b)]
                if fused:
                    expected = acc.encode(acc.decode(start) + sum(products))
                else:
                    total = acc.decode(start)
                    for p in products:
                        total = acc.decode(acc.encode(total + acc.decode(acc.encode(p))))
                    expected = acc.encode(total)
                self.assertEqual(m.get(2, 0, 2 * sew), expected, (sew, fused))

    def test_vtdot_nar_and_saturation(self):
        m, fmt = TakumVectorMachine(128), TakumFormat(8)
        m.vsetvli(2, 8)
        load(m, 4, 8, [fmt.nar - 1] * 2)
        load(m, 5, 8, [fmt.nar - 1] * 2)
        m.vtdot_vv(2, 4, 5)
        self.assertEqual(m.get(2, 0, 16), TakumFormat(16).nar - 1)  # saturates, never NaR
        load(m, 5, 8, [fmt.nar, 0])
        m.vtdot_vv(2, 4, 5)
        self.assertEqual(m.get(2, 0, 16), TakumFormat(16).nar)

    def test_vncvt_matches_convert(self):
        rng = random.Random(11)
        for sew in (8, 16, 32):
            m = TakumVectorMachine(128)
            vl = m.vsetvli(64, sew)
            wide = [rng.getrandbits(2 * sew) for _ in range(vl)]
            load(m, 6, 2 * sew, wide)
            m.vncvt_t_t(4, 6)
            self.assertEqual([m.get(4, i, sew) for i in range(vl)],
                             [TakumFormat(2 * sew).convert(w, sew) for w in wide])

    def test_operand_groups_checked_before_execution(self):
        m = TakumVectorMachine(128)
        m.vsetvli(3, 16, 2)
        for instruction, operands in ((m.vtdot_vv, (1, 3, 8)), (m.vtdot_vv, (1, 4, 5)),
                                      (m.vtdot_vv, (32, 4, 8)), (m.vtdot_vv, (2, -2, 8)),
                                      (m.vncvt_t_t, (3, 8)), (m.vncvt_t_t, (4, 6)),
                                      (m.vncvt_t_t, (10, 8)), (m.vncvt_t_t, (0, 8, False)),
                                      (m.vtadd_vv, (0, 4, 8, False))):
            with self.subTest(instruction=instruction.__name__, operands=operands):
                with self.assertRaises(ValueError):
                    instruction(*operands)
        self.assertEqual(sum(m.counts.values()), 1)
        # Reduction destination names one register, even with LMUL > 1.
        m.vtdot_vv(3, 4, 8)
        m.vncvt_t_t(8, 8)  # low part of the wide source may overlap

    def test_t64_is_only_a_wide_operand(self):
        m = TakumVectorMachine(128)
        m.vsetvli(0, 64)
        for instruction in (m.vtadd_vv, m.vtsub_vv, m.vtmul_vv, m.vtdot_vv, m.vncvt_t_t):
            args = (4, 8) if instruction == m.vncvt_t_t else (4, 8, 12)
            with self.subTest(instruction=instruction.__name__), self.assertRaises(ValueError):
                instruction(*args)

    def test_trace_shows_encoding(self):
        m = TakumVectorMachine(128, trace=True)
        m.vsetvli(4, 16)
        m.vtmul_vv(1, 2, 3)
        self.assertIn(f"0x{encode('vtmul.vv', 1, 2, 3):08x}", m.trace[-1])
        self.assertEqual(m.counts["vtmul.vv"], 1)


if __name__ == "__main__":
    unittest.main()
