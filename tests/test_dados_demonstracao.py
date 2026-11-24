"""Geração e remoção de demonstrações sem banco real."""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from demo_data import gerar_cenarios_demonstracao


SOLICITANTES = [
    {"id": 10, "nome": "Pessoa A", "nome_completo": "Pessoa A", "departamento": "Departamento A"},
    {"id": 20, "nome": "Pessoa B", "nome_completo": "Pessoa B", "departamento": "Departamento B"},
]
ANALISTAS = [{"id": 101, "nome_completo": "Suporte A"}, {"id": 102, "nome_completo": "Suporte B"}]
CONFIG = {"usar_horario_comercial": False, "limite_chamados_ativos_por_usuario": 5}
AGORA = datetime(2026, 11, 24, 18)


class CenariosDemonstracao(unittest.TestCase):
    def gerar(self, **alteracoes):
        argumentos = dict(solicitantes=SOLICITANTES, analistas=ANALISTAS, quantidade=120,
                          agora=AGORA, configuracao=CONFIG,
                          para_local=database.para_horario_local_sem_fuso, para_utc=database.para_utc,
                          marcador=database.MARCADOR_DADOS_DEMONSTRACAO_DASHBOARD)
        argumentos.update(alteracoes)
        return gerar_cenarios_demonstracao(**argumentos)

    def test_usa_cadastros_reais_e_nao_autoriza_conhecimento(self):
        cenarios = self.gerar()
        self.assertEqual(len(cenarios), 120)
        for cenario in cenarios:
            c = cenario["chamado"]
            solicitante = next(u for u in SOLICITANTES if u["id"] == c["usuario_id"])
            metadados = json.loads(c["metadados_ia"])
            self.assertEqual(metadados["departamento_demo"], solicitante["departamento"])
            self.assertTrue(metadados["sintetico"])
            self.assertEqual(metadados["origem"], database.MARCADOR_DADOS_DEMONSTRACAO_DASHBOARD)
            self.assertIn(c["analista_id"], (None, 101, 102))
            self.assertFalse(c["compartilhar_conhecimento"])
            self.assertIsNone(c["uso_ia_autorizado_em"])
        self.assertEqual({c["chamado"]["usuario_id"] for c in cenarios}, {10, 20})
        self.assertEqual(len({json.loads(c["chamado"]["metadados_ia"])["lote"] for c in cenarios}), 1)

    def test_inclui_estados_categorias_datas_e_avaliacoes_coerentes(self):
        cenarios = self.gerar()
        self.assertEqual({c["chamado"]["status"] for c in cenarios}, set(database.TRANSICOES_STATUS))
        self.assertEqual({c["chamado"]["categoria"] for c in cenarios}, database.CATEGORIAS_VALIDAS)
        self.assertEqual({c["chamado"]["urgencia"] for c in cenarios}, database.URGENCIAS_VALIDAS)
        self.assertLess(min(c["chamado"]["criado_em"] for c in cenarios), datetime(2026, 9, 1))
        for cenario in cenarios:
            c = cenario["chamado"]
            for campo in ("primeira_resposta_em", "resolvido_em", "pausado_em", "atualizado_em"):
                if c[campo] is not None:
                    self.assertLessEqual(c["criado_em"], c[campo])
                    self.assertLessEqual(c[campo], AGORA)
            for _, _, _, data in cenario["mensagens"] + cenario["eventos"]:
                self.assertLessEqual(c["criado_em"], data)
                self.assertLessEqual(data, AGORA)
            if c["status"] in {"Novo", "Cancelado"}:
                self.assertIsNone(c["analista_id"])
                self.assertIsNone(c["primeira_resposta_em"])
            if c["status"] == "Em Espera":
                self.assertIsNotNone(c["pausado_em"])
            if c["status"] == "Fechado":
                self.assertIn(cenario["nota"], range(1, 6))
                self.assertIsNotNone(c["diagnostico_final"])
                self.assertLessEqual(c["primeira_resposta_em"], c["resolvido_em"])
            else:
                self.assertIsNone(cenario["nota"])

    def test_prazos_usam_configuracao_vigente_e_fuso(self):
        config = {**CONFIG, "usar_horario_comercial": True}
        for cenario in self.gerar(configuracao=config):
            c = cenario["chamado"]
            prazos = database.sla.calcular_prazos(database.para_horario_local_sem_fuso(c["criado_em"]), c["urgencia"], config)
            self.assertEqual((c["prazo_resposta"], c["prazo_resolucao"]), tuple(database.para_utc(p) for p in prazos))

    def test_preserva_vaga_para_chamado_real_sem_exceder_limite(self):
        cenarios = self.gerar(ativos_por_usuario={10: 4, 20: 3})
        ativos = Counter(c["chamado"]["usuario_id"] for c in cenarios
                         if c["chamado"]["status"] not in {"Fechado", "Cancelado"})
        self.assertEqual(ativos[10], 0)
        self.assertEqual(ativos[20], 1)
        self.assertEqual(len(cenarios), 120)

    def test_sem_participantes_nao_inventa_contas(self):
        for alteracoes in ({"solicitantes": []}, {"analistas": []}):
            with self.subTest(alteracoes=alteracoes), self.assertRaises(ValueError):
                self.gerar(**alteracoes)


