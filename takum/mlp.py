"""Dense neural network layers on the vector kernel (machine learning case).

A bias-free fully connected layer y = ReLU(W x) is the CSR kernel of
spmv.py on a full matrix, with x loaded contiguously and a ReLU after the
narrowing conversion. The network has three layers (64 -> 64 -> 64 -> 16),
ReLU after the first two, and He-initialised Gaussian weights; the input is
standard Gaussian. Weights and inputs are binary64 numbers taken as exact
fractions, so every format starts from the same exact network.

Without bias the network is positively homogeneous: scaling the input by
2^k scales every activation and the output by exactly 2^k. The scale sweep
therefore isolates the effect of dynamic range: an IEEE format has the same
relative error at every scale that stays in range, while a takum's
precision depends on the magnitude.
"""

from fractions import Fraction
import math
import random

from .codec import power_of_two
from .spmv import (CSR, Variant, count_instructions, log10_relative_error, quantize_values, reference_spmv,
                   relu, spmv_fast, spmv_simulated)

LAYERS = (64, 64, 64, 16)
SCALES = tuple(range(-16, 17, 4))


def network(seed: int, sizes=LAYERS):
    """(weight matrices, input vector) of one random network."""
    rng = random.Random(seed)
    weights = []
    for n_in, n_out in zip(sizes, sizes[1:]):
        std = math.sqrt(2 / n_in)
        weights.append(CSR.dense([[rng.gauss(0, std) for _ in range(n_in)] for _ in range(n_out)],
                                 f"layer{len(weights)}"))
    x = [Fraction(rng.gauss(0, 1)) for _ in range(sizes[0])]
    return weights, x


def scaled(x, k: int):
    factor = power_of_two(k)
    return [v * factor for v in x]


def reference_mlp(weights, x):
    """binary128 reference: every product and sum rounded to binary128,
    ReLU exact."""
    for index, W in enumerate(weights):
        x = reference_spmv(W, x)
        if index < len(weights) - 1:
            x = [v if v > 0 else Fraction(0) for v in x]
    return x


def mlp_fast(weights, x, variant: Variant, vlen: int = 128, lmul: int = 1, quantized_weights=None):
    """Network output in the variant's format and the number of input and
    weight entries that saturated (takum) or overflowed/flushed (IEEE)."""
    xq, stats = quantize_values(x, variant)
    events = stats.saturated + stats.overflow + stats.flushed_to_zero
    for index, W in enumerate(weights):
        if quantized_weights is None:
            a, wstats = quantize_values(W.values, variant)
            events += wstats.saturated + wstats.overflow + wstats.flushed_to_zero
        else:
            a = quantized_weights[index]
        xq = spmv_fast(W, variant, a, xq, vlen, lmul, dense=True)
        if index < len(weights) - 1:
            xq = relu(xq, variant)
    return xq, events


def mlp_simulated(weights, x, variant: Variant, vlen: int = 128, lmul: int = 1, trace: bool = False):
    """Run every layer on the functional machine. Returns (output, machines)."""
    machines = []
    for index, W in enumerate(weights):
        x, machine = spmv_simulated(W, variant, x, vlen, lmul, trace=trace, dense=True,
                                    relu=index < len(weights) - 1)
        machines.append(machine)
    return x, machines


def mlp_instructions(weights, variant: Variant, vlen: int = 128, lmul: int = 1) -> dict:
    total = {"vector": 0, "scalar": 0, "total": 0, "strips": 0}
    for index, W in enumerate(weights):
        counts = count_instructions(W.row_lengths(), variant, vlen, lmul, dense=True,
                                    relu=index < len(weights) - 1)
        for key in total:
            total[key] += counts[key]
    total["macs"] = sum(W.nnz for W in weights)
    return total


def mlp_error(weights, x, variant: Variant, reference, vlen: int = 128, lmul: int = 1, quantized_weights=None):
    y, events = mlp_fast(weights, x, variant, vlen, lmul, quantized_weights)
    return log10_relative_error(y, reference), events
