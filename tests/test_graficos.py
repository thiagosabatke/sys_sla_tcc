"""Contagens e séries usadas pelos gráficos de chamados."""

from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.charts import (
    SITUACOES_CHAMADOS, resumir_por_situacao, resumir_evolucao_por_situacao,
    exibir_grafico_situacao,
)
from ui.report_scope import ESCOPO_BACKLOG, ESCOPO_TODOS, filtrar_escopo


class GraficosChamados(unittest.TestCase):
    def test_backlog_exclui_finalizados_e_mantem_resolvidos_aguardando_confirmacao(self):
        registros = [{"id": i, "status": estado} for i, estado in enumerate(
            ("Novo", "Em Andamento", "Em Espera", "Resolvido", "Cancelado", "Fechado"))]
        self.assertEqual([c["id"] for c in filtrar_escopo(registros, ESCOPO_BACKLOG)], [0, 1, 2, 3])
        self.assertEqual(len(filtrar_escopo(registros, ESCOPO_TODOS)), 6)
        self.assertEqual(len(registros), 6)

    def test_backlog_renderiza_apenas_serie_ativa(self):
        dados = resumir_por_situacao([{"status": "Novo"}], "Equipe", lambda _: "Suporte")
        with patch("ui.charts.st.bar_chart") as grafico, patch("ui.report_scope.st.caption") as legenda:
            exibir_grafico_situacao(dados, "Equipe", escopo=ESCOPO_BACKLOG)
        self.assertEqual(grafico.call_args.kwargs["y"], ["Ativos"])
        legenda.assert_called_with(f"**Escopo: {ESCOPO_BACKLOG}**")

    def test_cada_chamado_entra_uma_vez_e_resolvidos_continuam_ativos(self):
        chamados = [{"status": estado, "equipe": "Suporte"} for estado in
                    ("Novo", "Em Andamento", "Em Espera", "Resolvido", "Cancelado", "Fechado")]
        dados = resumir_por_situacao(chamados, "Equipe", lambda c: c["equipe"], grupos=["Redes"])
        self.assertEqual(list(dados.columns), ["Equipe", "Ativos", "Cancelados", "Fechados"])
        self.assertEqual(dados.to_dict("records"), [
            {"Equipe": "Suporte", "Ativos": 4, "Cancelados": 1, "Fechados": 1},
            {"Equipe": "Redes", "Ativos": 0, "Cancelados": 0, "Fechados": 0},
        ])
        self.assertEqual(int(dados[list(SITUACOES_CHAMADOS)].sum().sum()), len(chamados))

    def test_recorte_so_cancelados_mantem_demais_series_zeradas(self):
        dados = resumir_por_situacao([{"status": "Cancelado"}], "Motivo", lambda _: "Duplicado")
        self.assertEqual(dados.iloc[0].to_dict(),
                         {"Motivo": "Duplicado", "Ativos": 0, "Cancelados": 1, "Fechados": 0})

    def test_evolucao_preserva_dias_vazios_e_situacao_atual(self):
        chamados = [{"status": "Fechado", "criado_em": datetime(2026, 11, 1, 10)},
                    {"status": "Cancelado", "criado_em": datetime(2026, 11, 3, 11)},
                    {"status": "Resolvido", "criado_em": datetime(2026, 11, 3, 12)},
                    {"status": "Novo", "criado_em": None}]
        dados = resumir_evolucao_por_situacao(chamados)
        self.assertEqual(dados["Data"].dt.day.tolist(), [1, 2, 3])
        self.assertEqual(dados[list(SITUACOES_CHAMADOS)].values.tolist(), [[0, 0, 1], [0, 0, 0], [1, 1, 0]])
        self.assertTrue(resumir_evolucao_por_situacao([]).empty)

    def test_renderizacao_nao_soma_total_e_metricas_como_series(self):
        dados = resumir_por_situacao([{"status": "Fechado"}], "Analista", lambda _: "Ana")
        dados["Total"] = 1
        dados["Tempo médio"] = 10
        with patch("ui.charts.st.bar_chart") as grafico, patch("ui.report_scope.st.caption"):
            exibir_grafico_situacao(dados, "Analista")
        self.assertEqual(grafico.call_args.kwargs["y"], ["Ativos", "Cancelados", "Fechados"])
        self.assertEqual(grafico.call_args.kwargs["x_label"], "Analista")
        self.assertEqual(grafico.call_args.kwargs["y_label"], "Chamados")
        self.assertTrue(grafico.call_args.kwargs["stack"])


if __name__ == "__main__":
    unittest.main()