class PersistenciaDemonstracao(unittest.TestCase):
    def setUp(self):
        self.participantes_reais = database._participantes_demonstracao
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value
        self.cursor.fetchone.return_value = {"total": 12}
        self.cursor.fetchall.return_value = []
        self.cursor.lastrowid = 501
        for nome, valor in (("exigir_permissao", None), ("usuario_eh_administrador", True),
                            ("obter_configuracao_sla", CONFIG), ("conectar", self.conn),
                            ("_participantes_demonstracao", (SOLICITANTES, ANALISTAS))):
            p = patch.object(database, nome, return_value=valor)
            p.start()
            self.addCleanup(p.stop)

    def test_adiciona_lote_sem_alterar_cadastros_ou_apagar_existentes(self):
        self.assertEqual(database.inserir_dados_demonstracao_dashboard(1, quantidade=24), 24)
        comandos = [chamada.args[0] for chamada in self.cursor.execute.call_args_list]
        self.assertEqual(sum(q.startswith("INSERT INTO chamados") for q in comandos), 24)
        self.assertFalse(any(q.startswith(("UPDATE usuarios", "INSERT INTO usuarios", "DELETE")) for q in comandos))
        self.conn.commit.assert_called_once()
        self.conn.rollback.assert_not_called()

    def test_falha_intermediaria_desfaz_lote_completo(self):
        def executar(consulta, *_):
            if "INSERT INTO mensagens_chamado" in consulta:
                raise RuntimeError("Falha simulada")
        self.cursor.execute.side_effect = executar
        with self.assertRaises(RuntimeError):
            database.inserir_dados_demonstracao_dashboard(1, 12)
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_recriar_valida_participantes_antes_de_remover(self):
        with patch.object(database, "_participantes_demonstracao", return_value=([], ANALISTAS)):
            with self.assertRaises(ValueError):
                database.recriar_dados_demonstracao_dashboard(1)
        self.assertFalse(any(c.args[0].startswith("DELETE") for c in self.cursor.execute.call_args_list))
        self.conn.commit.assert_not_called()
        self.conn.rollback.assert_called_once()

    def test_remocao_exige_marcador_e_flag_sintetico(self):
        self.cursor.rowcount = 24
        self.assertEqual(database.remover_dados_demonstracao_dashboard(1), 24)
        consulta, parametros = self.cursor.execute.call_args_list[0].args
        self.assertIn("DELETE FROM chamados", consulta)
        self.assertIn("JSON_EXTRACT(metadados_ia, '$.sintetico') = TRUE", consulta)
        self.assertEqual(parametros, (database.MARCADOR_DADOS_DEMONSTRACAO_DASHBOARD,))
        self.conn.commit.assert_called_once()

    def test_somente_administrador_pode_inserir_contar_ou_remover(self):
        with patch.object(database, "usuario_eh_administrador", return_value=False):
            for operacao in (database.inserir_dados_demonstracao_dashboard, database.remover_dados_demonstracao_dashboard,
                             database.contar_dados_demonstracao_dashboard, database.recriar_dados_demonstracao_dashboard):
                with self.subTest(operacao=operacao.__name__), self.assertRaises(PermissionError):
                    operacao(1)
        database.conectar.assert_not_called()

    def test_quantidade_invalida_nao_abre_transacao(self):
        for quantidade in (0, 11, 501, True, 12.5):
            with self.subTest(quantidade=quantidade), self.assertRaises(ValueError):
                database.inserir_dados_demonstracao_dashboard(1, quantidade)
        database.conectar.assert_not_called()

    def test_participantes_sao_escolhidos_por_permissoes_efetivas(self):
        self.cursor.fetchall.return_value = [
            {"id": 1, "nome": "Admin", "perfil_chave": "administrador"},
            {"id": 2, "nome": "Suporte", "perfil_chave": "perfil_personalizado"},
            {"id": 3, "nome": "Solicitante", "perfil_chave": "outro_perfil"},
        ]
        permissoes = {1: {p[0] for p in database.PERMISSOES_PADRAO_RBAC},
                      2: {"chamados.visualizar_fila", "chamados.assumir", "chamados.responder_atribuidos", "chamados.registrar_resolucao"},
                      3: {"chamados.abrir", "chamados.visualizar_proprios"}}
        with patch.object(database, "permissoes_usuario", side_effect=lambda id: permissoes[id]):
            solicitantes, analistas = self.participantes_reais(self.cursor)
        self.assertEqual([u["id"] for u in solicitantes], [3])
        self.assertEqual([u["id"] for u in analistas], [2])


if __name__ == "__main__":
    unittest.main()
