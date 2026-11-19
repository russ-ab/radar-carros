"""Gera o relatório visual (HTML) do dia: snapshot + análise -> modelo.

Uso:
    python3 -I scripts/relatorio_html.py                    # hoje, todos os modelos
    python3 -I scripts/relatorio_html.py --data AAAA-MM-DD

Entradas: data/snapshots/<data>.json e data/analises/<data>.json (escrita por Claude
depois da conversa). Saída: relatorios/<modelo>-<data>.html (autocontido).
"""

import argparse
import base64
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELOS = ROOT / "relatorios" / "modelos"
SAIDA = ROOT / "relatorios"

# Financiamento e régua do score vêm do config.json (fonte única) para a página recalcular
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402
from busca import UA, pontuar, versao_curta  # noqa: E402

FOTOS = ROOT / "data" / "fotos"
TAMANHO_FOTO = "?s=fill&w=480&h=320&q=70"
TAMANHO_LEVE = "?s=fill&w=360&h=240&q=55"  # último degrau: cache separado em data/fotos/leve/

# Limite do Artifact: 16 MB por página. Folga de 1 MB.
LIMITE_BYTES = 15 * 1024 * 1024

# Degraus de redução, do mais completo ao mais enxuto. `cand` = máximo de fotos dos candidatos
# fora dos destaques (None = todas); `fora` = descartados e ignorados. Destaques sempre levam todas.
DEGRAUS = [
    {"nome": "padrão (descartados e ignorados só com a capa)", "cand": None, "fora": 1, "leve": False},
    # quem está fora do ranking perde a capa antes de os candidatos perderem fotos (são muitos: ~5 MB em 13/10)
    {"nome": "descartados e ignorados sem foto", "cand": None, "fora": 0, "leve": False},
    {"nome": "candidatos fora dos destaques com até 3 fotos", "cand": 3, "fora": 0, "leve": False},
    {"nome": "candidatos fora dos destaques só com a capa", "cand": 1, "fora": 0, "leve": False},
    {"nome": "fotos menores (360×240, qualidade 55)", "cand": 1, "fora": 0, "leve": True},
]


def qtd_fotos(veredito, destaque, degrau):
    """Quantas fotos o carro leva neste degrau (None = todas)."""
    if veredito in ("ignorado", "descartar"):
        return degrau["fora"]
    return None if destaque else degrau["cand"]


def primeiro_que_cabe(degraus, medir, limite=LIMITE_BYTES):
    """Devolve (degrau, tamanho) do primeiro degrau cujo HTML cabe no limite; senão, erro claro."""
    tamanhos = []
    for d in degraus:
        tamanho = medir(d)
        tamanhos.append(f"{d['nome']}: {tamanho / 1e6:.1f} MB")
        if tamanho <= limite:
            return d, tamanho
    raise ValueError(f"Relatório não cabe em {limite / 1e6:.1f} MB nem no último degrau ({'; '.join(tamanhos)}). "
                     "Levar as fotos para `files` do Artifact ou reduzir os carros exibidos.")


