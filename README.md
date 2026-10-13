# Takum-RVV

Trabalho de Arquitetura e Organização de Computadores, UFMG, 2026/2.

Esta primeira etapa implementa o formato Takum linear em 8, 16 e 32 bits:
conversão, extração dos campos S/D/R/C/F, soma, subtração e multiplicação.
A integração com instruções vetoriais será feita na próxima etapa.

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

## Testes

```sh
make test       # testes locais
make reference  # comparação com libtakum
make verify    # testes e geração dos resultados
```

A comparação com libtakum requer Git, um compilador C99 e internet na primeira
execução. No Mac ARM, usamos o patch de portabilidade incluído em `scripts/`.
Os resultados com e sem patch estão em `results/`, incluindo a execução sem
patch em Linux. A implementação e os critérios de validação são descritos no artigo.

## Arquivos

- `takum/`: implementação e interface de terminal.
- `tests/`: testes automáticos, incluindo todos os pares T8.
- `scripts/`: validação, exportação dos resultados e geração do ZIP.
- `results/`: resultados dos testes e tabela de valores T8.
- `paper/`: fonte LaTeX e classe IEEEtran.
- `output/pdf/phase1.pdf`: artigo da primeira etapa.

Para compilar o artigo, instale [Tectonic](https://tectonic-typesetting.github.io/)
e execute `make paper`. Para gerar o ZIP da entrega, execute `make package`.
O pacote contém os arquivos acima. Materiais de consulta e configuração do GitHub
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
