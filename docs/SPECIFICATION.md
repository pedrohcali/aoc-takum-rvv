# Especificação da primeira entrega

## 1. Escopo e referência normativa

Implementação própria, em Python, da **variante linear** da definição 8 de
Hunhold (2024), com tamanhos T8, T16 e T32. A escolha é coerente com o estudo de
SIMD de Hunhold (2025), cuja figura 2 identifica explicitamente o Takum linear.
O enunciado cita ambos os trabalhos e não fixa a variante; a escolha está
registrada para discussão com o professor.

O artigo de 2024 assume a variante logarítmica quando nenhuma é declarada.
Por isso toda a documentação deste projeto identifica a variante linear.
A libtakum 2.0.0 chama a linear de `takumN` e a logarítmica de `takum_logN`.

## 2. Campos e valor

```text
MSB                                      LSB
 S | D | R2 R1 R0 | C (r bits) | F (p bits)
 1   1      3           r            p
```

- `S`: sinal.
- `D`: direção da característica.
- `R`: inteiro de 3 bits, entre 0 e 7.
- `r = R` se D=1; `r = 7-R` se D=0.
- `C`: inteiro sem sinal de r bits.
- `c = 2^r - 1 + C` se D=1.
- `c = 1 - 2^(r+1) + C` se D=0.
- `p = n - 5 - r`, quando todos os bits C estão presentes.
- `f = F / 2^p`.
- `e = (1 - 2S)(c + S)`.
- Valor finito não nulo: `((1 - 3S) + f) * 2^e`.

A definição 8 é enunciada para n ≥ 12. Como Takums são invariantes à extensão
com zeros, cadeias menores são estendidas com zeros para decodificação
(Hunhold, 2025, figura 1). Quando T8 não contém todos os bits de C, completamos
C com zeros à direita (*ghost bits*). Nesse caso não existem bits F físicos.
O objeto `Fields` informa o número de zeros acrescentados e os campos
interpretados após essa extensão. Zeros extras na fração seriam equivalentes,
mas não são materializados, para deixar visível a precisão armazenada.

### Casos especiais

- Bits todos zero: zero único, sem sinal negativo.
- Apenas o bit de sinal ativo: NaR (*Not a Real*).
- NaR é representado por `None` na API de valores exatos.
- `NaN`, infinitos e `NaR` na entrada numérica convertem para NaR.
- Qualquer operação com NaR resulta em NaR, inclusive `NaR * 0`.
- Padrões de bits inválidos e tamanhos não suportados geram `ValueError`.

### Exemplos T8

| Hex | Bits | Valor exato |
|---|---|---|
| 00 | 00000000 | 0 |
| 01 | 00000001 | 2^-239 |
| 40 | 01000000 | 1 |
| 44 | 01000100 | 3/2 |
| 48 | 01001000 | 2 |
| 7f | 01111111 | 2^239 |
| 80 | 10000000 | NaR |
| c0 | 11000000 | -1 |
| ff | 11111111 | -2^-239 |

A negação usa complemento de dois, módulo 2^n. Zero e NaR são invariantes.

## 3. Codificação e arredondamento

1. Classificar zero e valores não finitos.
2. Obter sinal e magnitude como fração exata.
3. Saturar magnitudes menores/maiores que os extremos representáveis.
4. Calcular `c = floor(log2(magnitude))` com comprimentos de inteiros e comparação
   exata; nenhuma função de logaritmo de ponto flutuante é necessária.
5. Calcular `f = magnitude / 2^c - 1` e os campos D/R/C.
6. Construir o prefixo e arredondar a cauda para o inteiro par mais próximo.
   O fator `2^(n-5-r)` pode ter expoente negativo em T8, portanto o corte pode
   remover bits de C. Resto exato preserva os bits descartados relevantes.
7. Impedir que o arredondamento de um valor finito não nulo produza zero ou NaR.
8. Aplicar complemento de dois se o sinal original era negativo.

**Decisão de desempate:** adotamos nearest/even da libtakum 2.0.0. O pseudocódigo
do algoritmo 1 do artigo de 2024 apenas incrementa quando o primeiro bit
removido é 1; não explicita esse desempate. A decisão não é atribuída ao artigo.

O arredondamento no fluxo de bits não equivale sempre à menor distância real.
Por exemplo, T8 representa 2^15 (`0x60`) e 2^17 (`0x61`); o ponto de decisão do
fluxo fica em 2^16, enquanto a média aritmética dos extremos é 81920.

Os diagnósticos `saturated_low` e `saturated_high` indicam que a magnitude exata
estava fora dos extremos representáveis. Não significam exceções IEEE nem
constituem proposta de CSRs. `inexact` compara o resultado decodificado com o
valor exato; `invalid` indica NaR.

## 4. ALU

Fluxo: **bits de entrada → decodificação exata → operação racional →
arredondamento/codificação → bits de saída**.

`TakumALU(width).execute(operation, a, b)` aceita `add`, `sub` e `mul` e dois
inteiros sem sinal contendo os bits. Retorna o resultado exato anterior ao
arredondamento, os bits finais e os diagnósticos. `add`, `sub` e `mul` também
estão disponíveis como métodos que retornam apenas os bits.

Não há fusão de operações: uma sequência soma/produto arredonda após cada
instrução escalar. Produto escalar com acúmulo ampliado será especificado na fase 2.

Conversões para uma largura maior preservam valores e correspondem à extensão
com zeros à direita; conversões para larguras menores seguem a mesma política
de arredondamento/saturação.

## 5. Escolhas de engenharia

| Escolha | Motivo | Custo/limite |
|---|---|---|
| Python e biblioteca padrão | Reprodução simples e inspeção didática | Sem estimativa de desempenho de hardware |
| Frações exatas | Evitar arredondamento intermediário e dependência de `long double` | Mais lento que ponto flutuante nativo |
| Encoder construído por campos | Evidenciar a lógica exigida no enunciado | Mais código que usar uma biblioteca pronta |
| Oráculo T8 por busca em tabela | Algoritmo independente do encoder | Exaustão limitada a T8 |
| Referência externa fixada | Reproduzir a comparação | Exige compilador e correção de portabilidade documentada |

## 6. Próxima etapa

Integrar a ALU a um modelo de registradores vetoriais e especificar `vtadd.vv`,
`vtsub.vv`, `vtmul.vv`, `vtdot.vv` e `vncvt.t.t`. Definir VLEN, VL, SEW,
mascaramento, política de cauda e largura do acumulador antes de medir instruções.
A proposta Zvtakum será tratada como extensão experimental do trabalho.
