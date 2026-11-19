import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import relatorio_html as r  # noqa: E402


class TestQtdFotos(unittest.TestCase):
    def test_degrau_padrao(self):
        d = r.DEGRAUS[0]
        self.assertIsNone(r.qtd_fotos("observar", False, d))     # todas
        self.assertEqual(r.qtd_fotos("descartar", False, d), 1)  # só a capa
        self.assertEqual(r.qtd_fotos("ignorado", False, d), 1)

    def test_fora_do_ranking_perde_a_capa_antes_dos_candidatos_perderem_fotos(self):
        d = r.DEGRAUS[1]
        self.assertEqual(r.qtd_fotos("ignorado", False, d), 0)
        self.assertIsNone(r.qtd_fotos("observar", False, d))

    def test_destaque_sempre_com_todas(self):
        for d in r.DEGRAUS:
            self.assertIsNone(r.qtd_fotos("visitar", True, d))

    def test_ultimo_degrau_enxuga_tudo(self):
        d = r.DEGRAUS[-1]
        self.assertEqual(r.qtd_fotos("sem análise", False, d), 1)
        self.assertEqual(r.qtd_fotos("descartar", False, d), 0)
        self.assertTrue(d["leve"])

    def test_fatiar_com_none_pega_todas(self):
        self.assertEqual(["a", "b", "c"][:r.qtd_fotos("observar", False, r.DEGRAUS[0])], ["a", "b", "c"])


class TestPrimeiroQueCabe(unittest.TestCase):
    def test_para_no_primeiro_que_cabe(self):
        tamanhos = iter([20, 14, 1])
        medidos = []
        degrau, tam = r.primeiro_que_cabe(r.DEGRAUS, lambda d: medidos.append(d) or next(tamanhos), limite=15)
        self.assertIs(degrau, r.DEGRAUS[1])
        self.assertEqual((tam, len(medidos)), (14, 2))

    def test_erro_claro_se_nada_cabe(self):
        with self.assertRaises(ValueError) as e:
            r.primeiro_que_cabe(r.DEGRAUS, lambda d: 99, limite=15)
        self.assertIn("files", str(e.exception))


if __name__ == "__main__":
    unittest.main()
