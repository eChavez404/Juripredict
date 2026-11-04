# docs/

Documentação de entrega das disciplinas. Os arquivos `.docx` ficam aqui, mas
**não são versionados** — `*.docx` está no `.gitignore`, porque são binários que
mudam a cada salvamento.

| Documento | Disciplina |
|---|---|
| `TED01_BIGDATA_JuriPredict.docx` | Big Data e Ciência de Dados — prospecção, diagnóstico e seleção de dados |
| `TED01_IA_JuriPredict.docx` | Inteligência Artificial — problema, solução e MVP |

Para versionar um deles apesar da regra:

```bash
git add -f docs/TED01_BIGDATA_JuriPredict.docx
```

## Big Data e Ciência de Dados: TEDs 01 a 03

`JuriPredict_Documento_Tecnico_BigData.pdf` reúne as três etapas e **é versionado**
(exceção no `.gitignore`).

| Etapa | Seções |
|---|---|
| TED 01: seleção da base, problema e necessidades de dados | 1 a 5 |
| TED 02: limpeza, preparação e análise exploratória | 6 e 7 |
| TED 03: modelagem, discussão e decisões | 8 a 10 |
| Repositório, dados e reprodução | 11 |

## Os números do documento saem do pipeline

A tabela da seção 6.2 e a divisão da 6.4 são produzidas por:

```bash
cd dataset/pipeline
python montar_dataset.py     # composição, taxa-base, partições
python exportar_dataset.py   # versão publicável e cartão
```

Eles mudam quando uma regra de rotulagem muda. Antes de fechar uma versão do
documento, rode os dois e confira contra o que está escrito.
