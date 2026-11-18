# Takum na extensão vetorial RISC-V

Arquitetura e Organização de Computadores, UFMG, 2026/2.

Implementamos cinco instruções vetoriais para Takum em Python. Usamos o simulador
para comparar Takum e ponto flutuante em dois cálculos: o produto de uma matriz
esparsa por um vetor e uma rede de três camadas densas. Nas 358 matrizes testadas,
T8 sempre produziu um resultado finito. Nas 235 em que E4M3 também ficou dentro
da faixa, E4M3 teve erro menor em 181.

[Artigo (PDF)](output/pdf/final.pdf) · [Slides (PDF)](output/pdf/final-slides.pdf)

## Rodar a demonstração

Na pasta do projeto, com Python 3.10 ou mais recente:

```sh
python3 -m takum vector-demo
```

O programa mostra as cinco instruções, depois uma matriz 4 × 4 e uma camada
densa com ReLU. Na camada densa, T8 e E4M3 chegam ao mesmo vetor
`[6, 0, 7, 0]`. T8 executa 37 instruções vetoriais e E4M3 executa 53. Para
experimentar a aritmética escalar, use `python3 -m takum add --width 8 1.5 2.25`.
O resultado é 3,5 porque, em T8, o segundo operando já entra na soma como 2.

## Testes e experimentos

`make test` roda a suíte local. Para repetir também as 548.793 comparações com
a libtakum, execute `make verify`. Essa etapa precisa de Git, compilador C99 e
acesso à internet na primeira execução.

```sh
make fetch
make bench BENCH_DIR=output/repeticao
make mlp
```

O primeiro comando baixa as matrizes listadas em `results/matrix-list.csv` e
confere seus hashes. O segundo grava a nova medição na pasta indicada. O
terceiro repete o experimento das redes nas nove escalas de entrada.

Os critérios de arredondamento, a semântica das instruções e o método de
avaliação estão na [especificação do formato](docs/SPECIFICATION.md), na
[descrição de Zvtakum](docs/ZVTAKUM.md) e nas [notas dos experimentos](docs/EVALUATION.md).
O [registro de decisões](docs/DECISIONS.md) explica as escolhas de projeto.

Os PDFs já estão em `output/pdf/`. Com Tectonic instalado, `make package`
recompila o artigo e os slides e gera `output/entrega-aoc.zip`.

## Integrantes

- Arthur dos Santos Fernandes
- Bruno Lima Soares
- Lucas Rodrigues Prosperi Ayala
- Pedro Henrique Campos Lima
- Pedro Lopes Ozelin
