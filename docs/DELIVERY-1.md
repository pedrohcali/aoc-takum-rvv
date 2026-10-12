# Primeira entrega: 11/10/2026

## Correspondência com o enunciado

A marca da semana 4 engloba revisão bibliográfica/especificação (semanas 1 e 2)
e implementação da ALU T8/T16/T32 (semanas 3 e 4).

| Requisito | Evidência |
|---|---|
| Revisão bibliográfica | Referências no README e artigo parcial |
| Especificação do decodificador | `docs/SPECIFICATION.md` |
| Extração S/D/R/C/F | `TakumFormat.fields` e tabela `results/t8-values.csv` |
| Conversão T8/T16/T32 | `encode`, `decode`, `convert` |
| Soma/subtração/multiplicação | `TakumALU` |
| Testes automáticos | `tests/`, `scripts/run_tests.py` e CI |
| Versionamento e organização | Repositório Git; entrega em ZIP gerado por `make package` |
| Documentação contínua | Especificação, validação, decisões e artigo parcial |
| Demonstração funcional | `python3 -m takum demo` e `docs/DEMO.md` |

## Equipe confirmada

- Arthur dos Santos Fernandes
- Bruno Lima Soares
- Lucas Rodrigues Prosperi Ayala
- Pedro Henrique Campos Lima
- Pedro Lopes Ozelin

Os cinco integrantes estão identificados no artigo e no README.

## Escopo posterior (não incluído na conclusão da fase 1)

- Semanas 5 e 6: integração RVV e cinco instruções propostas.
- Semana 7: SpMV, comparação FP8/FP16/FP32, referência Float128 validada,
  distribuição de erro e contagem de instruções/CSRs.
- Semana 8: artigo final de até seis páginas, slides finais e apresentação de 15 minutos.

O artigo entregue agora é parcial e relata validação aritmética. Seus resultados
não são os benchmarks comparativos exigidos para a entrega final.
