# Registro de decisões de projeto

Decisões que moldaram o projeto, com as alternativas consideradas, o motivo da
escolha e onde ela aparece no repositório. A data é a do commit que registrou a
decisão; o histórico do git mostra o resto do processo. Decisões substituídas
continuam no registro, marcadas como tal. As seções citadas são do artigo final
(`paper/final.tex`).

## Fase 1: formato e ALU escalar

| Data | Decisão | Alternativas | Motivo | Evidência |
|---|---|---|---|---|
| 28/09/2026 | Takum linear | Takum logarítmico | O enunciado descreve o campo de fração F; o estudo do AVX10.2 [Hunhold 2025] usa a variante linear | `takum/codec.py`, seção III |
| 28/09/2026 | Simulador funcional em Python, só com a biblioteca padrão | RTL em VHDL/Verilog; simulador em C++ | O enunciado aceita os três; Python com frações exatas torna cada resultado verificável e reproduzível em qualquer máquina | `takum/` |
| 28/09/2026 | Aritmética com frações exatas e um único arredondamento por operação | Ponto flutuante nativo; `long double` | Evita erro intermediário e dependência de plataforma | `takum/codec.py`, `takum/alu.py` |
| 28/09/2026 | Arredondamento ao mais próximo, empate para par, sobre a sequência de bits | Arredondar o valor real ao mais próximo | É o comportamento da libtakum; o teste `test_characteristic_rounding_is_not_nearest_real` mostra a diferença | `takum/codec.py`, `tests/test_codec.py` |
| 28/09/2026 | Saturação: valores fora da faixa vão ao maior ou menor módulo, nunca a 0 ou NaR | Estouro para NaR; flush para zero | Definição do formato; mantém resultados finitos e ordenados | `takum/codec.py` |
| 28/09/2026 | Oráculo T8 independente do encoder (tabela de limiares de 9 bits) | Testar o encoder contra si mesmo | Um erro no encoder não pode passar despercebido | `tests/test_exhaustive_oracle.py` |
| 12/10/2026 | libtakum fixada (revisão `776ac0c`) com patch de portabilidade, comparada em macOS e Linux | Usar a versão mais recente sem patch | A versão original falha em plataformas com `long double` de 64 bits; fixar a revisão torna a comparação reproduzível | `scripts/libtakum-portable.patch`, `results/reference-upstream-*.json` |

## Fase 2: extensão Zvtakum

| Data | Decisão | Alternativas | Motivo | Evidência |
|---|---|---|---|---|
| 09/11/2026 | Opcode custom-2 com o leiaute OP-V e o `funct6` da instrução IEEE equivalente | Ocupar `funct6` livres do OP-V | O espaço custom é reservado a extensões não padronizadas; não colide com extensões futuras | `takum/zvtakum.py`, seção IV-A |
| 09/11/2026 | SEW seleciona T8/T16/T32 | Bit novo em `vtype` (como o `altfmt` das propostas BF16/OFP8) | Um formato por largura dispensa estado novo | `takum/zvtakum.py`, seção IV-A |
| 09/11/2026 | `vtdot.vv` com soma exata e um arredondamento em 2·SEW | Arredondar cada produto e soma parcial | Proposta de Hunhold (`VDPPT8PT16`); a variante passo a passo fica como ablação para medir o efeito | `takum/zvtakum.py`, `ABLATION` em `takum/spmv.py` |
| 09/11/2026 | Nenhum CSR novo; NaR e saturação no lugar de `frm`/`fflags` | Indicador de saturação | Takum tem um único arredondamento e codifica o inválido no dado; a saturação não ocorreu nas matrizes medidas | Seção IV-B |
| 09/11/2026 | Modelo por instrução, sem tempo | Modelo de ciclos | O enunciado pede contagem de instruções e erro; ciclos exigiriam uma microarquitetura não especificada | `takum/rvv.py`, seção IV-D |
| 09/11/2026 | Ampliação T→2T por extensão com zeros, sem instrução nova | `vwcvt.t.t` | Ampliar um takum é anexar zeros; instruções de inteiro já fazem isso | Seção IV-A, tabela II |

