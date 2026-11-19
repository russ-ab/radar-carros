import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import sondar  # noqa: E402


class TestFacetas(unittest.TestCase):
    def test_acha_grupos_aninhados(self):
        # Formato de FiltersGrouped (showMenu=true): grupos dentro de grupos
        d = {"FiltersGrouped": [
            {"name": "MostUsed", "items": [{"name": "Make", "items": [{"name": "NISSAN", "count": 12}]}]},
            {"name": "StyleStructure", "items": [{"name": "BodyType", "items": [
                {"name": "Utilitário esportivo", "count": 90}, {"name": "Hatch", "count": 40}]}]},
        ]}
        f = sondar.facetas(d)
        self.assertEqual(f["Make"], [("NISSAN", 12)])
        self.assertEqual(f["BodyType"], [("Utilitário esportivo", 90), ("Hatch", 40)])

    def test_formato_plano(self):
        d = {"Filters": [{"name": "SellerType", "items": [{"name": "Pessoa Física", "count": 342}]},
                         {"name": "BodyType", "items": [{"name": "Sedã", "count": 353}]}]}
        f = sondar.facetas(d)
        self.assertEqual(f["SellerType"], [("Pessoa Física", 342)])
        self.assertEqual(f["BodyType"], [("Sedã", 353)])

    def test_sem_menu(self):
        self.assertEqual(sondar.facetas({}), {})


if __name__ == "__main__":
    unittest.main()
