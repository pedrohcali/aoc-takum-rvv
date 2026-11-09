# Zvtakum: extensão vetorial Takum (fase 2)

## 1. Escopo

Zvtakum é uma extensão experimental, não padronizada, que acrescenta ao RVV 1.0
as cinco instruções do enunciado para Takum linear T8, T16 e T32. O modelo é
funcional, por instrução: executa o efeito arquitetural de cada instrução e a
conta, mas não modela pipeline, latência nem hierarquia de memória.

| Arquivo | Conteúdo |
|---|---|
| `takum/rvv.py` | Estado vetorial (registradores, `vl`, `vtype`), instruções RVV usadas pelos kernels e linha de base IEEE |
| `takum/zvtakum.py` | Codificação e semântica das cinco instruções |
| `takum/spmv.py` | Kernels SpMV CSR, caminho rápido e contagem de instruções |
| `takum/vector_demo.py` | Demonstração (`python3 -m takum vector-demo`) |

## 2. Estado arquitetural

- 32 registradores vetoriais de VLEN bits. Padrão: VLEN = 128 (Zvl128b, o mínimo
  da extensão V); o modelo aceita qualquer potência de dois a partir de 64.
- `vsetvli` define `vl`, SEW ∈ {8, 16, 32, 64} e LMUL ∈ {1, 2, 4, 8}.
  `VLMAX = VLEN · LMUL / SEW`.
- Máscara em `v0`; elementos inativos e de cauda ficam inalterados
  (políticas *mask undisturbed* e *tail undisturbed*).
- Grupos de registradores precisam estar alinhados ao EMUL; o modelo rejeita
  grupos desalinhados.

**SEW seleciona o formato**, exatamente como já seleciona FP16/FP32/FP64 nas
instruções IEEE: SEW=8 → T8, SEW=16 → T16, SEW=32 → T32. Zvtakum não acrescenta
nenhum CSR nem bit de `vtype`.

## 3. Codificação

As instruções reutilizam o leiaute OP-V
(`funct6 | vm | vs2 | vs1 | funct3 | vd | opcode`) sob o opcode principal
**custom-2** (`1011011`), que o RISC-V reserva a extensões não padronizadas.
Assim não colidem com codificações padrão atuais ou futuras. Cada `funct6`
repete o da instrução IEEE equivalente, e `funct3` é OPFVV (`001`).

| Instrução | funct6 | vs1 | Equivalente IEEE | Exemplo (vd=2, vs2=4, vs1=5) |
|---|---|---|---|---|
| `vtadd.vv vd, vs2, vs1` | `000000` | registrador | `vfadd.vv` | `0x0242915b` |
| `vtsub.vv vd, vs2, vs1` | `000010` | registrador | `vfsub.vv` | `0x0a42915b` |
| `vtmul.vv vd, vs2, vs1` | `100100` | registrador | `vfmul.vv` | `0x9242915b` |
| `vtdot.vv vd, vs2, vs1` | `111100` (o de `vfwmacc`) | registrador | `vfwmul.vv` + `vfredosum.vs` | `0xf242915b` |
| `vncvt.t.t vd, vs2` | `010010` | `10100` (fixo) | `vfncvt.f.f.w` | `0x4a4a115b` |

`vncvt.t.t` segue o padrão de VFUNARY0, em que o campo vs1 seleciona a
operação; `10100` é o mesmo seletor de `vfncvt.f.f.w`. Com `vm=0` a instrução
é mascarada por `v0`. `zvtakum.decode` faz a operação inversa e rejeita
palavras que não são Zvtakum.

## 4. Semântica

Todas as instruções operam sobre os elementos `0 ≤ i < vl` ativos.

- **`vtadd.vv`, `vtsub.vv`, `vtmul.vv`:** `vd[i] = round(vs2[i] op vs1[i])` no
  formato de SEW, pela `TakumALU` da fase 1: resultado exato e um único
  arredondamento (para o par no fluxo de bits, com saturação).
- **`vtdot.vv`:** `vd[0] = round₂(vd[0] + Σ vs2[i] · vs1[i])`. As fontes têm
  SEW bits; o acumulador `vd[0]` tem 2·SEW bits (T8→T16, T16→T32, T32→T64).
  A soma dos produtos é exata e há **um único arredondamento** para 2·SEW, como
  as instruções `VDPPT8PT16`/`VDPPT16PT32`/`VDPPT32PT64` propostas por Hunhold
  (2025) para o AVX10.2. Com `vl = 0` nada é escrito. O modo de ablação
  (`vtdot_fused=False`) arredonda cada produto e cada soma parcial para 2·SEW,
  como faz `vfwmacc` no IEEE; ele existe só para medir o efeito da fusão.
- **`vncvt.t.t`:** `vd[i] (SEW) = round(vs2[i] (2·SEW))`, com a mesma política de
  arredondamento e saturação de `TakumFormat.convert`. A conversão de alargamento
  não precisa de instrução própria, porque é exata e equivale a acrescentar
  zeros à direita: `vwsll.vx vd, vs2, t0` (Zvbb) com `t0 = SEW` faz T8→T16,
  T16→T32 e T32→T64.

**O que não precisa de instrução nova.** Takum é ordenado como inteiro em
complemento de dois, e a negação é a negação inteira. Por isso as instruções
de inteiro do RVV já cobrem:

