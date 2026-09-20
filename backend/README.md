# backend/

Camada 3: Django + Django REST Framework expondo agregações sobre a tabela que a
camada 1 produz.

**Ainda não iniciada, e isso é decisão, não atraso.** A API da primeira versão é
consulta agregada sobre `casos` — escrevê-la antes de o dataset existir significa
fixar endpoints contra um schema que ainda vai mudar, e medir cobertura contra
uma base vazia.

## Pré-condição para começar

Camada 1 tendo produzido dado **verificado**, não só código que roda:

- corpus real coletado e processado (`processar.py` sobre `dataset/data/normalized`);
- gold set anotado e concordância medida por classe (`gold_set.py comparar`);
- `montar_dataset.py` fechando sem quebrar o invariante de uma linha por
  `(numero_cnj, pedido)`;
- cobertura da fonte medida por vara e ano (`auditoria_cobertura.py`).

## O que a API precisa carregar

Nenhuma taxa é devolvida sozinha. Toda resposta de agregação traz `n`, intervalo
de confiança e cobertura da fonte naquele recorte, e abaixo do piso de amostra
devolve o motivo da abstenção em vez do número (invariante I3).

```
backend/
├── Dockerfile
└── juripredict/        projeto Django
```
