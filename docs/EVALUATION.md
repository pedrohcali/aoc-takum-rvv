# Avaliação experimental (fase 3)

## 1. Pergunta

Comparar a SpMV `y = A·x` em Takum (T8, T16, T32) com IEEE 754 / OFP8
(E4M3, E5M2, binary16, binary32) quanto a:

1. erro relativo acumulado em relação à precisão quádrupla (binary128);
2. número de instruções executadas pelo kernel vetorial;
3. estado de controle e status (CSRs) exigido.

## 2. Método

| Item | Escolha | Motivo |
|---|---|---|
| Matrizes | Todas as matrizes reais, inteiras ou de padrão do NIST Matrix Market em formato de coordenadas, com até 50.000 não nulos após expandir as simétricas: 358 matrizes, 3.054.096 não nulos | Mesmo limite de Hunhold (2025). A SuiteSparse, usada por ele, recusou todos os downloads durante o projeto (HTTP 403 do armazenamento, inclusive para matrizes conhecidas); as coleções do Matrix Market também fazem parte da SuiteSparse |
| Leitura | Valores decimais do Matrix Market lidos como frações exatas; simétricas expandidas | Nenhum arredondamento antes do formato avaliado |
| Vetor `x` | Uns | Representável em todos os formatos; o erro vem de A e da aritmética |
| Referência | binary128: entradas, produtos e somas arredondados em binary128 | Pedido do enunciado (Float128) |
| Acumulação | 2·SEW em todos: T8→T16, T16→T32, T32→T64, FP8→binary16, binary16→binary32, binary32→binary64 | Comparação justa |
| Erro da SpMV | `‖y_f − y_ref‖₂ / ‖y_ref‖₂`, em log10 | Uma medida por matriz, como na Fig. 3 de Hunhold |
| Erro de conversão | `‖A_f − A‖_F / ‖A‖_F` | Separa o efeito do formato do efeito da aritmética |
| Valores especiais | NaN ou ∞ em `y_f` conta como erro infinito; matrizes com `y_ref = 0` são excluídas | |
| Instruções | VLEN = 128, LMUL = 1; contagem dinâmica completa (vetoriais e escalares) | Ver `docs/ZVTAKUM.md`, seção 7 |
| Ablação | `vtdot.vv` arredondando cada passo em 2·SEW | Separa o efeito da soma exata |

As normas são calculadas exatamente: os valores são escalados para inteiros por
um denominador comum, que se cancela na razão. Só o log10 final é de ponto
flutuante.

**Por que confiar no caminho rápido.** O simulador executa cada instrução e é
lento demais para ~1.400 matrizes. O benchmark usa `spmv_fast`, que aplica a
mesma aritmética sem o simulador, e `count_instructions`, que conta pela fórmula
do kernel. `tests/test_spmv.py` exige resultados idênticos bit a bit e contagens
iguais às do simulador, para todas as variantes, VLEN 128 e 256, com linhas mais
longas que VLMAX, estouros, saturação e matriz vazia.

## 3. Execução

```sh
make fetch     # baixa índice e matrizes para .cache/matrices/ e grava results/matrix-list.csv
make bench     # roda e resume; pode ser interrompido e retomado
make bench-synthetic   # versão offline, 64 matrizes sintéticas
```

Arquivos gerados em `results/`:

| Arquivo | Conteúdo |
|---|---|
| `matrix-list.csv` | Matrizes selecionadas, com SHA-256 de cada arquivo baixado |
| `spmv-errors.csv` | Uma linha por matriz e formato: erros, estatísticas de conversão, instruções |
| `spmv-cdf.csv`, `spmv-conversion-cdf.csv` | Distribuições usadas no artigo e nos slides |
| `spmv-summary.json`, `spmv-macros.tex` | Números do texto do artigo e dos slides |
| `benchmark-run.json`, `benchmark-skipped.csv` | Metadados da execução e matrizes que não puderam ser lidas |
| `synthetic-*` | Mesmo conjunto para a rodada sintética offline |

