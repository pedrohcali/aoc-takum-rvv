# Takum-RVV: AOC/UFMG 2026/2

Modelo funcional da aritmética **Takum linear** T8/T16/T32, preparado para a
primeira entrega do Projeto Integrador de Arquitetura e Organização de Computadores.

**Primeira entrega: 11/10/2026.** Escopo: conversão, extração dos campos e ALU
escalar com soma, subtração e multiplicação. A extensão vetorial Zvtakum,
os benchmarks esparsos e a comparação com FP8/FP16/FP32 pertencem às próximas etapas.

## Executar

Requisito: Python 3.10 ou superior. O simulador e os testes locais não precisam de
bibliotecas externas nem de instalação do pacote. Execute na raiz do repositório:

```sh
python3 -m takum encode --width 8 1.5
python3 -m takum decode --width 8 0x44
python3 -m takum add --width 16 1.5 2.25
python3 -m takum mul --width 32 --raw 0x40000000 0xc0000000
python3 -m takum demo
python3 scripts/run_tests.py
```

Valores decimais e frações (`1.5`, `3/2`) entram sem conversão intermediária para
`float`. `NaR`, `NaN` e infinitos são mapeados para NaR. Operações da CLI recebem
valores numéricos por padrão; `--raw` recebe padrões de bits. Ambos os operandos
são quantizados **antes** da operação.

Exemplo: em T8, `1.5 + 2.25` vira `1.5 + 2.0 = 3.5`, pois 2.25 é um empate de
conversão que arredonda para 2.0. Em T16, o resultado é exatamente 3.75.

## Validação

```sh
make test       # testes offline e relatório JSON
make reference  # comparação com libtakum; precisa de Git, C99 e internet na primeira execução
make artifacts # tabela completa T8 e demonstração JSON
make verify    # os três passos anteriores
```

- Testes de ida e volta para todas as 256 codificações T8 e 65.536 codificações T16.
- Oráculo independente por tabela: todos os 65.536 pares T8 em cada operação
  (196.608 resultados aritméticos).
- T32: amostras determinísticas, fronteiras de regime e casos extremos.
- 548.793 comparações com a referência C fixada em uma revisão específica.
- CI em Python 3.10/3.13 e comparação diferencial em Linux/macOS.

**A referência usa uma correção de portabilidade explícita.** A versão original da
libtakum falha na codificação de 1.5 em T32 no Mac ARM usado na validação. O patch,
a execução original e a execução corrigida estão preservados. Em Linux x86-64 a
biblioteca original, sem patch, concorda em todas as comparações; no Mac ARM a
concordância vale apenas para a cópia corrigida. Consulte
[Validação](docs/VALIDATION.md).

## Organização

| Caminho | Conteúdo |
|---|---|
| `takum/codec.py` | Campos S/D/R/C/F, codificação, decodificação e conversões |
| `takum/alu.py` | Soma, subtração, multiplicação e diagnósticos |
| `takum/cli.py` | Interface de terminal e demonstração |
| `tests/` | Testes de propriedades, casos conhecidos e oráculo independente |
| `scripts/` | Validação diferencial e exportação de resultados |
| `results/` | Evidências reproduzíveis da primeira entrega |
| `docs/SPECIFICATION.md` | Especificação numérica e decisões |
| `docs/DELIVERY-1.md` | Checklist da entrega e pendências da equipe |
| `docs/DEMO.md` | Roteiro comentado da demonstração |
| `paper/phase1.tex` | Artigo parcial em inglês, formato IEEE |
| `output/pdf/phase1.pdf` | Artigo parcial compilado |
| `INPUTS/` | Enunciado, artigos de referência e template IEEE |

Para compilar o artigo, instale [Tectonic](https://tectonic-typesetting.github.io/)
e execute `make paper` (a primeira compilação baixa os pacotes LaTeX).

`make package` gera `output/entrega-1.zip` com os arquivos versionados. Antes de
empacotar arquivos novos, adicione-os ao Git. O pacote inclui código, testes,
documentação, resultados e PDF; não inclui o histórico Git ou o cache da referência.

## Modelo adotado

Os cálculos internos usam `fractions.Fraction`: soma e produto são exatos antes
do único arredondamento de saída. O arredondamento é para o par no fluxo de bits,
com saturação de valores finitos fora da faixa. Em T8, quando o corte alcança C,
isso pode diferir do número real representável mais próximo.

Este é um **modelo funcional escalar**. Não mede ciclos, área, potência ou ganho de
velocidade; os indicadores de saturação/inexatidão são diagnósticos do programa,
não CSRs arquiteturais. Não há suporte a Takum logarítmico nesta versão.

## Referências

1. L. Hunhold, *Beating Posits at Their Own Game: Takum Arithmetic*, 2024.
   [Artigo](https://arxiv.org/abs/2404.18603), definição 8 e algoritmos 4 e 5.
2. L. Hunhold, *Streamlining SIMD ISA Extensions with Takum Arithmetic:
   A Case Study on Intel AVX10.2*, 2025.
   [Artigo](https://arxiv.org/abs/2503.14067).
3. [libtakum 2.0.0](https://github.com/takum-arithmetic/libtakum), revisão
   `776ac0ca7855f640100731ed8bbb0c7cf83b2d94` (licença ISC).

## Equipe

- Arthur dos Santos Fernandes
- Bruno Lima Soares
- Lucas Rodrigues Prosperi Ayala
- Pedro Henrique Campos Lima
- Pedro Lopes Ozelin