| Operação | IEEE (precisa de versão de ponto flutuante) | Takum (instrução de inteiro existente) |
|---|---|---|
| Comparação | `vmfeq`, `vmfne`, `vmflt`, `vmfle`, `vmfgt`, `vmfge` | `vmseq`, `vmsne`, `vmslt`, `vmsle`, `vmsgt` |
| Mínimo, máximo, ReLU | `vfmin`, `vfmax` | `vmin`, `vmax` (ReLU = `vmax.vx vd, vs, zero`) |
| Negação, valor absoluto | `vfsgnjn`, `vfsgnjx` | `vrsub.vx vd, vs, zero`; `vmax` de x e −x |
| Classificação | `vfclass` | `vmseq` com 0 e com NaR (só dois valores especiais) |

NaR é o menor padrão, então `vmax.vx` com zero leva NaR a 0, assim como
`vfmax` leva NaN a 0 no IEEE (`maximumNumber`). Nos dois casos, uma ReLU pode
esconder um valor inválido.

**Valores especiais.** Qualquer operando NaR produz NaR, inclusive em `vtdot`.
Não existem infinitos, zero negativo nem subnormais. Valores finitos fora da
faixa saturam no maior ou menor valor representável; nunca viram NaR nem zero.

## 5. CSRs

A extensão F usa `fcsr` = `frm` (3 bits, cinco modos de arredondamento) +
`fflags` (NV, DZ, OF, UF, NX). Zvtakum não lê nem escreve `fcsr`:

| Elemento do IEEE | Em Zvtakum |
|---|---|
| `frm` (RNE, RTZ, RDN, RUP, RMM) e modo dinâmico | Um único arredondamento; não há o que selecionar |
| NV (operação inválida) | NaR, que se propaga no próprio dado |
| DZ (divisão por zero) | Não há divisão no subconjunto; seria NaR |
| OF / UF (estouro) | Saturação; o resultado continua finito e ordenado |
| NX (inexato) | Não sinalizado; o modelo expõe `inexact` só como diagnóstico |
| Subnormais, ±0, ±∞, NaNs com carga | Não existem |

A análise com números está em [EVALUATION.md](EVALUATION.md).

## 6. Linha de base IEEE no mesmo modelo

Para comparar com o mesmo modelo de contagem, `takum/rvv.py` implementa
`vfwcvt.f.f.v`, `vfmul.vv`, `vfwmul.vv`, `vfredosum.vs` (soma ordenada,
determinística) e `vfncvt.f.f.w` para FP16, FP32 e FP64, com arredondamento para
o par mais próximo. **O RVV ratificado não tem FP8.** Para E4M3 e E5M2
modelamos as conversões FP8↔FP16 no papel que `vtype.altfmt` cumpre nas
propostas de FP8; a aritmética acontece em FP16, que contém todos os valores
FP8. E4M3 segue a especificação OCP OFP8 (sem infinitos, máximo 448), no modo
sem saturação: estouro vira NaN.

## 7. Kernel SpMV (CSR, linha a linha)

Mesmo esqueleto para todos os formatos; muda só o corpo do laço interno.
Os deslocamentos de coluna são guardados em bytes (pré-processamento único).

```text
para cada linha i:                         escalar: lw, lw, sub, addi, beqz
    vsetivli t0, 1, e(2·SEW)               vetor
    vmv.s.x  v2, zero                      acumulador em 2·SEW
    enquanto restam elementos:
        vsetvli  t0, a5, e(SEW), m1
        vle(SEW).v    v4, (a1)             valores de A
        vle32.v       v12, (a2)            deslocamentos das colunas
        vluxei32.v    v5, (a4), v12        x[col]
        Takum:   vtdot.vv v2, v4, v5
        FP16/32: vfwmul.vv v6, v4, v5 ; vsetvli zero, zero, e(2·SEW), m2 ; vfredosum.vs v2, v6, v2
        FP8:     vfwcvt.f.f.v v6, v4 ; vfwcvt.f.f.v v8, v5 ; vsetvli zero, zero, e16, m2
                 vfmul.vv v10, v6, v8 ; vfredosum.vs v2, v10, v2
        escalar: sub, slli, add, slli, add, bnez
    vsetivli t0, 1, e(2·SEW) ; vse(2·SEW).v v2, (a3)
    escalar: addi, bne
em faixas de VLMAX sobre y: vsetvli ; vle(2·SEW) ; vncvt.t.t | vfncvt.f.f.w ; vse(SEW)
```

Instruções vetoriais por faixa do laço interno: **Takum 5, FP16/FP32 7, FP8 9.**

**Camada densa `y = ReLU(W x)`** (`spmv_simulated(..., dense=True, relu=True)`):
o mesmo laço, mas x é lido com `vle(SEW).v v5, (a2)` contíguo, sem `vle32` e
sem `vluxei32` (Takum 4, FP16/FP32 6, FP8 8 por faixa). Na passada final, depois
do estreitamento, vem a ReLU: `vmax.vx v4, v4, zero` no Takum e
`vfmax.vf v4, v4, f0` no IEEE. O controle escalar por linha é `mv, mv, addi, bne`
e por faixa `sub, slli, add, add, bnez`.
`spmv.count_instructions` aplica esse modelo a qualquer matriz; os testes exigem
que ele coincida com a contagem do simulador e que o caminho rápido produza o
mesmo resultado, bit a bit, que a execução instrução por instrução.
