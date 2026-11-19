"""Sondagem leve da API para calibrar o config.json (usada pelo /setup). Não grava snapshot.

Uso:
    python3 -I scripts/sondar.py facetas               # 1 chamada: carrocerias e marcas no raio, com contagem
    python3 -I scripts/sondar.py facetas --marca NISSAN # 1 chamada: modelos da marca no raio
    python3 -I scripts/sondar.py buscas                # 1 chamada por busca do config (só a página 1)

`buscas` mostra, para cada alvo, quantos anúncios a API achou, como ela entendeu o filtro
(FilterCustom) e as versões vistas com o destino de cada uma (aceita / ignorada / cortada),
para conferir as listas `exigir` e `excluir`. Pausa de 20 a 45 s entre chamadas (antibot).
Status != 200: para na hora (exit 2), igual à busca diária.
"""

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import busca as b  # noqa: E402
import config  # noqa: E402

GRUPOS = {"BodyType": "Carrocerias", "Make": "Marcas", "Model": "Modelos", "Transmission": "Câmbios",
          "SellerType": "Vendedores"}


def chamar(nome, url):
    status, corpo = b.chamar(f"sondagem-{nome}", url)
    if status != 200:
        raise b.salvar_bloqueio(f"sondagem-{nome}", 1, status, corpo)
    return json.loads(corpo)


def facetas(d):
    """{"BodyType": [(nome, contagem), ...], ...} a partir das facetas da resposta (showMenu=true).

    Em 11/2026 elas vinham em `Filters` (lista plana de grupos); em 10/2026, em `FiltersGrouped`
    (grupos dentro de grupos). A busca é recursiva e aceita os dois.
    """
    achados = {}

    def andar(itens):
        for x in itens or []:
            if x.get("name") in GRUPOS:
                achados[x["name"]] = [(i.get("name"), i.get("count")) for i in x.get("items") or []]
            andar(x.get("items"))

    andar(d.get("FiltersGrouped") or d.get("Filters"))
    return achados


def com_menu(url):
    return url + "&showMenu=true"


def cmd_facetas(cfg, marca):
    regra = {"marca": marca, "ano_min": 1990} if marca else {"ano_min": 1990}
    # sem modelo1: com a marca, a API devolve os modelos dela na faceta
    d = chamar("facetas", com_menu(b.montar_url(regra, 1, cfg)))
    b.RAW.mkdir(parents=True, exist_ok=True)
    bruto = b.RAW / f"sondagem-facetas{'-' + marca.lower() if marca else ''}.json"
    bruto.write_text(json.dumps(d, ensure_ascii=False))
    print(f"Anúncios no raio com preço e km dentro dos cortes (qualquer ano): {d.get('Count')} (resposta em {bruto.relative_to(ROOT)})")
    achadas = facetas(d)
    if not achadas:
        print(f"Sem facetas na resposta (chaves: {sorted(d)}).", file=sys.stderr)
    for chave, itens in achadas.items():
        print(f"\n{GRUPOS[chave]}:")
        for nome, n in sorted(itens, key=lambda x: -(x[1] or 0)):
            print(f"  {n or 0:5d}  {nome}")


def cmd_buscas(cfg, pausa):
    for i, (nome, regra) in enumerate(b.buscas(cfg).items()):
        if i:
            time.sleep(pausa())
        d = chamar(nome, b.montar_url(regra, 1, cfg))
        fc = d.get("FilterCustom") or {}
        pags = (d.get("Pagination") or {}).get("PageTotal") or 1
        entendeu = {"Veiculos": fc.get("Veiculos"), "Carroceria": fc.get("Carroceria"), "Cidade": fc.get("Cidade")}
        print(f"\n## {nome}: {d.get('Count')} anúncios, {pags} página(s) de 47")
        print("   a API entendeu:", json.dumps(entendeu, ensure_ascii=False))
        destinos = Counter()
        for a in d.get("SearchResults") or []:
            s = a["Specification"]
            r = b.classificar(s["Make"]["Value"], s["Model"]["Value"], s["Version"]["Value"],
                              s.get("Transmission"), int(s["YearModel"]), cfg)
            destino = "cortada (câmbio)" if r is None else (f"ignorada: {r[1]}" if r[1] else f"aceita ({r[0]})")
            rotulo = s["Version"]["Value"] if nome != "geral" else f"{s['Make']['Value']} {s['Model']['Value']}"
            destinos[(destino, rotulo)] += 1
        for (destino, rotulo), n in sorted(destinos.items()):
            print(f"   {n:3d}  {destino:45s} {rotulo}")
        if nome != "geral" and not d.get("Count"):
            print("   ATENÇÃO: nenhum anúncio. Conferir a grafia de marca/modelo com `sondar.py facetas --marca`.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["facetas", "buscas"])
    ap.add_argument("--marca")
    ap.add_argument("--pausa-min", type=float, default=20)
    ap.add_argument("--pausa-max", type=float, default=45)
    args = ap.parse_args()
    try:
        cfg = config.carregar()
    except config.ConfigInvalida as e:
        print(e, file=sys.stderr)
        return 1
    try:
        if args.acao == "facetas":
            cmd_facetas(cfg, args.marca)
        else:
            cmd_buscas(cfg, lambda: random.uniform(args.pausa_min, args.pausa_max))
    except b.Bloqueio as e:
        print(f"BLOQUEIO: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
