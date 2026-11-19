"""Configuração da busca: carrega, valida e completa o config.json (escrito pelo /setup).

Uso (linha de comando, chamado pelo /setup):
    python3 -I scripts/config.py cidade "Indaiatuba" SP   # acha lat/long no IBGE (data/ref/municipios.csv)
    python3 -I scripts/config.py validar                  # valida o config.json e imprime o resumo
    python3 -I scripts/config.py tarifas 95000 50000 48 1452.20 0.0166
        # tarifas/IOF embutidas numa simulação do banco (preço, entrada, meses, parcela, taxa ao mês)

O caminho do arquivo vem de RADAR_CONFIG (usado pelos testes) ou é config.json na raiz.
"""

import csv
import json
import os
import sys
import unicodedata

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUNICIPIOS = ROOT / "data" / "ref" / "municipios.csv"

# Código IBGE da UF -> (sigla, nome). A Webmotors usa o nome por extenso no filtro de cidade.
UFS = {
    12: ("AC", "Acre"), 27: ("AL", "Alagoas"), 16: ("AP", "Amapá"), 13: ("AM", "Amazonas"),
    29: ("BA", "Bahia"), 23: ("CE", "Ceará"), 53: ("DF", "Distrito Federal"), 32: ("ES", "Espírito Santo"),
    52: ("GO", "Goiás"), 21: ("MA", "Maranhão"), 51: ("MT", "Mato Grosso"), 50: ("MS", "Mato Grosso do Sul"),
    31: ("MG", "Minas Gerais"), 15: ("PA", "Pará"), 25: ("PB", "Paraíba"), 41: ("PR", "Paraná"),
    26: ("PE", "Pernambuco"), 22: ("PI", "Piauí"), 33: ("RJ", "Rio de Janeiro"), 24: ("RN", "Rio Grande do Norte"),
    43: ("RS", "Rio Grande do Sul"), 11: ("RO", "Rondônia"), 14: ("RR", "Roraima"), 42: ("SC", "Santa Catarina"),
    35: ("SP", "São Paulo"), 28: ("SE", "Sergipe"), 17: ("TO", "Tocantins"),
}
NOME_UF = {sigla: nome for sigla, nome in UFS.values()}

CAMBIOS = ("automatico", "manual", "qualquer")
VENDEDORES = ("Concessionária", "Loja", "Pessoa Física")  # nomes da faceta SellerType da API
CRITERIOS = ("parcela", "preco", "km", "uso", "fipe", "ano")


class ConfigInvalida(Exception):
    pass


def caminho():
    return Path(os.environ.get("RADAR_CONFIG") or ROOT / "config.json")


def carregar(arquivo=None):
    """Lê, valida e completa. Erro claro se o arquivo não existe (o usuário ainda não rodou /setup)."""
    arq = Path(arquivo) if arquivo else caminho()
    if not arq.exists():
        raise ConfigInvalida(f"{arq} não existe. Rode /setup no Claude Code para criar a configuração.")
    cfg = json.loads(arq.read_text())
    erros = validar(cfg)
    if erros:
        raise ConfigInvalida(f"{arq} com problemas:\n- " + "\n- ".join(erros))
    return completar(cfg)


