"""Busca diária de oportunidades na API interna da Webmotors (/api/search/car).

Uso:
    python3 -I scripts/busca.py              # busca na API, grava snapshot do dia e relatório
    python3 -I scripts/busca.py --sem-busca  # só regenera o relatório a partir do snapshot do dia

As regras pessoais (local, raio, cortes, alvos, financiamento, régua do score) vêm do
config.json, criado pelo /setup (ver scripts/config.py).

Saídas:
    data/snapshots/AAAA-MM-DD.json  fotografia do dia (anúncios já filtrados e enriquecidos)
    data/relatorio.md               diff contra o snapshot anterior (novos, preço mudou, sumiram)
    data/log.jsonl                  status de cada chamada (monitoramento do antibot)
    data/raw/                       corpo de respostas com erro/bloqueio

Buscas: uma por modelo-alvo (cfg["alvos"]) + uma geral (cfg["busca"]["geral"]), unidas por id.
Câmbio fora do escolhido é cortado (some); marca proibida, modelo recusado, versão abaixo das
aprovadas e ano abaixo do mínimo entram no snapshot com "ignorado" = motivo (aparecem
esmaecidos, fora do ranking e do diff).

Bloqueio: na primeira resposta != 200 o script para (exit 2) sem gravar snapshot,
para não gerar falsos "sumiram". Se existir data/cookies.json (lista de cookies no
formato do Playwright, exportada após resolver o captcha), eles são enviados.
"""

import argparse
import json
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"
SNAPSHOTS = DATA / "snapshots"
LOG = DATA / "log.jsonl"
RELATORIO = DATA / "relatorio.md"
COOKIES = DATA / "cookies.json"

API = "https://www.webmotors.com.br/api/search/car"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# --- Constantes da Webmotors (iguais para qualquer usuário; as regras pessoais vêm do config.json) ---
LOCADORAS = ["LOCALIZA", "MOVIDA", "UNIDAS", "LIONS"]
FOTO_BASE = "https://image.webmotors.com.br/_fotos/anunciousados/gigante/"
MAX_FOTOS = 5
# Palavras de motor/câmbio/combustível que não dizem a versão (para o título curto no comparador)
NAO_VERSAO = {"FLEX", "TURBO", "AUTOMATICO", "AUTOMATICA", "AUT", "AT", "MT", "CVT", "XTRONIC", "TIPTRONIC", "DCT",
              "TSI", "TGDI", "GDI", "VVT", "IFLEX", "FLEXSTART", "TOTALFLEX", "TOTAL", "GASOLINA", "DIESEL", "HIBRIDO",
              "ELETRICO", "MANUAL", "PORTAS", "4X2", "4X4", "AWD", "TB", "TDI", "MPI", "VTI", "DOHC", "SOHC", ""}


# --- Regras puras (testadas em tests/test_busca.py). `cfg` é o config completo (config.carregar) ---

def parcela(preco, meses, fin):
    """Tabela Price: saldo = preço − entrada + tarifas (tarifas e IOF somados ao financiado)."""
    saldo = preco - fin["entrada"] + fin["tarifas"]
    if saldo <= 0:
        return 0.0
    return saldo * fin["taxa_mes"] / (1 - (1 + fin["taxa_mes"]) ** -meses)


def preco_para_parcela(valor, meses, fin):
    """Inverso de `parcela`: maior preço cuja parcela em `meses` é `valor`."""
    i = fin["taxa_mes"]
    return valor * (1 - (1 + i) ** -meses) / i + fin["entrada"] - fin["tarifas"]


def faixa(valor_parcela, fin):
    if valor_parcela <= fin["parcela_ideal"]:
        return "ideal"
    return "no limite" if valor_parcela <= fin["parcela_limite"] else "acima"


def km_por_ano(km, ano_fabricacao, ano_atual):
    return km / max(1, ano_atual - ano_fabricacao)


def tokens(texto):
    return set(re.split(r"[^A-Z0-9]+", sem_acento(texto).upper()))


def eh_manual(versao, cambio):
    return (cambio or "").strip().lower() == "manual" or "MANUAL" in tokens(versao)


