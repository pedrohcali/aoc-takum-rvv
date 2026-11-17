# Takum-RVV

Trabalho de Arquitetura e Organização de Computadores, UFMG, 2026/2.

O projeto implementa o formato Takum linear e o avalia como tipo de elemento da
extensão vetorial RISC-V (RVV), em três etapas:

1. **Formato e ALU** (T8, T16, T32 e T64): conversão, extração dos campos
   S/D/R/C/F, soma, subtração e multiplicação, com aritmética exata.
2. **Extensão Zvtakum**: modelo funcional do RVV com as instruções `vtadd.vv`,
   `vtsub.vv`, `vtmul.vv`, `vtdot.vv` e `vncvt.t.t` ([especificação](docs/ZVTAKUM.md)).
3. **Avaliação**: SpMV com 358 matrizes reais do Matrix Market em Takum e em E4M3, E5M2,
   binary16 e binary32, com erro relativo à precisão quádrupla e contagem de
   instruções; camadas densas de rede neural (`ReLU(W x)`) com varredura de
   escala da entrada; e análise estática das instruções e dos decodificadores
   ([método](docs/EVALUATION.md)).

As decisões de projeto, com alternativas e justificativas, estão em
[docs/DECISIONS.md](docs/DECISIONS.md).

## Execução

É necessário Python 3.10 ou superior, sem bibliotecas adicionais.
Na pasta do projeto:

```sh
python3 -m takum encode --width 8 1.5
python3 -m takum decode --width 8 0x44
python3 -m takum add --width 16 1.5 2.25
python3 -m takum mul --width 32 1.5 -2
python3 -m takum demo
```

Por padrão, os operandos são valores numéricos. Para informar os bits diretamente,
use `--raw`. As entradas são convertidas para a largura escolhida antes da operação.
Por exemplo, em T8, `1.5 + 2.25` resulta em `3.5`, pois `2.25` arredonda para `2`.

As instruções vetoriais, o kernel SpMV e a camada densa podem ser vistos com:

```sh
python3 -m takum vector-demo
```

## Avaliação

```sh
make fetch            # baixa as matrizes do NIST Matrix Market (até 50 mil não nulos)
make bench BENCH_DIR=output/repeticao  # repete a medição nessa pasta
make bench-synthetic  # versão offline, com matrizes sintéticas
make mlp              # camadas densas com ReLU, 64 redes em 9 escalas (~4 min)
make isa              # contagem dos padrões especiais de cada formato
```

O benchmark pode ser interrompido e retomado. Os resultados alimentam o artigo
e os slides automaticamente.

## Testes

```sh
make test       # testes locais
make reference  # comparação com libtakum
make verify     # suíte completa, referência C e exemplos escalares
```

A comparação com libtakum requer Git, um compilador C99 e internet na primeira
execução. No Mac ARM, usamos o patch de portabilidade incluído em `scripts/`.
Os resultados com e sem patch estão em `results/`, incluindo a execução sem
patch em Linux. A implementação e os critérios de validação são descritos no artigo.

## Arquivos

- `takum/`: formato, ALU, formatos IEEE de referência, modelo vetorial,
  Zvtakum, SpMV, camada densa (MLP) e interface de terminal.
- `tests/`: testes automáticos, incluindo todos os pares T8 e a equivalência
  entre o simulador e o benchmark.
- `scripts/`: validação, benchmark, exportação dos resultados e geração do ZIP.
- `results/`: resultados dos testes, do benchmark e tabela de valores T8.
- `docs/`: especificação, Zvtakum, avaliação, validação, registro de decisões e
  roteiro da demonstração.
- `paper/`: artigos da primeira etapa e final (LaTeX, IEEEtran).
- `slides/`: apresentação final (Beamer).
- `output/pdf/`: artigos e slides compilados.

Para compilar artigos e slides, instale [Tectonic](https://tectonic-typesetting.github.io/)
e execute `make paper slides`. Para gerar o ZIP da entrega, execute `make package`.
O arquivo é `output/entrega-final.zip`. Ele inclui o artigo
(`output/pdf/final.pdf`), os slides (`output/pdf/final-slides.pdf`), o código,
os testes, a documentação e os dados usados nos gráficos. O [mapa da entrega](docs/DELIVERY-FINAL.md)
indica onde verificar cada requisito. Materiais de consulta e configuração do GitHub
ficam apenas no repositório.

## Referências

- L. Hunhold, [Beating Posits at Their Own Game: Takum Arithmetic](https://arxiv.org/abs/2404.18603), 2024.
- L. Hunhold, [Streamlining SIMD ISA Extensions with Takum Arithmetic](https://arxiv.org/abs/2503.14067), 2025.
- [libtakum 2.0.0](https://github.com/takum-arithmetic/libtakum), revisão `776ac0ca7855f640100731ed8bbb0c7cf83b2d94`.

## Integrantes

- Arthur dos Santos Fernandes
- Bruno Lima Soares
- Lucas Rodrigues Prosperi Ayala
- Pedro Henrique Campos Lima
- Pedro Lopes Ozelin