## Fase 3: avaliação

| Data | Decisão | Alternativas | Motivo | Evidência |
|---|---|---|---|---|
| 09/11/2026 | Acumulador 2·SEW em todos os formatos (T8→T16, FP8→FP16, FP16→FP32, ...) | Acumular cada formato na própria largura | Comparação justa: a diferença medida vem do formato, não da largura do acumulador | `takum/spmv.py` |
| 09/11/2026 | FP8 modelado com `vfwcvt` para binary16 | Não avaliar FP8 | O RVV ratificado não tem aritmética FP8; o enunciado pede FP8 | `takum/spmv.py`, seção IV-E |
| 09/11/2026 | OFP8 sem saturação (estouro vira NaN em E4M3 e infinito em E5M2) | Modo saturante | Expõe o estouro em vez de escondê-lo no maior valor; o erro conta como infinito | `takum/ieee.py` |
| 09/11/2026 | bfloat16 fora da avaliação numérica | Incluir bfloat16 | O enunciado pede FP8, FP16 e FP32; bfloat16 aparece só na análise estática | Seção IV-C |
| 09/11/2026 | x = vetor de uns, VLEN = 128, LMUL = 1 | x aleatório; VLEN maior | x de uns é exato em todos os formatos, então o erro vem de A e da aritmética; VLEN 128 é o mínimo do Zvl128b | Seção V |
| 09/11/2026 | Todas as matrizes da SuiteSparse com até 50 mil não nulos (substituída) | | O servidor de arquivos da SuiteSparse respondeu 403 a todos os downloads | Linha seguinte |
| 09/11/2026 | NIST Matrix Market, matrizes reais com até 50 mil não nulos (358 matrizes) | Esperar a SuiteSparse; matrizes sintéticas | Os conjuntos da Matrix Market também fazem parte da SuiteSparse; o desvio é declarado no artigo | `scripts/fetch_matrices.py`, `results/matrix-list.csv` |
| 09/11/2026 | Caminho rápido e contagem analítica para o benchmark, com igualdade ao simulador exigida nos testes | Rodar tudo no simulador | O simulador completo levaria horas; os testes garantem resultados idênticos bit a bit | `tests/test_spmv.py` |
| 09/11/2026 | Erro medido com normas exatas em inteiros | Normas em ponto flutuante | A medida não acrescenta erro próprio | `log10_relative_error` em `takum/spmv.py` |

## Ajustes finais: aprendizado de máquina e análise estática

| Data | Decisão | Alternativas | Motivo | Evidência |
|---|---|---|---|---|
| 09/11/2026 | Kernel de ML: camada densa `ReLU(W x)` sobre o mesmo kernel CSR | Convolução; atenção | É a operação dominante de MLPs e reaproveita o kernel e os testes da SpMV | `takum/mlp.py` |
| 09/11/2026 | ReLU do Takum com `vmax.vx` de inteiros | Instrução `vtmax` nova | Takum é ordenado como inteiro em complemento de dois; NaR (o menor padrão) vira 0, assim como `vfmax` transforma NaN em 0 | `takum/rvv.py`, `tests/test_mlp.py` |
| 09/11/2026 | Redes aleatórias (He), sem bias, com varredura de escala 2^k | Rede treinada em um conjunto de dados | Sem dependências externas; sem bias a rede é homogênea, então a varredura isola o efeito da faixa dinâmica | `scripts/run_mlp.py` |
| 09/11/2026 | Análise estática por contagem exaustiva das classes de valores e tabela de instruções verificada nas especificações | Estimar área de hardware | Não temos síntese de RTL; contar casos especiais e instruções é verificável | `scripts/isa_analysis.py`, seção IV-C, tabelas II e III |
| 17/11/2026 | Repetição completa do benchmark e das redes no Mac ARM, em diretórios vazios | Confiar só na execução Linux | Contagens de instruções e eventos de faixa idênticas; diferença máxima nos erros log10 abaixo de 8 × 10⁻¹⁵ (SpMV) e 3 × 10⁻⁹ (redes); os valores arredondados do artigo coincidem | `make bench`, `make mlp` |
