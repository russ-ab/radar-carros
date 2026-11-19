import copy
import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import busca as b  # noqa: E402
import config  # noqa: E402

# O exemplo do repositório é a configuração de teste: se ele quebrar, os testes avisam.
CFG = config.carregar(ROOT / "config.exemplo.json")
FIN = CFG["financiamento"]


def cfg_com(**mudancas):
    """Cópia do exemplo com chaves de `busca` trocadas, já completada."""
    bruto = copy.deepcopy(CFG)
    bruto.pop("score")
    bruto["busca"].update(mudancas)
    return config.completar(bruto)


def a_vista():
    bruto = copy.deepcopy(CFG)
    bruto.pop("score")
    bruto["financiamento"] = None
    bruto["busca"]["preco_ideal"] = 80000
    return config.completar(bruto)


class TestParcela(unittest.TestCase):
    # Tabela Price: entrada 50 mil, +2.800 de tarifas no financiado, 1,66% a.m. (config.exemplo.json)
    def test_valores(self):
        self.assertAlmostEqual(b.parcela(90000, 48, FIN), 1300.60, places=2)
        self.assertAlmostEqual(b.parcela(90000, 36, FIN), 1588.86, places=2)

    def test_inverso(self):
        for meses in (36, 48):
            preco = b.preco_para_parcela(1300, meses, FIN)
            self.assertAlmostEqual(b.parcela(preco, meses, FIN), 1300, places=6)

    def test_preco_abaixo_da_entrada(self):
        self.assertEqual(b.parcela(40000, 48, FIN), 0.0)


class TestFaixa(unittest.TestCase):
    def test_faixas(self):
        self.assertEqual(b.faixa(1300, FIN), "ideal")
        self.assertEqual(b.faixa(1300.01, FIN), "no limite")
        self.assertEqual(b.faixa(1500, FIN), "no limite")
        self.assertEqual(b.faixa(1500.01, FIN), "acima")


class TestKmPorAno(unittest.TestCase):
    def test_idade_minima_um_ano(self):
        self.assertEqual(b.km_por_ano(12000, 2026, 2026), 12000)

    def test_media(self):
        self.assertEqual(b.km_por_ano(46000, 2022, 2026), 11500)


class TestCambio(unittest.TestCase):
    def test_automatico_aceita_cvt_e_corta_manual(self):
        # A Webmotors rotula alguns automáticos como "CVT", não "Automática"
        self.assertTrue(b.cambio_aceito("1.6 ADVANCE XTRONIC", "CVT", "automatico"))
        self.assertTrue(b.cambio_aceito("1.0 TURBO LT AUTOMÁTICO", "Automática", "automatico"))
        self.assertFalse(b.cambio_aceito("1.0 TURBO LT", "Manual", "automatico"))
        self.assertFalse(b.cambio_aceito("1.0 TURBO LT MANUAL", None, "automatico"))

    def test_manual(self):
        self.assertTrue(b.cambio_aceito("1.0 TURBO LT", "Manual", "manual"))
        self.assertFalse(b.cambio_aceito("1.6 ADVANCE XTRONIC", "CVT", "manual"))

    def test_qualquer(self):
        self.assertTrue(b.cambio_aceito("1.0 TURBO LT", "Manual", "qualquer"))
        self.assertTrue(b.cambio_aceito("1.6 ADVANCE XTRONIC", "CVT", "qualquer"))


class TestVersaoAceita(unittest.TestCase):
    TRACKER = CFG["alvos"]["tracker"]
    KICKS = CFG["alvos"]["kicks"]

    def test_exigir(self):
        self.assertTrue(b.versao_aceita("1.0 TURBO FLEX LT AUTOMÁTICO", self.TRACKER))
        self.assertTrue(b.versao_aceita("1.2 TURBO FLEX PREMIER AUTOMÁTICO", self.TRACKER))
        self.assertFalse(b.versao_aceita("1.0 TURBO FLEX AUTOMÁTICO", self.TRACKER))

    def test_excluir(self):
        self.assertTrue(b.versao_aceita("1.6 16V FLEXSTART ADVANCE PLUS XTRONIC", self.KICKS))
        self.assertFalse(b.versao_aceita("1.6 16V FLEXSTART SENSE XTRONIC", self.KICKS))

    def test_token_com_acento_no_config(self):
        self.assertTrue(b.versao_aceita("1.0 TSI HIGHLINE", {"exigir": ["highline"]}))
        self.assertFalse(b.versao_aceita("1.5 SEDÃ ATTITUDE", {"excluir": ["Attitúde"]}))


