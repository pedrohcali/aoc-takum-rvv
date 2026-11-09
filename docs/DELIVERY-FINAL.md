# Entrega final: 11/11/2026

## Correspondência com o enunciado

| Requisito | Evidência |
|---|---|
| Fase 1: extração S/D/R/C/F | `takum/codec.py`, `results/t8-values.csv` |
| Fase 1: soma, subtração e multiplicação T8/T16/T32 | `takum/alu.py`, `tests/`, `docs/VALIDATION.md` |
| Fase 2: `vtadd.vv`, `vtsub.vv`, `vtmul.vv`, `vtdot.vv`, `vncvt.t.t` | `takum/zvtakum.py`, `docs/ZVTAKUM.md`, `tests/test_zvtakum.py` |
| Fase 2: integração ao modelo vetorial RISC-V | `takum/rvv.py` (`vl`, `vtype`, máscara, grupos de registradores) |
| Fase 3: SpMV com matrizes esparsas | `takum/spmv.py`, `scripts/run_benchmark.py` |
| Fase 3: comparação com FP8, FP16 e FP32 | `takum/ieee.py` (E4M3, E5M2, binary16, binary32), `results/spmv-errors.csv` |
| Fase 3: erro relativo acumulado contra Float128 | Referência binary128; `results/spmv-cdf.csv`, figura 1 do artigo |
| Fase 3: complexidade de instruções e CSRs | `docs/EVALUATION.md` seção 4, `docs/ZVTAKUM.md` seção 5, tabela II do artigo |
| Código-fonte e testes automáticos | `takum/`, `tests/`, `scripts/run_tests.py`, CI |
| Artigo IEEE em inglês, até 6 páginas | `paper/final.tex`, `output/pdf/final.pdf` |
| Slides | `slides/final-slides.tex`, `output/pdf/final-slides.pdf` |
| Demonstração funcional | `python3 -m takum vector-demo`, `docs/DEMO.md` |
| Repositório organizado | README, `docs/`, Makefile |

## Comandos

```sh
make test             # suíte completa
make vector           # demonstração das instruções vetoriais
make fetch bench      # benchmark com as matrizes reais
make paper slides     # PDFs
```

O artigo da fase 1 (`paper/phase1.tex`, `output/pdf/phase1.pdf`) foi mantido
sem alterações, como registro da primeira entrega.
