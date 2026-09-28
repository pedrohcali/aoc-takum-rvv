# Roteiro da demonstração da fase 1

Tempo sugerido: 5 a 7 minutos. Executar na raiz do repositório.

## 1. Campos e representação (1 minuto)

```sh
python3 -m takum encode --width 8 1.5
python3 -m takum decode --width 8 0x01
```

Explicar `0x44 = 01000100`: S=0, D=1, R=0, C vazio e F=100.
Portanto f=1/2, e=0 e o valor é 3/2. Em `0x01`, quatro zeros implícitos
completam C; o valor é 2^-239.

## 2. ALU e quantização dos operandos (2 minutos)

```sh
python3 -m takum add --width 8 1.5 2.25
python3 -m takum add --width 16 1.5 2.25
python3 -m takum mul --width 32 1.5 -2
python3 -m takum sub --width 8 1 1
```

Resultados: 3.5, 3.75, -3 e 0. Em T8, 2.25 arredonda previamente para 2;
não é um erro da adição. Os operandos efetivos aparecem na saída.
A aritmética racional calcula o resultado exato desses operandos, e depois
arredonda uma única vez para a largura de saída.

## 3. Limites e NaR (1 minuto)

```sh
python3 -m takum mul --width 8 --raw 0x7f 0x7f
python3 -m takum mul --width 8 --raw 0x01 0x01
python3 -m takum add --width 8 NaR 1
```

O primeiro produto satura no máximo; o segundo, no mínimo positivo.
Nenhum deles vira infinito ou zero. O último propaga NaR.

## 4. Evidências e limitações (1 a 3 minutos)

```sh
python3 scripts/run_tests.py
python3 scripts/validate_reference.py
```

Mostrar a contagem de comparações e a ausência de divergências na referência
com patch de portabilidade. Explicar que o patch é do validador externo, e que
os 196.608 casos T8 também passam por um oráculo exato independente.
A execução original que falhou permanece registrada em `results/`.

Finalizar: a fase 1 implementa a semântica escalar. Ainda serão adicionados os
registradores/instruções vetoriais e os experimentos de álgebra linear.

## Perguntas para ensaiar

1. Como D/R determinam o tamanho de C?
2. Por que T8 precisa de ghost bits em alguns regimes?
3. Qual a diferença entre a variante linear e a logarítmica?
4. Em que ponto ocorre o arredondamento? Como um empate é decidido?
5. Por que um produto muito pequeno não vira zero?
6. Por que os tempos do Python não medem velocidade da ALU em hardware?
7. Como os testes evitam usar o próprio encoder como única referência?
8. Qual problema apareceu na libtakum e como a comparação foi tornada reproduzível?