def validar(cfg):
    erros = []
    local, busca, fin = cfg.get("local") or {}, cfg.get("busca") or {}, cfg.get("financiamento")
    for k in ("cidade", "uf", "lat", "lng", "raio_km"):
        if local.get(k) in (None, ""):
            erros.append(f"local.{k} faltando")
    if local.get("uf") and local["uf"] not in NOME_UF:
        erros.append(f"local.uf inválida: {local['uf']}")
    for k in ("preco_max", "km_max"):
        if not isinstance(busca.get(k), (int, float)) or busca[k] <= 0:
            erros.append(f"busca.{k} precisa ser um número positivo")
    if busca.get("cambio", "automatico") not in CAMBIOS:
        erros.append(f"busca.cambio precisa ser um de {CAMBIOS}")
    vend = busca.get("vendedores") or []
    if not vend or any(v not in VENDEDORES for v in vend):
        erros.append(f"busca.vendedores precisa ter um ou mais de {VENDEDORES}")
    geral = busca.get("geral")
    if geral is not None and not geral.get("ano_min"):
        erros.append("busca.geral.ano_min faltando (ou geral = null para não fazer busca geral)")
    alvos = cfg.get("alvos") or {}
    if not alvos and not geral:
        erros.append("sem alvos e sem busca geral: nada para buscar")
    for chave, a in alvos.items():
        if chave != slug_chave(chave):
            erros.append(f"alvos.{chave}: a chave precisa ser minúscula, sem acento nem espaço (ex.: t-cross)")
        if chave == "geral":
            erros.append("alvos.geral: nome reservado para a busca geral")
        for k in ("nome", "marca", "modelo", "ano_min"):
            if not a.get(k):
                erros.append(f"alvos.{chave}.{k} faltando")
    if fin is not None:
        for k in ("entrada", "taxa_mes", "tarifas", "prazos", "parcela_ideal", "parcela_limite"):
            if fin.get(k) is None:
                erros.append(f"financiamento.{k} faltando (ou financiamento = null para compra à vista)")
        if fin.get("taxa_mes") and fin["taxa_mes"] >= 0.2:
            erros.append("financiamento.taxa_mes é fração ao mês (1,66% = 0.0166)")
        if fin.get("parcela_ideal") and fin.get("parcela_limite") and fin["parcela_ideal"] > fin["parcela_limite"]:
            erros.append("financiamento.parcela_ideal maior que parcela_limite")
    elif not busca.get("preco_ideal"):
        erros.append("compra à vista: busca.preco_ideal faltando (preço que vale nota máxima)")
    score = cfg.get("score") or {}
    for k, regra in score.items():
        if k not in CRITERIOS:
            erros.append(f"score.{k}: critério desconhecido (use {CRITERIOS})")
        elif len(regra.get("curva") or []) < 1 or "peso" not in regra:
            erros.append(f"score.{k}: precisa de peso e curva [[valor, pontos], ...]")
    if not erros:
        total = sum(r["peso"] for r in completar(cfg)["score"].values())
        if total != 100:
            erros.append(f"pesos do score somam {total}, precisam somar 100")
    return erros


def score_padrao(cfg):
    """Régua padrão do score (0 a 100), derivada dos cortes. O config pode sobrescrever qualquer critério.

    Curva = pontos [valor, pontos] ligados por retas; antes do primeiro e depois do último, fica no extremo.
    """
    busca, fin = cfg["busca"], cfg.get("financiamento")
    km_max = busca["km_max"]
    anos = [a["ano_min"] for a in (cfg.get("alvos") or {}).values()]
    if busca.get("geral"):
        anos.append(busca["geral"]["ano_min"])
    ano_ref = min(anos)
    if fin:
        preco = {"parcela": {"peso": 10, "curva": [[fin["parcela_ideal"], 10], [fin["parcela_limite"], 2],
                                                   [round(fin["parcela_limite"] * 1.1), 0]]}}
    else:
        preco = {"preco": {"peso": 10, "curva": [[busca["preco_ideal"], 10], [busca["preco_max"], 0]]}}
    return {
        **preco,
        "km": {"peso": 25, "curva": [[int(round(km_max * 0.7, -3)), 25], [km_max, 7.5]]},
        "uso": {"peso": 20, "curva": [[10000, 20], [20000, 0]]},
        "fipe": {"peso": 25, "curva": [[90, 25], [100, 15], [110, 0]]},
        "ano": {"peso": 20, "curva": [[ano_ref, 8], [ano_ref + 3, 20]]},
    }


def completar(cfg):
    cfg = json.loads(json.dumps(cfg))  # cópia
    b = cfg["busca"]
    b.setdefault("cambio", "automatico")
    b.setdefault("marcas_proibidas", [])
    b.setdefault("modelos_recusados", [])
    b.setdefault("geral", None)
    cfg.setdefault("alvos", {})
    cfg.setdefault("financiamento", None)
    cfg.setdefault("relatorio", {}).setdefault("artifact_url", None)
    padrao = score_padrao(cfg)
    escolhido = cfg.get("score") or {}
    chave_preco = "parcela" if cfg["financiamento"] else "preco"
    cfg["score"] = {k: escolhido.get(k, v) for k, v in padrao.items() if k in (chave_preco, "km", "uso", "fipe", "ano")}
    if cfg["financiamento"]:
        cfg["financiamento"]["prazo_ref"] = max(cfg["financiamento"]["prazos"])
    return cfg


def slug_chave(texto):
    return "-".join(sem_acento(texto).lower().split())


