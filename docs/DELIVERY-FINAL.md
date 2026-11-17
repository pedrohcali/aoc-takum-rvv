# Entrega final: 17/11/2026

O enunciado situa a entrega no dia da segunda prova. A apresentação dura
15 minutos e inclui a demonstração funcional.

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
make verify           # suíte e comparação com a referência C
make vector           # demonstração das instruções vetoriais
make fetch            # verifica as 358 matrizes publicadas
make bench BENCH_DIR=output/repeticao  # nova medição de SpMV
make mlp              # camadas densas (aprendizado de máquina)
make isa              # análise estática dos decodificadores
make summary          # recompõe os resumos a partir dos CSVs
make package          # compila os PDFs finais e gera output/entrega-final.zip
```

## Conferência de 17 de novembro

No Mac ARM, a suíte passou nos 52 testes e a referência C com o patch de
portabilidade coincidiu nas 548.793 comparações. A demonstração executou as
cinco instruções, a SpMV e a camada densa com ReLU.

Repetimos os experimentos em diretórios vazios com os mesmos parâmetros da
execução Linux. Conferimos as 3.580 linhas de SpMV (358 matrizes × 10 variantes)
e as 5.760 linhas das redes (64 redes × 9 escalas × 10 variantes). As contagens
de instruções e eventos de faixa coincidiram. A maior diferença absoluta entre
os erros em escala log10 foi inferior a 8 × 10⁻¹⁵ na SpMV e a 3 × 10⁻⁹ nas
redes. Os valores arredondados usados no artigo e nos slides coincidiram.

O artigo da fase 1 (`paper/phase1.tex`, `output/pdf/phase1.pdf`) foi mantido
sem alterações, como registro da primeira entrega.
