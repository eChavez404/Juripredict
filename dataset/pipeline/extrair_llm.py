"""
Camada 3: extrai as variaveis que so existem em prosa, a partir do CAPITULO
recortado da fundamentacao — nunca da sentenca inteira.

    python extrair_llm.py --dry-run          # ve o prompt e estima tokens, sem gastar
    python extrair_llm.py --limite 500       # extrai de verdade

A chave vem do arquivo .env na raiz do projeto:

    GEMINI_API_KEY = sua-chave-aqui

Grava em `valores`, uma linha por campo, com evidencia, metodo e versao — e e
de la que o montar_dataset.py monta o CSV.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

VERSAO_PROMPT = "extracao-v1"
# Flash-Lite tem cota diaria muito maior que o Flash no free tier, e a tarefa
# aqui e extracao estruturada — nao precisa do modelo mais capaz.
MODELO_PADRAO = "gemini-2.0-flash-lite"
LOTE_PADRAO = 20          # capitulos por chamada
PAUSA = 4.0               # segundos entre chamadas (respeita o RPM)
TENTATIVAS = 3

SCHEMA_INSALUBRIDADE = {
    "laudo_existe": "true | false - houve pericia nos autos",
    "laudo_conclusao": "insalubre | nao_insalubre | inconclusivo | null",
    "laudo_grau": "10 | 20 | 40 | null",
    "agente": "biologico | quimico | fisico | outro | null",
    "epi_discutido": "true | false",
    "epi_considerado_eficaz": "sim | nao | nao_discutido",
    "juiz_divergiu_do_perito": "true | false",
}

SCHEMA_HORAS_EXTRAS = {
    "cartoes_juntados": "sim | nao | parcialmente",
    "cartoes_invalidados": "true | false - marcacao britanica ou invariavel",
    "acordo_de_compensacao": "valido | invalido | inexistente",
    "banco_de_horas": "true | false",
    "prova_testemunhal": "favoravel_reclamante | favoravel_reclamada | inexistente",
}

SCHEMAS = {
    "insalubridade": SCHEMA_INSALUBRIDADE,
    "periculosidade": SCHEMA_INSALUBRIDADE,
    "horas_extras": SCHEMA_HORAS_EXTRAS,
}

INSTRUCAO = """Voce recebe {n} capitulos de fundamentacao de sentencas trabalhistas,
cada um identificado por um id.

Extraia APENAS o que esta escrito em cada um. Nao infira, nao complete, nao
suponha. Se a informacao nao aparece no texto, use null.

Atencao: anote a conclusao do PERITO, nao a do juiz. Se o perito concluiu pela
insalubridade e o juiz indeferiu por outra razao, laudo_conclusao continua
sendo "insalubre".

Responda SOMENTE com um ARRAY JSON, um objeto por capitulo, na mesma ordem,
cada objeto com a chave "id" mais exatamente estas chaves:

{schema}