def foto_embutida(url, nome, leve=False):
    """Baixa (com cache em data/fotos/) e devolve como data URI: a página publicada não pode buscar imagens externas."""
    pasta = FOTOS / "leve" if leve else FOTOS
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{nome}.jpg"
    if not arq.exists():
        req = urllib.request.Request(url + (TAMANHO_LEVE if leve else TAMANHO_FOTO), headers={"user-agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                arq.write_bytes(r.read())
        except Exception as e:  # foto é opcional: segue sem ela
            print(f"  foto falhou ({nome}): {e}", file=sys.stderr)
            return None
        time.sleep(0.2)
    return "data:image/jpeg;base64," + base64.b64encode(arq.read_bytes()).decode()


def montar_dados(dia, cfg, degrau=DEGRAUS[0]):
    snap = json.loads((ROOT / "data" / "snapshots" / f"{dia}.json").read_text())
    arq_analise = ROOT / "data" / "analises" / f"{dia}.json"
    analise = json.loads(arq_analise.read_text()) if arq_analise.exists() else {}

    vereditos = analise.get("vereditos", {})
    grupos = analise.get("grupos", [])
    principal = {}  # id -> id do anúncio que representa o grupo
    for g in grupos:
        for i in g:
            principal[i] = g[0]

    carros = []
    for a in snap["anuncios"].values():
        if principal.get(a["id"], a["id"]) != a["id"]:
            continue  # duplicado: entra como "também anunciado em" no principal
        ids = next((g for g in grupos if a["id"] in g), [a["id"]])
        outros = [snap["anuncios"][str(i)] for i in ids[1:] if str(i) in snap["anuncios"]]
        v = vereditos.get(str(a["id"]), {})
        # Sempre recalcula: o snapshot guarda o score da época, mas a régua pode ter mudado
        a["score_base"], a["score_partes"] = pontuar(
            a["preco"], a["km"], a["km_ano"], a["fipe_pct"], int(a["ano"].split("/")[-1]), cfg)
        ajustes = [{"pontos": p, "motivo": m} for p, m in analise.get("ajustes", {}).get(str(a["id"]), [])]
        score = max(0, min(100, a["score_base"] + sum(j["pontos"] for j in ajustes)))
        veredito = "ignorado" if a.get("ignorado") else v.get("veredito", "sem análise")
        # Fotos embutidas pesam: quantas o carro leva depende do degrau (ver DEGRAUS e o limite de 16 MB)
        destaque = any(d.get("id") == a["id"] for d in analise.get("destaques", []))
        urls = a.get("fotos", [])[:qtd_fotos(veredito, destaque, degrau)]
        fotos = [f for i, url in enumerate(urls) if (f := foto_embutida(url, f"{a['id']}-{i}", degrau["leve"]))]
        carros.append({
            **{k: a[k] for k in a if k not in ("comentario", "fotos")},
            "versao_curta": versao_curta(a["versao"]),
            "score": score,
            "ajustes": ajustes,
            "fotos": fotos,
            # ignorado (marca proibida, versão/ano abaixo do aprovado) vence qualquer veredito: fica fora do ranking
            "veredito": veredito,
            "motivo": f"Ignorado: {a['ignorado']}." if a.get("ignorado") else v.get("motivo", ""),
            "tambem_em": [{"cidade": o["cidade"], "loja": o["loja"], "preco": o["preco"], "link": o["link"]} for o in outros],
        })

    return {
        "data": dia,
        "gerado_em": snap["gerado_em"],
        "local": {"cidade": cfg["local"]["cidade"], "raio_km": cfg["local"]["raio_km"]},
        "km_max": cfg["busca"]["km_max"],
        "preco_ideal": cfg["busca"].get("preco_ideal"),
        "nomes": {k: a["nome"] for k, a in cfg["alvos"].items()},
        "financiamento": cfg["financiamento"],  # null = compra à vista
        "score": cfg["score"],
        "resumo": analise.get("resumo", ""),
        "manchete": analise.get("manchete", ""),
        "destaques": analise.get("destaques", []),
        "achados": analise.get("achados", []),
        "mercado": analise.get("mercado", []),
        "carros": carros,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=date.today().isoformat())
    ap.add_argument("--modelo", default="todos")
    args = ap.parse_args()

    try:
        cfg = config.carregar()
    except config.ConfigInvalida as e:
        print(e, file=sys.stderr)
        return 1
    nomes = sorted(p.name.removesuffix(".html") for p in MODELOS.glob("*.html"))
    alvo = nomes if args.modelo == "todos" else [args.modelo]
    for nome in alvo:
        modelo = (MODELOS / f"{nome}.html").read_text()
        paginas = {}

        def medir(degrau):
            dados = json.dumps(montar_dados(args.data, cfg, degrau), ensure_ascii=False).replace("</", "<\\/")
            paginas[degrau["nome"]] = modelo.replace("__DADOS__", dados)
            return len(paginas[degrau["nome"]].encode())

        try:
            degrau, tamanho = primeiro_que_cabe(DEGRAUS, medir, LIMITE_BYTES)
        except ValueError as e:
            print(f"ERRO: {e}", file=sys.stderr)
            return 1
        destino = SAIDA / f"{nome}-{args.data}.html"
        destino.write_text(paginas[degrau["nome"]])
        print(f"{destino.relative_to(ROOT)} — {tamanho / 1e6:.1f} MB (limite {LIMITE_BYTES / 1e6:.1f} MB; degrau: {degrau['nome']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