class TestVersaoCurta(unittest.TestCase):
    def test_tira_motor_e_cambio(self):
        self.assertEqual(b.versao_curta("1.0 TURBO FLEX LT AUTOMÁTICO"), "LT")
        self.assertEqual(b.versao_curta("1.6 16V FLEXSTART ADVANCE PLUS XTRONIC"), "ADVANCE PLUS")
        self.assertEqual(b.versao_curta("1.0 200 TSI COMFORTLINE AUTOMÁTICO"), "COMFORTLINE")
        self.assertEqual(b.versao_curta("1.4 250 TSI TOTAL FLEX HIGHLINE AUTOMÁTICO"), "HIGHLINE")


class TestCurva(unittest.TestCase):
    PONTOS = [[90, 25], [100, 15], [110, 0]]

    def test_extremos_travados(self):
        self.assertEqual(b.curva(50, self.PONTOS), 25)
        self.assertEqual(b.curva(150, self.PONTOS), 0)

    def test_interpola(self):
        self.assertEqual(b.curva(95, self.PONTOS), 20)
        self.assertEqual(b.curva(105, self.PONTOS), 7.5)

    def test_um_ponto_so(self):
        self.assertEqual(b.curva(10, [[5, 3]]), 3)


class TestClassificar(unittest.TestCase):
    def test_manual_cortado(self):
        self.assertIsNone(b.classificar("VOLKSWAGEN", "T-CROSS", "1.0 200 TSI MANUAL", "Manual", 2022, CFG))

    def test_cambio_qualquer_nao_corta(self):
        self.assertEqual(b.classificar("VOLKSWAGEN", "T-CROSS", "1.0 200 TSI", "Manual", 2022, cfg_com(cambio="qualquer")),
                         ("t-cross", None))

    def test_alvo_aceito(self):
        self.assertEqual(b.classificar("CHEVROLET", "TRACKER", "1.0 TURBO FLEX LT AUTOMÁTICO", "Automática", 2022, CFG),
                         ("tracker", None))

    def test_modelo_com_nome_composto_casa_por_token(self):
        # "KICKS PLAY" (1ª geração renomeada) também é o Kicks dos alvos
        self.assertEqual(b.classificar("NISSAN", "KICKS PLAY", "1.6 ADVANCE PLUS XTRONIC", "CVT", 2025, CFG), ("kicks", None))

    def test_versao_excluida_ignorada(self):
        self.assertEqual(b.classificar("NISSAN", "KICKS", "1.6 16V FLEXSTART SENSE XTRONIC", "CVT", 2023, CFG),
                         ("kicks", "versão abaixo das aprovadas"))

    def test_ano_abaixo_do_minimo_ignorado(self):
        chave, motivo = b.classificar("NISSAN", "KICKS", "1.6 16V FLEXSTART ADVANCE XTRONIC", "CVT", 2021, CFG)
        self.assertEqual(chave, "kicks")
        self.assertIn("2022", motivo)

    def test_marca_proibida_ignorada(self):
        self.assertEqual(b.classificar("RENAULT", "DUSTER", "1.6 ICONIC CVT", "CVT", 2022, CFG),
                         ("duster", "marca proibida"))

    def test_marca_proibida_com_acento(self):
        cfg = cfg_com(marcas_proibidas=["CITROËN"])
        self.assertEqual(b.classificar("CITROËN", "C4 CACTUS", "1.6 FEEL AUTOMÁTICO", "Automática", 2022, cfg),
                         ("c4-cactus", "marca proibida"))

    def test_modelo_recusado_ignorado(self):
        self.assertEqual(b.classificar("JEEP", "RENEGADE", "1.3 T270 TURBO FLEX SPORT AT6", "Automática", 2023, CFG),
                         ("renegade", "modelo recusado"))
        # Outro modelo da mesma marca continua candidato
        self.assertEqual(b.classificar("JEEP", "COMPASS", "2.0 16V FLEX LONGITUDE AUTOMÁTICO", "Automática", 2021, CFG),
                         ("compass", None))

    def test_fora_dos_alvos_e_candidato(self):
        self.assertEqual(b.classificar("VOLKSWAGEN", "T-CROSS", "1.0 200 TSI COMFORTLINE AUTOMÁTICO", "Automática", 2022, CFG),
                         ("t-cross", None))


