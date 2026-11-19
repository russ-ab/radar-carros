import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402

EXEMPLO = json.loads((ROOT / "config.exemplo.json").read_text())


def com(**caminhos):
    """Cópia do exemplo com valores trocados: com(**{"busca.km_max": 0})."""
    cfg = copy.deepcopy(EXEMPLO)
    for chave, valor in caminhos.items():
        *pais, ult = chave.split(".")
        alvo = cfg
        for p in pais:
            alvo = alvo[p]
        alvo[ult] = valor
    return cfg


class TestValidar(unittest.TestCase):
    def test_exemplo_valido(self):
        self.assertEqual(config.validar(EXEMPLO), [])

    def test_local_incompleto(self):
        self.assertIn("local.lat faltando", config.validar(com(**{"local.lat": None})))

    def test_taxa_em_porcentagem(self):
        erros = config.validar(com(**{"financiamento.taxa_mes": 1.66}))
        self.assertTrue(any("fração" in e for e in erros))

    def test_nada_para_buscar(self):
        erros = config.validar(com(alvos={}, **{"busca.geral": None}))
        self.assertTrue(any("nada para buscar" in e for e in erros))

    def test_chave_de_alvo(self):
        cfg = com()
        cfg["alvos"]["T Cross"] = cfg["alvos"]["kicks"]
        self.assertTrue(any("minúscula" in e for e in config.validar(cfg)))

    def test_vendedor_desconhecido(self):
        self.assertTrue(config.validar(com(**{"busca.vendedores": ["Leilão"]})))

    def test_a_vista_exige_preco_ideal(self):
        erros = config.validar(com(financiamento=None))
        self.assertTrue(any("preco_ideal" in e for e in erros))
        self.assertEqual(config.validar(com(financiamento=None, **{"busca.preco_ideal": 80000})), [])

    def test_pesos_precisam_somar_100(self):
        erros = config.validar(com(score={"km": {"peso": 40, "curva": [[35000, 40], [50000, 10]]}}))
        self.assertTrue(any("somam 115" in e for e in erros))


class TestCompletar(unittest.TestCase):
    def test_padroes(self):
        cfg = config.completar(EXEMPLO)
        self.assertEqual(list(cfg["score"]), ["parcela", "km", "uso", "fipe", "ano"])
        self.assertEqual(sum(r["peso"] for r in cfg["score"].values()), 100)
        self.assertEqual(cfg["financiamento"]["prazo_ref"], 48)
        self.assertEqual(cfg["score"]["km"]["curva"], [[35000, 25], [50000, 7.5]])
        self.assertEqual(cfg["score"]["ano"]["curva"], [[2021, 8], [2024, 20]])
        self.assertIsNone(cfg["relatorio"]["artifact_url"])

    def test_score_sobrescrito(self):
        regra = {"peso": 25, "curva": [[20000, 25], [50000, 0]]}
        self.assertEqual(config.completar(com(score={"km": regra}))["score"]["km"], regra)

    def test_a_vista_troca_parcela_por_preco(self):
        cfg = config.completar(com(financiamento=None, **{"busca.preco_ideal": 80000}))
        self.assertIn("preco", cfg["score"])
        self.assertNotIn("parcela", cfg["score"])
        self.assertEqual(cfg["score"]["preco"]["curva"], [[80000, 10], [100000, 0]])

    def test_nao_altera_o_original(self):
        original = copy.deepcopy(EXEMPLO)
        config.completar(EXEMPLO)
        self.assertEqual(EXEMPLO, original)


class TestCarregar(unittest.TestCase):
    def test_arquivo_ausente_manda_rodar_setup(self):
        with self.assertRaises(config.ConfigInvalida) as e:
            config.carregar(ROOT / "nao-existe.json")
        self.assertIn("/setup", str(e.exception))

    def test_invalido_lista_os_erros(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(com(**{"busca.km_max": 0}), fh)
        with self.assertRaises(config.ConfigInvalida) as e:
            config.carregar(fh.name)
        self.assertIn("busca.km_max", str(e.exception))
        Path(fh.name).unlink()


class TestLocalizar(unittest.TestCase):
    def test_acha_sem_acento_e_minusculo(self):
        self.assertEqual(config.localizar("sao jose dos campos", "sp")["cidade"], "São José dos Campos")

    def test_uf_diferencia_homonimos(self):
        # Há "Bom Jesus" em vários estados
        self.assertEqual(config.localizar("Bom Jesus", "RS")["uf"], "RS")

    def test_nao_achou(self):
        self.assertIsNone(config.localizar("Cidade Inventada", "SP"))


class TestTarifas(unittest.TestCase):
    def test_simulacao_real(self):
        # Simulação de um banco: R$ 95 mil, R$ 50 mil de entrada, 1,66% a.m., 48x de R$ 1.452,20
        self.assertAlmostEqual(config.tarifas_implicitas(95000, 50000, 48, 1452.20, 0.0166), 2789, delta=1)

    def test_sem_tarifas(self):
        import busca
        fin = {"entrada": 20000, "tarifas": 0, "taxa_mes": 0.015}
        p = busca.parcela(60000, 36, fin)
        self.assertAlmostEqual(config.tarifas_implicitas(60000, 20000, 36, p, 0.015), 0, places=6)


class TestResumo(unittest.TestCase):
    def test_traz_precos_de_referencia(self):
        texto = config.resumo(config.completar(EXEMPLO))
        self.assertIn("Campinas/SP + 50 km", texto)
        self.assertIn("48x: parcela R$ 1.300 → preço até R$ 89.9", texto)
        self.assertIn("Nissan Kicks (kicks)", texto)
        self.assertIn("Concessionária, Loja", texto)
        self.assertIn("1,66% ao mês", texto)


if __name__ == "__main__":
    unittest.main()
