# data/

Dados das TEDs de Big Data e Ciência de Dados. As pastas ficam no Git, o conteúdo não.

| Pasta | Conteúdo | Gerado por |
|---|---|---|
| `raw/` | `labeled.json` (6.449 processos rotulados) e `unlabeled.json` (2.904.255 movimentações sem rótulo), como publicados na fonte | `notebooks/TED01` ou `src/ted01_baixar_e_inspecionar.py` |
| `processed/` | Base tratada (`processos.jsonl`), movimentações sem rótulo limpas, léxico de nomes usado no mascaramento, lista de auditoria dos pesos e modelo treinado (`modelo_status.joblib`) | `notebooks/TED02` e `notebooks/TED03`, ou os scripts `src/ted02_*.py` e `src/ted03_*.py` |

## Por que não está versionado

- A licença declarada na fonte é "Unknown".
- Os dois arquivos brutos somam 658 MB, acima do limite de 100 MB por arquivo do GitHub.
- Os textos trazem nomes de partes e advogados. O mascaramento da TED 02 é heurístico, e
  `processed/lexico_nomes.txt` é, ele próprio, uma lista de nomes.

As métricas, os gráficos e os metadados da base tratada, sem o texto das movimentações,
ficam versionados em `resultados/`.

## Como obter

Fonte: [Brazilian Legal Proceedings](https://www.kaggle.com/datasets/felipepolo/brazilian-legal-proceedings),
de Felipe Maia Polo, versão 2 (14/05/2021). O download não exige conta no Kaggle.

```bash
python src/ted01_baixar_e_inspecionar.py
```

O script baixa os arquivos para `raw/` e interrompe a execução se o SHA-256 não for o da
versão usada nos documentos:

```
labeled.json    653013a741af31ad389f44458bc0bf5fd4c78a380646556d0772dee47846c63a
unlabeled.json  0451bc19da272cd849a25e510d44ad1735f42a51436514eff114bba7fece3042
```
