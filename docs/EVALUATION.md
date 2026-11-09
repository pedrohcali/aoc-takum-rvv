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