Custo medido: cerca de 1,1 ms de CPU por não nulo para os 10 formatos
(7 + 3 da ablação), paralelizado por matriz; a rodada completa levou 3 minutos
em 16 núcleos.

## 4. Instruções e CSRs

**Laço interno por faixa** (instruções vetoriais): Takum 5, binary16/binary32 7,
FP8 9. A diferença vem de `vtdot.vv`, que substitui a multiplicação alargada, a
troca de `vtype` e a redução; o FP8 ainda precisa de duas conversões, porque o
RVV não tem aritmética FP8. O controle escalar é o mesmo para todos os formatos.

**CSRs.** Os kernels IEEE dependem de `frm` (modo dinâmico) e, para detectar
estouro, precisariam ler `fflags` ou testar o dado. Zvtakum não lê nem escreve
`fcsr`; `vtype` não ganha bits, porque SEW já define o formato. Em 8 bits, o IEEE
precisa ainda distinguir E4M3 de E5M2, um bit de estado a mais. A contrapartida é
que a saturação é silenciosa: os contadores `saturated` de `spmv-errors.csv`
mostram quantas entradas foram limitadas, informação que o hardware só daria com
um indicador próprio.

**Análise estática da ISA.** Além das 5 instruções, o que cada abordagem
precisa (tabela II do artigo; detalhes em `docs/ZVTAKUM.md` §4):

| Necessidade | RVV IEEE, com BF16 e os rascunhos de OFP8 | Zvtakum |
|---|---|---|
| Escolha do formato | SEW e `vtype.altfmt` (rascunho Zvfbfa) | SEW |
| Ampliação | `vfwcvt.f.f.v`, `vfwcvtbf16.f.f.v` | `vwsll.vx` (Zvbb, inteiro) |
| Redução | `vfncvt.f.f.w`, `vfncvt.rod.f.f.w`, `vfncvtbf16[.sat].f.f.w`, `vfncvt[.sat].f.f.q` | `vncvt.t.t` |
| Comparação, mín./máx., ReLU | `vmf*`, `vfmin`, `vfmax` | `vms*`, `vmin`, `vmax` de inteiros |
| Sinal, classificação | `vfsgnj*`, `vfclass` | `vrsub`, `vmseq` |
| Estado de controle | `frm`, `fflags` | nenhum |

BF16 tem conversões e multiplica-acumula ratificados (Zvfbfmin, Zvfbfwma).
Zvfbfa (bit `altfmt` em `vtype`) e Zvfofp8min (só conversões OFP8, com versões
saturante e não saturante) são rascunhos ainda não ratificados.

**Decodificador.** `scripts/isa_analysis.py` (`make isa`) percorre todos os
padrões de bits de cada formato e conta as classes que o decodificador trata
à parte (`results/isa-encodings.csv`):

| Formato | Campo de expoente | Subnormais | ±∞ | NaN | Padrões especiais |
|---|---:|---:|---:|---:|---:|
| E4M3 | 4 | 14 | 0 | 2 | 7,0% |
| E5M2 | 5 | 6 | 2 | 6 | 6,2% |
| binary16 | 5 | 2.046 | 2 | 2.046 | 6,2% |
| bfloat16 | 8 | 254 | 2 | 254 | 0,8% |
| binary32 | 8 | 16.777.214 | 2 | 16.777.214 | 0,8% |
| T*n* (qualquer *n*) | 4 a 11 | 0 | 0 | 1 (NaR) | 2/2^*n* |

Cada formato IEEE tem seu próprio corte de campos e quatro classes especiais
(zero, subnormal, infinito, NaN). Takum tem uma regra para todas as larguras:
o expoente vem de no máximo os 12 primeiros bits, o resto é fração, e só 0 e
NaR são especiais.

## 5. Resultados

Números completos em `results/spmv-summary.json`; artigo e slides os leem de
`results/spmv-macros.tex`. Mediana do log10 do erro relativo da SpMV:

