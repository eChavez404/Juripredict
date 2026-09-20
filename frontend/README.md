# frontend/

Camada 4: React + Vite. Consulta, drill-down até as decisões e comparação entre
unidades julgadoras.

**Ainda não iniciada.** Depende da camada 3, que depende da 1. Ver
`backend/README.md` para a pré-condição.

## O que a interface precisa respeitar

- **Nenhum número sozinho.** Toda taxa exibida vem com `n`, intervalo de
  confiança e cobertura da fonte naquele recorte.
- **Todo número rastreável.** Sempre é possível abrir a lista de decisões que
  originaram a estimativa.
- **Abstenção visível.** Abaixo do piso de amostra ou de cobertura, a tela diz o
  motivo — não exibe um número frágil, nem um espaço vazio.

Estado de abstenção e estado de carregamento são telas diferentes: "não há dado
suficiente para esta vara neste ano" não pode parecer erro.

```
frontend/
├── Dockerfile
└── src/
```
