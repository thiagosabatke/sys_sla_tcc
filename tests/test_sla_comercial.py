from datetime import datetime
import sys
from pathlib import Path
import unittest

# Permite executar este arquivo diretamente, além do unittest discovery/pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sla


CONFIGURACAO = {
    "dias_uteis": [0, 1, 2, 3, 4],
    "hora_inicio": "08:00",
    "hora_fim": "18:00",
    "matriz": sla.MATRIZ_SLA_MINUTOS,
    "limiar_risco": 0.8,
    "horas_fechamento_automatico": 72,
}


class TestesSlaComercial(unittest.TestCase):
    def test_prazo_avanca_para_proximo_dia_util(self):
        criado = datetime(2026, 10, 16, 17, 30)  # sexta-feira
        prazo, _ = sla.calcular_prazos(criado, "Alta", CONFIGURACAO)
        self.assertEqual(prazo, datetime(2026, 10, 19, 8, 30))

    def test_fim_de_semana_nao_consume_sla(self):
        inicio = datetime(2026, 10, 16, 17, 0)
        fim = datetime(2026, 10, 19, 9, 0)
        self.assertEqual(sla.minutos_uteis_entre(inicio, fim, CONFIGURACAO), 120)

    def test_resolucao_apos_prazo_e_violada(self):
        criado = datetime(2026, 10, 13, 8, 0)
        prazo, _ = sla.calcular_prazos(criado, "Alta", CONFIGURACAO)
        estado = sla.avaliar_metrica(criado, prazo, datetime(2026, 10, 13, 9, 1), None, 0, CONFIGURACAO)
        self.assertEqual(estado["status"], "Violado")

    def test_espera_paused_sla(self):
        criado = datetime(2026, 10, 13, 8, 0)
        prazo, _ = sla.calcular_prazos(criado, "Alta", CONFIGURACAO)
        estado = sla.avaliar_metrica(criado, prazo, None, datetime(2026, 10, 13, 8, 10), 0, CONFIGURACAO, datetime(2026, 10, 13, 12, 0))
        self.assertEqual(estado["status"], "Pausado")


if __name__ == "__main__":
    unittest.main()