| Formato | Mediana | Erro < 100% | NaN/∞ | Instr. vetoriais/nnz |
|---|---:|---:|---:|---:|
| T8 | −0,7 | 87% | 0% | 1,23 |
| E4M3 | −1,2 | 64% | 34% | 1,80 |
| E5M2 | −1,0 | 73% | 25% | 1,80 |
| T16 | −3,2 | 97% | 0% | 1,47 |
| binary16 | −3,5 | 75% | 25% | 1,84 |
| T32 | −8,2 | 100% | 0% | 2,14 |
| binary32 | −7,6 | 100% | 0% | 2,76 |

- **Faixa dinâmica:** Takum nunca produziu resultado não finito e nenhuma entrada
  saturou. E4M3, E5M2 e binary16 deram NaN/∞ em 34%, 25% e 25% das matrizes.
- **Precisão dentro da faixa:** onde o IEEE não estoura, ele costuma ser mais
  preciso em 8 e 16 bits (T8 perde para E4M3 em 181 de 235 matrizes; T16 perde
  para binary16 em 110 de 270). Em 32 bits, T32 é mais preciso que binary32 em
  199 matrizes e menos em 33.
- **Soma exata do `vtdot`:** quase neutra para o erro com `x` = uns (muda o
  resultado em 103 matrizes T8, melhora em 52).
- **Instruções:** Takum executa 32% menos instruções vetoriais que FP8, 20% menos
  que binary16 e 22% menos que binary32 (16%, 9% e 11% no total).

Discussão completa na seção VI de `output/pdf/final.pdf`.

## 6. Aprendizado de máquina: camada densa

**Kernel.** Camada sem bias `y = ReLU(W x)`: o mesmo kernel CSR sobre a matriz
cheia, com x lido por `vle` contíguo e a ReLU depois do estreitamento
(`vmax.vx` de inteiro no Takum, `vfmax.vf` no IEEE). Ver `docs/ZVTAKUM.md` §7.

**Experimento** (`make mlp`, `takum/mlp.py`, `scripts/run_mlp.py`):

- 64 redes aleatórias 64→64→64→16, ReLU nas duas primeiras camadas, pesos
  N(0, 2/n) (He) e entrada N(0, 1), todos convertidos exatamente para frações;
- entrada multiplicada por 2^k, k = −16, −12, …, 16. Sem bias, a saída exata
  escala por 2^k, então a varredura isola a faixa dinâmica;
- referência binary128; erro relativo da saída da rede. Erro ≥ 100% conta
  como saída perdida.

**Resultados** (`results/mlp-summary.json`, figura 3 do artigo):

| Formato | Mediana log10 em k = 0 | Escalas sem perda (de 9) | Instr. vetoriais/MAC |
|---|---:|---:|---:|
| T8 | −0,9 | 7 | 0,317 |
| E4M3 | −1,2 | 4 | 0,567 |
| E5M2 | −0,9 | 7 | 0,567 |
| T16 | −3,3 | 9 | 0,572 |
| binary16 | −3,2 | 8 | 0,822 |
| T32 | −8,1 | 9 | 1,082 |
| binary32 | −7,2 | 9 | 1,582 |

- **Faixa:** o IEEE tem erro constante enquanto as ativações cabem no formato e
  perde a saída fora disso (subfluxo zera as ativações; estouro vira NaN ou ∞,
  que a ReLU seguinte transforma em 0). E4M3 perdeu a saída em 5 das 9 escalas,
  E5M2 e binary16 em 2^16. T16 e T32 nunca perderam; T8 perdeu em 19% e 47% das
  redes em 2^−16 e 2^16 e degrada aos poucos.
- **Precisão em k = 0:** repete a SpMV: E4M3 é mais preciso que T8, T16 e
  binary16 empatam, T32 é mais preciso que binary32.
- **Soma exata do `vtdot`:** não mudou nenhuma saída T16 ou T32; em T8 foi
  melhor em 80 e pior em 83 de 576 execuções. O estreitamento final para SEW
  domina o erro.
- **Instruções:** o kernel Takum executa 44% menos instruções vetoriais que FP8,
  30% menos que binary16 e 32% menos que binary32 (26%, 16% e 17% no total).
- **Limite:** redes aleatórias, não treinadas; o resultado descreve o erro
  aritmético, não a acurácia de um modelo.