class TestPontuar(unittest.TestCase):
    def test_carro_perfeito_vale_100(self):
        total, partes = b.pontuar(85000, 25000, 10000, 90, 2024, CFG)
        self.assertEqual(total, 100)
        self.assertEqual(sum(partes.values()), 100)

    def test_ano_modelo(self):
        anos = {a: b.pontuar(85000, 30000, 8000, 95, a, CFG)[1]["ano"] for a in (2025, 2024, 2023, 2022, 2021, 2020)}
        self.assertEqual(anos, {2025: 20, 2024: 20, 2023: 16, 2022: 12, 2021: 8, 2020: 8})

    def test_parcela(self):
        ideal = b.preco_para_parcela(1300, 48, FIN)
        limite = b.preco_para_parcela(1500, 48, FIN)
        self.assertEqual(b.pontuar(ideal - 1, 30000, 8000, 95, 2023, CFG)[1]["parcela"], 10)
        self.assertAlmostEqual(b.pontuar(limite, 30000, 8000, 95, 2023, CFG)[1]["parcela"], 2, delta=0.1)
        self.assertEqual(b.pontuar(limite + 10000, 30000, 8000, 95, 2023, CFG)[1]["parcela"], 0)

    def test_km_e_fipe(self):
        _, p = b.pontuar(85000, 50000, 20000, 110, 2021, CFG)
        self.assertEqual((p["km"], p["uso"], p["fipe"]), (7.5, 0, 0))
        _, r = b.pontuar(85000, 30000, 8000, 90, 2024, CFG)
        self.assertEqual((r["km"], r["uso"], r["fipe"]), (25, 20, 25))

    def test_sem_fipe_e_neutro(self):
        self.assertEqual(b.pontuar(85000, 30000, 8000, None, 2024, CFG)[1]["fipe"], 15)

    def test_modelo_nao_pontua(self):
        # A preferência de modelo fica na análise, não no score
        self.assertNotIn("modelo", b.pontuar(85000, 30000, 8000, 95, 2023, CFG)[1])

    def test_a_vista_pontua_preco(self):
        cfg = a_vista()
        _, partes = b.pontuar(80000, 30000, 8000, 95, 2023, cfg)
        self.assertNotIn("parcela", partes)
        self.assertEqual(partes["preco"], 10)
        self.assertEqual(b.pontuar(100000, 30000, 8000, 95, 2023, cfg)[1]["preco"], 0)


