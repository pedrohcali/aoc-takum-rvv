# Validação aritmética

## Estratégia

Três caminhos de verificação se complementam:

1. **Casos conhecidos e propriedades:** padrões extraídos diretamente da definição,
   todos os padrões T8/T16 em ida e volta, fronteiras e amostras T32, sinal,
   saturação, NaR, precisão da entrada decimal e interface CLI.
2. **Oráculo T8 independente:** interpreta os campos como strings, pré-calcula
   os limiares de arredondamento com codificações de 9 bits e usa busca binária
   nessa tabela. Para os 65.536 pares de operandos, calcula soma, subtração e
   produto exatos. O encoder de produção constrói os campos a partir do expoente;
   ele não usa essa tabela. Os valores esperados não chamam o codec de produção.
3. **Comparação com implementação externa C:** usa a libtakum 2.0.0, revisão
   `776ac0ca7855f640100731ed8bbb0c7cf83b2d94`, com a correção de portabilidade
   especificada abaixo. Semente pseudoaleatória: 20260928.

A implementação do projeto não importa ou chama a libtakum. A biblioteca é
compilada apenas para a validação opcional em `scripts/validate_reference.py`.

## Resultados locais registrados

- A suíte atual inclui a ALU escalar, as instruções vetoriais, SpMV e as camadas
  densas. O total e o resultado da última execução estão em `results/unit-tests.json`.
- Ida e volta exaustiva de 65.792 padrões T8/T16.
- 196.608 operações T8 contra o oráculo racional independente.
- 548.793 comparações diferenciais: nenhuma divergência com a referência corrigida.

Os relatórios JSON registram data UTC, plataforma, versão do Python, revisão,
semente, contagens por grupo, hash do patch e duração real. São evidências da
execução local, não resultados de desempenho de hardware.

### Cobertura da comparação diferencial

| Tipo | T8 | T16 | T32 |
|---|---:|---:|---:|
| Decodificação | 256 | 65.536 | 20.101 |
| Codificação | 20.261 | 85.541 | 40.106 |
| Soma | 65.536 | 20.064 | 20.064 |
| Subtração | 65.536 | 20.064 | 20.064 |
| Multiplicação | 65.536 | 20.064 | 20.064 |

As codificações incluem valores obtidos da decodificação, 20.000 valores
binários aleatórios por largura e cinco entradas especiais. T32 inclui padrões
nas fronteiras de D/R. Para T16/T32, cada operação combina 20.000 pares aleatórios
e 64 pares de valores especiais/fronteiras. Entradas duplicadas são contadas
como comparações, não como valores distintos.

## Falha reproduzida na biblioteca original

No Mac ARM utilizado, `long double` tem precisão de `double`. A função upstream
`extended_float_fraction_to_rounded_bits` incrementa `q` após já normalizar a
mantissa inteira para o bit mais significativo. Isso desloca incorretamente a
fração; por exemplo, `takum32_from_float64(1.5)` retorna `0x40000000` (1),
enquanto a definição dá `0x44000000` (1.5).

A rotina também depende da disposição de bytes de `long double`. Para evitar
pressupor sua representação, `scripts/libtakum-portable.patch` substitui apenas
a extração dessa fração por `ldexpl`, `floorl` e desempate para par. Em T32 são
necessários no máximo 27 bits de fração. Não mudamos a definição de campos,
as funções de adição/subtração/multiplicação nem a política de arredondamento
da referência. O diretório original é mantido limpo; o patch é aplicado a uma cópia.

- `results/reference-upstream-macos.json`: execução sem patch, com 156.294
  divergências em 548.793 comparações na plataforma registrada.
- `results/reference-upstream-linux.json`: execução sem patch em Linux x86-64
  (`long double` x87 de 80 bits), com zero divergências nas mesmas 548.793 comparações.
- `results/reference-validation.json`: execução com patch, com zero divergências.
- `scripts/libtakum-portable.patch`: alteração completa, revisável.
- `scripts/libtakum-LICENSE`: licença ISC do código de referência presente no patch.

Para repetir a execução original (o processo retorna status 1 caso haja divergência):

```sh
python3 scripts/validate_reference.py --reference-mode upstream \
  --output results/reference-upstream-local.json
```

Para repetir a referência corrigida:

```sh
python3 scripts/validate_reference.py
```

O resultado sem patch varia por compilador/arquitetura: o upstream original
diverge no Mac ARM e concorda em todas as comparações no Linux x86-64 registrado.
No Mac ARM, a concordância reportada é com a referência **corrigida**; não se
afirma que o upstream original passa nos testes em qualquer plataforma. O patch
é local a este projeto e não foi enviado aos mantenedores da biblioteca.

## Limites da evidência

- Exaustão de operações em T16/T32 é impraticável neste escopo; a cobertura é amostral.
- A referência C usa intermediários de ponto flutuante. A implementação racional
  tem semântica de resultado exato seguido de um arredondamento; casos adversariais
  não amostrados podem expor diferenças de arredondamento intermediário na referência.
- Zero divergências nas amostras não prova equivalência para todos os operandos T32.
- O oráculo T8 é independente do algoritmo de implementação, mas compartilha
  explicitamente a mesma definição e a decisão de desempate para par.
- Os erros de SpMV e a comparação com IEEE estão em [EVALUATION.md](EVALUATION.md).
  O simulador conta instruções. Ciclos, área e potência exigem um modelo de hardware.
