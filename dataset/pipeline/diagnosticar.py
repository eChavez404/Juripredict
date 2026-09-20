"""
Diagnostico das regras de corte e rotulagem contra documentos reais.

Nao altera nada. So mostra o que o cortador viu e o que o rotulador decidiu,
para que o ajuste seja feito sobre texto de verdade em vez de suposicao.

    python diagnosticar.py --entrada ../data/normalized
    python diagnosticar.py --entrada ../data/normalized --caso sem_capitulo
    python diagnosticar.py --entrada ../data/normalized --caso ambiguo --n 6
"""

import argparse
from pathlib import Path

from cortar_secoes import cortar
from rotular_por_regra import rotular
from processar import extrair_texto, classificar_evento

TEMA = "insalubridade"
LARGURA = 74


def classificar(caminho):
    """Roda o pipeline num documento e devolve o que aconteceu."""
    texto = extrair_texto(caminho)
    s = cortar(texto)
    cap = s.capitulo_de(TEMA)

    if not s.dispositivo:
        situacao = "sem_dispositivo"
        r = None
    else:
        r = rotular(s.dispositivo, TEMA, s.fundamentacao)
        situacao = r.resultado_pedido

    evento = classificar_evento(texto, s.dispositivo)
    if evento != "MERITO_PRIMEIRO_GRAU":
        situacao = evento

    return {"arquivo": caminho.name, "secoes": s, "capitulo": cap,
            "rotulo": r, "situacao": situacao, "texto": texto, "evento": evento}


def mostrar(d, completo=False):
    print("=" * LARGURA)
    print(f"{d['arquivo']}   [{d['situacao']}]")
    print("=" * LARGURA)

    s = d["secoes"]
    print(f"evento processual   : {d.get('evento', '-')}")
    print(f"tem capitulo do tema: {'sim' if d['capitulo'] else 'nao'}")
    print(f"estrategia de corte : {s.estrategia}")
    print(f"tem fundamentacao   : {'sim' if s.fundamentacao else 'NAO'}"
          f"   ({len(s.fundamentacao)} chars)")
    print(f"tem dispositivo     : {'sim' if s.dispositivo else 'NAO'}"
          f"   ({len(s.dispositivo)} chars)")

    print(f"\ntitulos detectados na fundamentacao ({len(s.capitulos)}):")
    if not s.capitulos:
        print("   NENHUM — e aqui que a ancora esta falhando")
    for c in s.capitulos:
        marca = "  <-- tema" if c.tema else ""
        print(f"   [{str(c.tema or '-'):<14}] {c.titulo[:52]}{marca}")

    if s.dispositivo:
        print("\ndispositivo:")
        disp = s.dispositivo if completo else s.dispositivo[:700]
        for linha in disp.split("\n"):
            if linha.strip():
                print(f"   {linha.strip()[:70]}")
        if not completo and len(s.dispositivo) > 700:
            print("   [...]")

    if d["rotulo"]:
        r = d["rotulo"]
        print(f"\nrotulo: pedido={r.resultado_pedido}  global={r.resultado_global}"
              f"  grau={r.grau}")
        if r.trecho:
            print(f"trecho que decidiu: {r.trecho[:200]}")

    # sinais de que o documento nao e sentenca de merito
    baixo = d["texto"][:2500].lower()
    pistas = [p for p in ("impugnacao aos calculos", "impugnação aos cálculos",
                          "liquidacao", "liquidação", "embargos de declaracao",
                          "embargos de declaração", "execucao", "execução",
                          "calculos", "cálculos")
              if p in baixo]
    if pistas:
        print(f"\nPISTAS de que NAO e merito: {pistas}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="../data/normalized")
    ap.add_argument("--caso", default="todos",
                    help="todos | sem_capitulo | ambiguo | nao_mencionado | "
                         "deferido | indeferido | sem_dispositivo")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--completo", action="store_true",
                    help="mostra o dispositivo inteiro")
    a = ap.parse_args()

    arquivos = sorted(p for p in Path(a.entrada).rglob("*")
                      if p.suffix.lower() in (".txt", ".html", ".htm", ".pdf"))
    if not arquivos:
        print(f"nenhum documento em {a.entrada}")
        return

    resultados = [classificar(p) for p in arquivos]

    print("\nRESUMO")
    print("-" * LARGURA)
    contagem = {}
    for r in resultados:
        contagem[r["situacao"]] = contagem.get(r["situacao"], 0) + 1
    for k, v in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"  {k:<20}{v:>4}")
    print()

    alvo = [r for r in resultados
            if a.caso == "todos" or r["situacao"] == a.caso]
    if not alvo:
        print(f"nenhum documento com situacao '{a.caso}'")
        return

    print(f"mostrando {min(a.n, len(alvo))} de {len(alvo)} com "
          f"situacao '{a.caso}'\n")
    for d in alvo[: a.n]:
        mostrar(d, a.completo)


if __name__ == "__main__":
    main()