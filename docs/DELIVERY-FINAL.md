# Entrega final: 17/11/2026

## Correspondência com o enunciado

| Requisito | Evidência |
|---|---|
| Fase 1: extração S/D/R/C/F | `takum/codec.py`, `results/t8-values.csv` |
| Fase 1: soma, subtração e multiplicação T8/T16/T32 | `takum/alu.py`, `tests/`, `docs/VALIDATION.md` |
| Fase 2: `vtadd.vv`, `vtsub.vv`, `vtmul.vv`, `vtdot.vv`, `vncvt.t.t` | `takum/zvtakum.py`, `docs/ZVTAKUM.md`, `tests/test_zvtakum.py`, figura 1 do artigo |
| Fase 2: integração ao modelo vetorial RISC-V | `takum/rvv.py` (`vl`, `vtype`, máscara, grupos de registradores) |
| Fase 3: SpMV com matrizes esparsas | `takum/spmv.py`, `scripts/run_benchmark.py` |
| Fase 3: comparação com FP8, FP16 e FP32 | `takum/ieee.py` (E4M3, E5M2, binary16, binary32), `results/spmv-errors.csv` |
| Fase 3: erro relativo acumulado contra Float128 | Referência binary128; `results/spmv-cdf.csv`, figura 2 do artigo |
| Fase 3: complexidade de instruções e CSRs | Contagem dinâmica e estática: `docs/EVALUATION.md` §4, `docs/ZVTAKUM.md` §4 e §5, seção IV-B e IV-C e tabelas II e III do artigo |
| Objetivo 1: impacto da representação na ISA e na ALU | `scripts/isa_analysis.py`, `results/isa-encodings.csv`, tabelas II e III do artigo |
| Objetivo 4: kernels de aprendizado de máquina | `takum/mlp.py`, `scripts/run_mlp.py`, `results/mlp-*.csv`, `docs/EVALUATION.md` §6, figura 3 do artigo |
| Código-fonte e testes automáticos | `takum/`, `tests/`, `scripts/run_tests.py`, CI |
| Artigo IEEE em inglês, até 6 páginas | `paper/final.tex`, `output/pdf/final.pdf` (5 páginas) |
| Slides | `slides/final-slides.tex`, `output/pdf/final-slides.pdf` |
| Demonstração funcional | `python3 -m takum vector-demo`, `docs/DEMO.md` |
| Registro do processo de projeto | `docs/DECISIONS.md`, histórico do git |
| Repositório organizado | README, `docs/`, Makefile |

## Comandos

```sh
make test             # suíte completa
make vector           # demonstração das instruções vetoriais
make fetch bench      # benchmark com as matrizes reais
make mlp              # camadas densas (aprendizado de máquina)
make isa              # análise estática dos decodificadores
make paper slides     # PDFs
```

O artigo da fase 1 (`paper/phase1.tex`, `output/pdf/phase1.pdf`) foi mantido
sem alterações, como registro da primeira entrega.
