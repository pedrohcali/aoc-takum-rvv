import contextlib
import io
import json
import unittest
from takum.cli import main


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            main(list(args))
        return json.loads(buffer.getvalue())

    def test_encode_decode_and_raw_operation(self):
        self.assertEqual(self.run_cli("encode", "1.5")["hex"], "0x44")
        self.assertEqual(self.run_cli("decode", "0x44")["value"], "3/2")
        self.assertEqual(self.run_cli("add", "--raw", "0x40", "0x40")["result"]["value"], "2")
        self.assertEqual(self.run_cli("add", "NaR", "1")["exact_result_of_quantized_inputs"], "NaR")

    def test_demo_all_widths(self):
        output = self.run_cli("demo")
        self.assertEqual({item["width"] for item in output}, {8, 16, 32})
        self.assertEqual(len(output), 15)

    def test_invalid_bits_fail_cleanly(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["decode", "0x100"])
        self.assertEqual(error.exception.code, 2)