def cambio_aceito(versao, cambio, regra):
    """`regra` = "automatico" (qualquer um que não seja manual: Automática, CVT, automatizado), "manual" ou "qualquer"."""
    if regra == "qualquer":
        return True
    return eh_manual(versao, cambio) == (regra == "manual")


def versao_aceita(versao, regra):
    """`exigir` = precisa ter ao menos um token; `excluir` = não pode ter nenhum."""
    t = tokens(versao)
    if regra.get("exigir") and not t & {sem_acento(x).upper() for x in regra["exigir"]}:
        return False
    return not t & {sem_acento(x).upper() for x in regra.get("excluir", [])}


def versao_curta(versao):
    """ "1.0 TURBO FLEX LT AUTOMÁTICO" -> "LT": tira motor, câmbio e combustível."""
    partes = re.split(r"\s+", sem_acento(versao).upper())
    return " ".join(p for p in partes if p not in NAO_VERSAO and not re.search(r"\d", p))


def curva(x, pontos):
    """Pontos [(valor, nota), ...] em ordem crescente de valor, ligados por retas; fora deles, o extremo."""
    if x <= pontos[0][0]:
        return pontos[0][1]
    for (x0, y0), (x1, y1) in zip(pontos, pontos[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pontos[-1][1]


def valores_score(preco, km, km_ano, fipe_pct, ano_modelo, cfg):
    fin = cfg["financiamento"]
    return {
        "parcela": parcela(preco, fin["prazo_ref"], fin) if fin else None,
        "preco": preco,
        "km": km,
        "uso": km_ano,
        "fipe": fipe_pct or 100,  # sem FIPE na API: neutro
        "ano": ano_modelo,
    }


def pontuar(preco, km, km_ano, fipe_pct, ano_modelo, cfg):
    """Score base de 0 a 100 pela régua de cfg["score"]. Ajustes da análise entram depois."""
    v = valores_score(preco, km, km_ano, fipe_pct, ano_modelo, cfg)
    partes = {k: round(curva(v[k], r["curva"]), 1) for k, r in cfg["score"].items()}
    return round(sum(partes.values())), partes


def classificar(marca, modelo, versao, cambio, ano_modelo, cfg):
    """Decide o destino de um anúncio. Devolve None (corte rígido: some) ou (chave, motivo_ignorado).

    Ignorado = aparece esmaecido no relatório, fora do ranking: marca proibida, modelo recusado,
    versão abaixo das aprovadas ou ano abaixo do mínimo de um modelo-alvo.
    """
    b = cfg["busca"]
    if not cambio_aceito(versao, cambio, b["cambio"]):
        return None
    marca_n = sem_acento(marca).upper()
    # por token: "KICKS PLAY" também é o Kicks dos alvos
    chave = next((k for k, r in cfg["alvos"].items()
                  if sem_acento(r["marca"]).upper() == marca_n and set(tokens(r["modelo"])) - {""} <= tokens(modelo)), None)
    if marca_n in {sem_acento(m).upper() for m in b["marcas_proibidas"]}:
        return slug(modelo), "marca proibida"
    if tokens(modelo) & {sem_acento(m).upper() for m in b["modelos_recusados"]}:
        return slug(modelo), "modelo recusado"
    if chave is None:
        return slug(modelo), None
    regra = cfg["alvos"][chave]
    if ano_modelo < regra["ano_min"]:
        return chave, f"ano-modelo abaixo do mínimo ({regra['ano_min']})"
    if not versao_aceita(versao, regra):
        return chave, "versão abaixo das aprovadas"
    return chave, None


def eh_locadora(nome_loja):
    nome = sem_acento(nome_loja or "").upper()
    return any(l in nome for l in LOCADORAS)


def sem_acento(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def slug(texto):
    # "1.0 TURBO FLEX LT AUTOMÁTICO" -> "10-turbo-flex-lt-automatico" (formato dos links do site)
    return "-".join(sem_acento(texto).lower().replace(".", "").split())


def comparar(anterior, atual):
    """Diff entre dois dicts {id: anuncio}. Ids são strings (chaves JSON)."""
    novos = [atual[i] for i in atual if i not in anterior]
    sumiram = [anterior[i] for i in anterior if i not in atual]
    mudou_preco = [
        {**atual[i], "preco_anterior": anterior[i]["preco"]}
        for i in atual if i in anterior and atual[i]["preco"] != anterior[i]["preco"]
    ]
    return {"novos": novos, "mudou_preco": mudou_preco, "sumiram": sumiram}


# --- API ---

def buscas(cfg):
    """Nome -> regra de cada busca: uma por alvo + a geral (se houver)."""
    todas = dict(cfg["alvos"])
    if cfg["busca"]["geral"]:
        todas["geral"] = cfg["busca"]["geral"]
    return todas


def montar_url(regra, pagina, cfg, extra=None):
    """URL da API. Os filtros vão dentro de `url`, no formato da página de busca do site."""
    l, b = cfg["local"], cfg["busca"]
    cidade = f"{config.NOME_UF[l['uf']]}-{l['cidade']}"
    params = {
        "tipoveiculo": "carros-usados",
        "localizacao": f"{l['lat']},{l['lng']}x{l['raio_km']}km",
        "estadocidade": cidade,
        **({"marca1": regra["marca"]} if regra.get("marca") else {}),
        **({"modelo1": regra["modelo"]} if regra.get("modelo") else {}),
        **({"carroceria": regra["carroceria"]} if regra.get("carroceria") else {}),
        "anode": str(regra["ano_min"]),
        "precoate": str(b["preco_max"]),
        "kmate": str(b["km_max"]),
        "anunciante": "|".join(b["vendedores"]),
        **(extra or {}),
        "page": str(pagina),
    }
    alvo = f"https://www.webmotors.com.br/carros-usados/{l['uf'].lower()}-{slug(l['cidade'])}?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )
    return API + "?" + urllib.parse.urlencode({
        "url": alvo, "displayPerPage": "47", "actualPage": str(pagina),
        "showCount": "true", "order": "1",
    })


def cabecalhos():
    h = {"accept": "application/json", "user-agent": UA}
    if COOKIES.exists():
        cookies = json.loads(COOKIES.read_text())
        h["cookie"] = "; ".join(
            f"{c['name']}={c['value']}" for c in cookies if "webmotors" in c.get("domain", "")
        )
    return h


def chamar(nome, url):
    req = urllib.request.Request(url, headers=cabecalhos())
    inicio = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, corpo = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, corpo = e.code, e.read()
    except Exception as e:  # rede, timeout
        status, corpo = 0, str(e).encode()
    DATA.mkdir(exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"), "busca": nome, "status": status,
            "bytes": len(corpo), "ms": int((time.time() - inicio) * 1000),
            "cookies": COOKIES.exists(),
        }, ensure_ascii=False) + "\n")
    return status, corpo


class Bloqueio(Exception):
    pass


def salvar_bloqueio(nome, pagina, status, corpo):
    RAW.mkdir(parents=True, exist_ok=True)
    destino = RAW / f"{datetime.now():%Y%m%dT%H%M%S}-{nome}-p{pagina}-status{status}.txt"
    destino.write_bytes(corpo)
    return Bloqueio(f"{nome}: status {status} ({len(corpo)} bytes) — corpo em {destino.relative_to(ROOT)}")


def buscar(nome, regra, pausa, cfg):
    anuncios, pagina, total_paginas = [], 1, 1
    while pagina <= total_paginas:
        status, corpo = chamar(nome, montar_url(regra, pagina, cfg))
        if status != 200:
            raise salvar_bloqueio(nome, pagina, status, corpo)
        d = json.loads(corpo)
        total_paginas = (d.get("Pagination") or {}).get("PageTotal") or 1
        anuncios += d.get("SearchResults") or []
        pagina += 1
        if pagina <= total_paginas:
            time.sleep(pausa())
    return anuncios


def enriquecer(a, modelo, ano_atual, cfg, ignorado=None):
    s, p, v = a["Specification"], a["Prices"], a["Seller"]
    fin = cfg["financiamento"]
    ano_fab, ano_mod = int(s["YearFabrication"]), int(s["YearModel"])
    km, preco = int(s["Odometer"]), int(p["Price"])
    k_ano = round(km_por_ano(km, ano_fab, ano_atual))
    score, partes = pontuar(preco, km, k_ano, a.get("FipePercent"), ano_mod, cfg)
    fotos = [FOTO_BASE + f["PhotoPath"].replace("\\", "/")
             for f in sorted((a.get("Media") or {}).get("Photos") or [], key=lambda f: f.get("Order", 0))][:MAX_FOTOS]
    return {
        "id": a["UniqueId"],
        "modelo": modelo,
        "nome": f"{s['Make']['Value']} {s['Model']['Value']}".title(),
        "ignorado": ignorado,
        "versao": s["Version"]["Value"],
        "cambio": s.get("Transmission"),
        "ano": f"{ano_fab}/{ano_mod}",
        "km": km,
        "km_ano": k_ano,
        "preco": preco,
        "score_base": score,
        "score_partes": partes,
        "fotos": fotos,
        "fipe_pct": a.get("FipePercent"),
        "parcelas": {str(n): round(parcela(preco, n, fin)) for n in fin["prazos"]} if fin else {},
        "faixa": faixa(parcela(preco, fin["prazo_ref"], fin), fin) if fin else None,
        "cidade": v.get("City"),
        "loja": v.get("FantasyName"),
        "tipo_vendedor": (v.get("AdType") or {}).get("Value"),
        "locadora": eh_locadora(v.get("FantasyName")),
        "porta_malas": s.get("TrunkCapacity"),
        "cor": (s.get("Color") or {}).get("Primary"),
        "atributos": [x["Name"] for x in s.get("VehicleAttributes") or []],
        "comentario": (a.get("LongComment") or "").strip(),
        "link": f"https://www.webmotors.com.br/comprar/{slug(s['Make']['Value'])}/{slug(s['Model']['Value'])}/"
                f"{slug(s['Version']['Value'])}/{s.get('NumberPorts') or 4}-portas/{ano_fab}-{ano_mod}/{a['UniqueId']}",
    }


# --- Snapshot e relatório ---

def snapshot_anterior(hoje):
    anteriores = sorted(p for p in SNAPSHOTS.glob("*.json") if p.stem < hoje)
    return json.loads(anteriores[-1].read_text()) if anteriores else None


def num(x):
    return f"{x:,}".replace(",", ".")


def colunas(cfg):
    fin = cfg["financiamento"]
    cols = ["Score", "Modelo", "Versão", "Ano", "Km", "Km/ano", "Preço", "FIPE"]
    if fin:
        cols += [f"Parcela {' / '.join(f'{n}x' for n in fin['prazos'])}", "Faixa"]
    return cols + ["Cidade", "Loja", "Flags", "Anúncio"]


def linha(a, cfg, extra=""):
    fin = cfg["financiamento"]
    flags = []
    if a["locadora"]:
        flags.append("locadora")
    if a["km_ano"] > 15000:
        flags.append(">15k km/ano")
    cel = [str(a.get("score_base", "—")), a["modelo"], a["versao"], a["ano"], num(a["km"]), num(a["km_ano"]),
           f"R$ {num(a['preco'])} {extra}".strip(), f"{a['fipe_pct']}%"]
    if fin:
        ps = a.get("parcelas") or {}
        cel += [" / ".join(num(ps.get(str(n), round(parcela(a["preco"], n, fin)))) for n in fin["prazos"]),
                a.get("faixa") or faixa(parcela(a["preco"], fin["prazo_ref"], fin), fin)]
    cel += [a["cidade"] or "—", a["loja"] or "—", ", ".join(flags) or "—", f"[{a['id']}]({a['link']})"]
    return "| " + " | ".join(cel) + " |"


def tabela(itens, cfg, extra=lambda a: ""):
    if not itens:
        return "_Nenhum._\n"
    cols = colunas(cfg)
    cab = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols)
    ordenados = sorted(itens, key=lambda a: (-a.get("score_base", 0), a["preco"]))
    return cab + "\n" + "\n".join(linha(a, cfg, extra(a)) for a in ordenados) + "\n"


