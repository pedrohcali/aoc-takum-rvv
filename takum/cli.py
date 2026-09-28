"""Command-line demo. Decimal strings enter the encoder without a float detour."""
import argparse
from dataclasses import asdict
import json
from . import TakumALU, TakumFormat


def describe(fmt, bits):
    fields = fmt.fields(bits)
    return {"hex": f"0x{bits:0{fmt.width // 4}x}",
            "binary": f"{bits:0{fmt.width}b}",
            "value": "NaR" if fields.value is None else str(fields.value),
            "fields": asdict(fields)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Linear Takum functional ALU")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("encode", "decode", "add", "sub", "mul"):
        p = sub.add_parser(command)
        p.add_argument("--width", type=int, choices=(8, 16, 32), default=8)
        p.add_argument("a", help="Numeric value, or raw bits for decode")
        if command in ("add", "sub", "mul"):
            p.add_argument("b", help="Numeric value (decimal, fraction or NaR)")
            p.add_argument("--raw", action="store_true", help="Treat operands as raw bit patterns")
    sub.add_parser("demo")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            output = []
            for width in (8, 16, 32):
                fmt, alu = TakumFormat(width), TakumALU(width)
                for op, a, b in (("add", "1.5", "2.25"), ("sub", "1", "1"),
                                 ("mul", "1.5", "-2"), ("mul", "1e70", "1e70"),
                                 ("add", "NaR", "1")):
                    result = alu.execute(op, fmt.encode(a), fmt.encode(b))
                    output.append({"width": width, "operation": op, "inputs": [a, b],
                                   "result": describe(fmt, result.bits),
                                   "status": asdict(result.rounded)})
        else:
            fmt = TakumFormat(args.width)
            if args.command == "decode":
                output = describe(fmt, int(args.a, 0))
            elif args.command == "encode":
                q = fmt.quantize(args.a)
                output = {**describe(fmt, q.bits), "status": asdict(q)}
            else:
                a = int(args.a, 0) if args.raw else fmt.encode(args.a)
                b = int(args.b, 0) if args.raw else fmt.encode(args.b)
                result = TakumALU(args.width).execute(args.command, a, b)
                output = {"a": describe(fmt, a), "b": describe(fmt, b),
                          "exact_result_of_quantized_inputs": "NaR" if result.exact is None else str(result.exact),
                          "result": describe(fmt, result.bits),
                          "status": asdict(result.rounded)}
    except (ValueError, ZeroDivisionError) as error:
        parser.error(str(error))
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