class TestUrl(unittest.TestCase):
    @staticmethod
    def decodificar(url):
        return urllib.parse.unquote(urllib.parse.unquote(url))  # o parâmetro url vai codificado duas vezes

    def test_busca_geral_sem_marca_com_carroceria(self):
        url = self.decodificar(b.montar_url(CFG["busca"]["geral"], 1, CFG))
        self.assertNotIn("marca1", url)
        self.assertIn("carroceria=Utilitário esportivo", url)
        self.assertIn("anode=2021", url)

    def test_busca_por_modelo(self):
        url = self.decodificar(b.montar_url(CFG["alvos"]["kicks"], 1, CFG))
        self.assertIn("marca1=NISSAN", url)
        self.assertIn("modelo1=KICKS", url)
        self.assertNotIn("carroceria", url)

    def test_local_e_cortes_do_config(self):
        url = self.decodificar(b.montar_url(CFG["alvos"]["kicks"], 2, CFG))
        self.assertIn("/carros-usados/sp-campinas?", url)
        self.assertIn("localizacao=-22.9053,-47.0659x50km", url)
        self.assertIn("estadocidade=São Paulo-Campinas", url)
        self.assertIn("precoate=100000", url)
        self.assertIn("kmate=50000", url)
        self.assertIn("anunciante=Concessionária|Loja", url)
        self.assertIn("actualPage=2", url)

    def test_so_marca(self):
        url = self.decodificar(b.montar_url({"marca": "NISSAN", "ano_min": 2020}, 1, CFG))
        self.assertIn("marca1=NISSAN", url)
        self.assertNotIn("modelo1", url)

    def test_geral_sem_carroceria(self):
        url = self.decodificar(b.montar_url({"carroceria": None, "ano_min": 2020}, 1, CFG))
        self.assertNotIn("carroceria", url)

    def test_buscas(self):
        self.assertEqual(list(b.buscas(CFG)), ["kicks", "tracker", "creta", "geral"])
        self.assertEqual(list(b.buscas(cfg_com(geral=None))), ["kicks", "tracker", "creta"])


class TestLocadora(unittest.TestCase):
    def test_reconhece(self):
        self.assertTrue(b.eh_locadora("Unidas Seminovos Americana"))
        self.assertTrue(b.eh_locadora("LOCALIZA SEMINOVOS"))
        self.assertFalse(b.eh_locadora("Automec Itu"))
        self.assertFalse(b.eh_locadora(None))


class TestRelatorio(unittest.TestCase):
    BASE = {"modelo": "kicks", "nome": "Nissan Kicks", "versao": "X", "ano": "2023/2023", "km": 1, "km_ano": 1,
            "preco": 90000, "fipe_pct": 90, "parcelas": {"36": 1585, "48": 1301}, "faixa": "no limite", "cidade": "C",
            "loja": "L", "locadora": False, "link": "u"}

    def snaps(self):
        snap = {"data": "d2", "descartados_pelo_filtro": {}, "anuncios": {
            "1": {**self.BASE, "id": 1, "ignorado": None}, "2": {**self.BASE, "id": 2, "ignorado": "marca proibida"}}}
        return snap, {"data": "d1", "anuncios": {"1": {**self.BASE, "id": 1}}}

    def test_ignorados_fora_do_diff(self):
        rel = b.gerar_relatorio(*self.snaps(), CFG)
        self.assertIn("## 🆕 Novos (0)", rel)
        self.assertIn("## 🚫 Ignorados (1)", rel)
        self.assertIn("Parcela 36x / 48x", rel)
        self.assertIn("1.585 / 1.301", rel)

    def test_a_vista_sem_coluna_de_parcela(self):
        rel = b.gerar_relatorio(*self.snaps(), a_vista())
        self.assertNotIn("Parcela", rel)

    def test_diff(self):
        anterior = {"1": {"id": 1, "preco": 90000}, "2": {"id": 2, "preco": 88000}, "3": {"id": 3, "preco": 85000}}
        atual = {"1": {"id": 1, "preco": 87000}, "2": {"id": 2, "preco": 88000}, "4": {"id": 4, "preco": 89000}}
        d = b.comparar(anterior, atual)
        self.assertEqual([a["id"] for a in d["novos"]], [4])
        self.assertEqual([a["id"] for a in d["sumiram"]], [3])
        self.assertEqual([(a["id"], a["preco_anterior"], a["preco"]) for a in d["mudou_preco"]], [(1, 90000, 87000)])


class TestSlug(unittest.TestCase):
    def test_formato_do_site(self):
        self.assertEqual(b.slug("1.0 TURBO FLEX LT AUTOMÁTICO"), "10-turbo-flex-lt-automatico")


if __name__ == "__main__":
    unittest.main()
