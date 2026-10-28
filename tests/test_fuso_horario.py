from datetime import datetime
import unittest

import database
import sla


class TestFusoHorario(unittest.TestCase):
    def test_converte_utc_para_horario_de_sao_paulo(self):
        utc = datetime(2026, 10, 27, 3, 15)
        self.assertEqual(
            database.para_horario_local_sem_fuso(utc),
            datetime(2026, 10, 27, 0, 15),
        )

    def test_converte_horario_local_para_utc_na_persistencia(self):
        local = datetime(2026, 10, 27, 0, 15)
        self.assertEqual(database.para_utc(local), datetime(2026, 10, 27, 3, 15))

    def test_prazo_comercial_e_calculado_na_hora_local(self):
        configuracao = {"usar_horario_comercial": True, "dias_uteis": [0, 1, 2, 3, 4],
                        "hora_inicio": "08:00", "hora_fim": "18:00"}
        criado_local = database.para_horario_local_sem_fuso(datetime(2026, 10, 16, 20, 30))

        prazo, _ = sla.calcular_prazos(criado_local, "Alta", configuracao)

        self.assertEqual(prazo, datetime(2026, 10, 19, 8, 30))