def candidatos(anuncios):
    return {i: a for i, a in anuncios.items() if not a.get("ignorado")}


def gerar_relatorio(snap, anterior, cfg):
    atual = candidatos(snap["anuncios"])
    ignorados = [a for a in snap["anuncios"].values() if a.get("ignorado")]
    diff = comparar(candidatos(anterior["anuncios"]), atual) if anterior else {"novos": list(atual.values()), "mudou_preco": [], "sumiram": []}
    ref = f"comparado com {anterior['data']}" if anterior else "primeira execução — tudo aparece como novo"
    por_modelo = {}
    for a in atual.values():
        por_modelo[a["modelo"]] = por_modelo.get(a["modelo"], 0) + 1
    contagem = ", ".join(f"{m}: {n}" for m, n in sorted(por_modelo.items(), key=lambda x: -x[1]))
    cortes = ", ".join(f"{m}: {n}" for m, n in snap["descartados_pelo_filtro"].items())
    linhas_ign = "\n".join(
        f"| {a.get('nome') or a['modelo']} | {a['versao']} | {a['ano']} | {num(a['km'])} | R$ {num(a['preco'])} | "
        f"{a['ignorado']} | [{a['id']}]({a['link']}) |"
        for a in sorted(ignorados, key=lambda a: (a.get("nome") or a["modelo"], a["preco"])))
    return "\n".join([
        f"# Relatório {snap['data']} ({ref})",
        "",
        f"Candidatos que passaram nos cortes: **{len(atual)}** ({contagem or 'nenhum'}).",
        f"Ignorados (aparecem esmaecidos, fora do ranking): {len(ignorados)}.",
        f"Cortados pelo câmbio (por busca): {cortes}.",
        "",
        f"## 🆕 Novos ({len(diff['novos'])})",
        tabela(diff["novos"], cfg),
        f"## 💲 Preço mudou ({len(diff['mudou_preco'])})",
        tabela(diff["mudou_preco"], cfg, lambda a: f"(antes {num(a['preco_anterior'])})"),
        f"## ❌ Sumiram ({len(diff['sumiram'])})",
        tabela(diff["sumiram"], cfg),
        f"## 📋 Todos os candidatos de hoje ({len(atual)})",
        tabela(list(atual.values()), cfg),
        f"## 🚫 Ignorados ({len(ignorados)})",
        ("| Carro | Versão | Ano | Km | Preço | Motivo | Anúncio |\n|---|---|---|---|---|---|---|\n" + linhas_ign + "\n")
        if ignorados else "_Nenhum._\n",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-busca", action="store_true", help="regenera o relatório a partir do snapshot de hoje")
    ap.add_argument("--pausa-min", type=float, default=20)
    ap.add_argument("--pausa-max", type=float, default=45)
    args = ap.parse_args()

    try:
        cfg = config.carregar()
    except config.ConfigInvalida as e:
        print(e, file=sys.stderr)
        return 1

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    hoje = date.today().isoformat()
    destino = SNAPSHOTS / f"{hoje}.json"

    if args.sem_busca:
        snap = json.loads(destino.read_text())
    else:
        pausa = lambda: random.uniform(args.pausa_min, args.pausa_max)
        anuncios, descartados = {}, {}
        try:
            for i, (nome, regra) in enumerate(buscas(cfg).items()):
                if i:
                    time.sleep(pausa())
                brutos = buscar(nome, regra, pausa, cfg)
                novos = cortados = 0
                for a in brutos:
                    s = a["Specification"]
                    destino_a = classificar(s["Make"]["Value"], s["Model"]["Value"], s["Version"]["Value"],
                                            s.get("Transmission"), int(s["YearModel"]), cfg)
                    if destino_a is None:
                        cortados += 1
                    elif str(a["UniqueId"]) not in anuncios:  # a busca geral repete os alvos
                        chave, motivo = destino_a
                        anuncios[str(a["UniqueId"])] = enriquecer(a, chave, date.today().year, cfg, motivo)
                        novos += 1
                descartados[nome] = cortados
                print(f"[{nome}] {len(brutos)} na API, {cortados} cortados, {novos} novos no snapshot", flush=True)
        except Bloqueio as e:
            print(f"BLOQUEIO: {e}", file=sys.stderr)
            print("Snapshot NÃO gravado. Resolver captcha e exportar cookies para data/cookies.json.", file=sys.stderr)
            return 2
        snap = {
            "data": hoje, "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "descartados_pelo_filtro": descartados, "anuncios": anuncios,
        }
        destino.write_text(json.dumps(snap, ensure_ascii=False, indent=2))

    RELATORIO.write_text(gerar_relatorio(snap, snapshot_anterior(hoje), cfg))
    print(f"Snapshot: {destino.relative_to(ROOT)} | Relatório: {RELATORIO.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