def sem_acento(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def localizar(cidade, uf):
    """Acha o município no IBGE. Devolve dict com cidade (grafia oficial), uf, lat, lng; ou None."""
    alvo = sem_acento(cidade).lower().strip()
    with MUNICIPIOS.open(encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            sigla = UFS[int(linha["codigo_uf"])][0]
            if sigla == uf.upper() and sem_acento(linha["nome"]).lower() == alvo:
                return {"cidade": linha["nome"], "uf": sigla, "lat": float(linha["latitude"]), "lng": float(linha["longitude"])}
    return None


def tarifas_implicitas(preco, entrada, meses, valor_parcela, taxa_mes):
    """Quanto de tarifas e IOF o banco somou ao financiado, a partir de uma simulação real.

    Tabela Price: o saldo que gera essa parcela, menos o que sobra do preço depois da entrada.
    A CET não entra como taxa: ela já é o efeito dessas tarifas sobre a taxa nominal.
    """
    saldo = valor_parcela * (1 - (1 + taxa_mes) ** -meses) / taxa_mes
    return saldo - (preco - entrada)


def n(x):
    """Número no formato brasileiro, sem casas: 102000 -> "102.000"."""
    return f"{x:,.0f}".replace(",", ".")


def resumo(cfg):
    """Texto para o /setup mostrar: cortes, alvos, financiamento com preço máximo por parcela, régua do score."""
    from busca import parcela, preco_para_parcela  # import tardio: busca importa este módulo
    l, b, fin = cfg["local"], cfg["busca"], cfg["financiamento"]
    linhas = [
        f"Local: {l['cidade']}/{l['uf']} + {l['raio_km']} km",
        f"Cortes: até R$ {n(b['preco_max'])} · até {n(b['km_max'])} km · câmbio {b['cambio']} · {', '.join(b['vendedores'])}",
        "Busca geral: " + (f"carroceria {b['geral'].get('carroceria') or 'qualquer'}, ano-modelo {b['geral']['ano_min']}+" if b["geral"] else "não"),
        "Marcas proibidas: " + (", ".join(b["marcas_proibidas"]) or "nenhuma"),
        "Modelos recusados: " + (", ".join(b["modelos_recusados"]) or "nenhum"),
        "Alvos:",
        *[f"  - {a['nome']} ({k}): ano-modelo {a['ano_min']}+, exigir {a.get('exigir') or '—'}, excluir {a.get('excluir') or '—'}"
          for k, a in cfg["alvos"].items()],
    ]
    if fin:
        taxa = f"{fin['taxa_mes'] * 100:.2f}".replace(".", ",")
        linhas.append(f"Financiamento: entrada R$ {n(fin['entrada'])}, {taxa}% ao mês, R$ {n(fin['tarifas'])} de tarifas no financiado")
        for p in fin["prazos"]:
            refs = [f"parcela R$ {n(v)} → preço até R$ {n(preco_para_parcela(v, p, fin))}"
                    for v in (fin["parcela_ideal"], fin["parcela_limite"])]
            linhas.append(f"  {p}x: " + " · ".join(refs))
        linhas.append(f"  Preço máximo do corte (R$ {n(b['preco_max'])}) em {fin['prazo_ref']}x: parcela de R$ {n(parcela(b['preco_max'], fin['prazo_ref'], fin))}")
    else:
        linhas.append(f"Compra à vista: preço ideal até R$ {n(b['preco_ideal'])}")
    linhas.append("Score (0 a 100):")
    linhas += [f"  - {k}: peso {r['peso']}, curva {r['curva']}" for k, r in cfg["score"].items()]
    return "\n".join(linhas)


def main(argv):
    if len(argv) >= 3 and argv[0] == "cidade":
        achado = localizar(argv[1], argv[2])
        if not achado:
            print(f"Não achei {argv[1]}/{argv[2]} em {MUNICIPIOS.relative_to(ROOT)}. Conferir a grafia.", file=sys.stderr)
            return 1
        print(json.dumps(achado, ensure_ascii=False))
        return 0
    if len(argv) == 6 and argv[0] == "tarifas":
        preco, entrada, meses, valor, taxa = (float(x.replace(",", ".")) for x in argv[1:])
        print(f"Tarifas/IOF no financiado: R$ {n(tarifas_implicitas(preco, entrada, int(meses), valor, taxa))}")
        return 0
    if argv[:1] == ["validar"]:
        try:
            cfg = carregar()
        except ConfigInvalida as e:
            print(e, file=sys.stderr)
            return 1
        print(resumo(cfg))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main(sys.argv[1:]))