Capitulos:
{capitulos}"""

BLOCO = """
=== id: {id} ===
{texto}
"""


def carregar_env(inicio=None):
    """Le o .env da raiz do projeto. Sem dependencia externa."""
    atual = (inicio or Path(__file__).resolve()).parent
    for pasta in [atual, *atual.parents]:
        env = pasta / ".env"
        if not env.exists():
            continue
        for linha in env.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and valor and chave not in os.environ:
                os.environ[chave] = valor
        return


def obter_chave():
    carregar_env()
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        sys.exit(
            "GEMINI_API_KEY vazia.\n\n"
            "Crie um .env na raiz do projeto com:\n"
            "    GEMINI_API_KEY = sua-chave\n\n"
            "A chave sai de https://aistudio.google.com/apikey\n"
            "Nunca versione o .env."
        )
    return chave


def montar_prompt(lote, tema):
    """`lote` e uma lista de (caso_id, texto)."""
    schema = json.dumps(SCHEMAS[tema], ensure_ascii=False, indent=2)
    blocos = "".join(BLOCO.format(id=cid, texto=(txt or "").strip())
                     for cid, txt in lote)
    return INSTRUCAO.format(n=len(lote), schema=schema, capitulos=blocos)


def validar_resposta(bruto, lote):
    """
    Confere item a item. So aproveita o que voltou com id que foi enviado.
    O que faltar continua pendente e entra na proxima execucao.
    """
    enviados = {cid for cid, _ in lote}
    if isinstance(bruto, dict):
        bruto = bruto.get("resultados") or bruto.get("items") or [bruto]
    if not isinstance(bruto, list):
        return {}, enviados

    aproveitados = {}
    for item in bruto:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id", "")).strip()
        if cid in enviados and cid not in aproveitados:
            aproveitados[cid] = {k: v for k, v in item.items() if k != "id"}
    return aproveitados, enviados - set(aproveitados)


def _limpar_json(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.removeprefix("json").strip()
        if "```" in t:
            t = t[: t.rindex("```")]
    return json.loads(t.strip())


def chamar_gemini(prompt, modelo, chave, max_tokens=8000):
    import google.generativeai as genai
    genai.configure(api_key=chave)
    m = genai.GenerativeModel(modelo)
    r = m.generate_content(prompt, generation_config={
        "temperature": 0,
        "max_output_tokens": max_tokens,
        "response_mime_type": "application/json",
    })
    return _limpar_json(r.text)


def pendentes(con, tema, limite):
    """Capitulos do tema que ainda nao tem extracao por LLM em `valores`."""
    campos = list(SCHEMAS[tema])
    marcas = ",".join("?" * len(campos))
    return con.execute(f"""
        SELECT c.caso_id, c.texto
        FROM capitulos c
        WHERE c.tema = ?
          AND c.caso_id IS NOT NULL
          AND c.caso_id NOT IN (
              SELECT caso_id FROM valores
              WHERE metodo = 'llm' AND campo IN ({marcas}))
        LIMIT ?
    """, (tema, *campos, limite)).fetchall()


def gravar(con, caso_id, dados, tema, modelo, capitulo):
    agora = time.strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    for campo in SCHEMAS[tema]:
        if campo not in dados:
            continue
        valor = dados[campo]
        valor = "nao_informado" if valor is None else str(valor)
        con.execute(
            "INSERT OR REPLACE INTO valores "
            "(caso_id, campo, valor, evidencia, metodo, versao, extraido_em) "
            "VALUES (?,?,?,?,?,?,?)",
            (caso_id, campo, valor, (capitulo or "")[:400], "llm",
             f"{modelo}:{VERSAO_PROMPT}", agora))
        n += 1
    con.commit()
    return n


def processar(banco, tema, limite, modelo, dry_run, lote_tam=LOTE_PADRAO):
    if not Path(banco).exists():
        sys.exit(f"banco nao encontrado: {banco}\nRode processar.py antes.")

    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    linhas = [(l["caso_id"], l["texto"]) for l in pendentes(con, tema, limite)]

    print(f"{len(linhas)} capitulos pendentes de extracao.")
    if not linhas:
        con.close()
        return

    lotes = [linhas[i:i + lote_tam] for i in range(0, len(linhas), lote_tam)]
    chars = sum(len(montar_prompt(l, tema)) for l in lotes)
    tokens = chars / 4                       # ~4 chars por token em pt-BR

    print(f"agrupados em {len(lotes)} chamadas de ate {lote_tam} capitulos")
    print(f"volume estimado: {tokens:,.0f} tokens de entrada")
    print(f"modelo: {modelo}")

    if dry_run:
        print("\n--- exemplo de prompt (primeiro lote, truncado) ---\n")
        print(montar_prompt(lotes[0][:2], tema)[:1600])
        print("\n--- fim ---\n")
        print("Nada foi enviado. Tire o --dry-run para extrair de verdade.")
        con.close()
        return

    chave = obter_chave()
    ok = falharam = campos = 0

    for i, lote in enumerate(lotes, 1):
        prompt = montar_prompt(lote, tema)
        bruto = None
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                bruto = chamar_gemini(prompt, modelo, chave)
                break
            except json.JSONDecodeError:
                if tentativa == TENTATIVAS:
                    print(f"  lote {i}: resposta nao e JSON valido")
            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower():
                    print(f"\n  lote {i}: cota atingida ({type(e).__name__})")
                    print("  O que ja foi gravado esta salvo. Rode de novo")
                    print("  amanha ou troque para um modelo com cota maior.")
                    bruto = None
                    break
                if tentativa == TENTATIVAS:
                    print(f"  lote {i}: {type(e).__name__} {msg[:120]}")
                else:
                    time.sleep(2 ** tentativa)

        if bruto is None:
            falharam += len(lote)
            if "cota" in locals().get("msg", ""):
                break
            continue

        aproveitados, faltaram = validar_resposta(bruto, lote)
        textos = dict(lote)
        for cid, dados in aproveitados.items():
            campos += gravar(con, cid, dados, tema, modelo, textos[cid])
        ok += len(aproveitados)
        falharam += len(faltaram)

        marca = f"  ({len(faltaram)} sem resposta)" if faltaram else ""
        print(f"  lote {i}/{len(lotes)}: {len(aproveitados)} extraidos{marca}")
        time.sleep(PAUSA)

    con.close()
    print(f"\n{ok} capitulos extraidos, {falharam} pendentes, "
          f"{campos} campos gravados.")
    if falharam:
        print("Os pendentes continuam no banco: rode de novo para tentar.")
    print("\nProximo passo: remontar o dataset para trazer os campos novos")
    print(f"  python montar_dataset.py --banco {banco} --saida ../data/dataset.csv")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--banco", default="../data/juripredict.db")
    p.add_argument("--tema", default="insalubridade", choices=list(SCHEMAS))
    p.add_argument("--limite", type=int, default=5000)
    p.add_argument("--modelo", default=MODELO_PADRAO)
    p.add_argument("--lote", type=int, default=LOTE_PADRAO,
                   help="capitulos por chamada; menos e mais seguro")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    processar(a.banco, a.tema, a.limite, a.modelo, a.dry_run, a.lote)