"""Regressões de navegação, indicadores e telas, sem banco ou chamadas à IA."""

from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.navigation import destino_inicial, paginas_autorizadas
from core.session import inicializar_sessao, limpar_sessao
from ui.admin_dashboard import (
    resumir_operacao, duracao_resolucao_horas, intervalo_abertura,
    filtrar_chamados_dashboard,
    resumir_carga_departamentos,
)
from streamlit.testing.v1 import AppTest


def chamado(**alteracoes):
    agora = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    registro = dict(id=1, titulo="Falha de acesso", descricao="Aplicativo não abre",
                    status="Novo", urgencia="Media", categoria="Acesso", usuario_id=10,
                    nome_usuario="Solicitante", analista_id=None, nome_analista=None,
                    departamento_usuario="Financeiro", equipe_destino="Suporte",
                    criado_em=agora, prazo_resposta=agora + timedelta(hours=4),
                    prazo_resolucao=agora + timedelta(hours=24), primeira_resposta_em=None,
                    resolvido_em=None, pausado_em=None, tempo_pausado_min=0,
                    sla_configuracao={"usar_horario_comercial": False}, confiabilidade="Alta",
                    metadados_ia=None, motivo_cancelamento=None)
    registro.update(alteracoes)
    return registro


class NavegacaoESessao(unittest.TestCase):
    def test_prioridade_por_permissoes_efetivas(self):
        casos = [
            ({"administracao.acessar", "relatorios.visualizar", "chamados.visualizar_fila"}, ("admin", "Dashboards")),
            ({"administracao.acessar", "chamados.visualizar_fila"}, ("analista", "Fila ativa")),
            ({"administracao.acessar", "chamados.visualizar_proprios"}, ("usuario", "Central de ajuda")),
            ({"chamados.visualizar_proprios"}, ("usuario", "Central de ajuda")),
            ({"administracao.acessar"}, ("admin", None)),
            ({"relatorios.visualizar"}, (None, None)),
            (set(), (None, None)),
        ]
        for permissoes, esperado in casos:
            with self.subTest(permissoes=permissoes):
                self.assertEqual(destino_inicial(permissoes.__contains__), esperado)

    def test_relatorios_nao_concedem_acesso_a_fila(self):
        permissoes = {"administracao.acessar", "relatorios.visualizar"}
        self.assertEqual(set(paginas_autorizadas(permissoes.__contains__)), {"admin"})

    def test_inicializacao_preserva_conversa_e_selecao(self):
        estado = {"chat_mensagens": ["mensagem"], "analista_nav": "Cancelados", "chamado_selecionado_analista": 9}
        inicializar_sessao(estado)
        self.assertEqual(estado["chat_mensagens"], ["mensagem"])
        self.assertEqual(estado["chamado_selecionado_analista"], 9)
        self.assertEqual(estado["analista_nav"], "Cancelados")

    def test_saida_descarta_dados_privados_e_filtros_da_conta(self):
        estado = {"usuario_logado": {"id": 7}, "usr_anexo_pronto_1": b"arquivo",
                  "exportacao_privacidade_1": "dados", "totp_secret_temp": "temporario", "filtro_status_ativa": ["Novo"]}
        limpar_sessao(estado)
        self.assertIsNone(estado["usuario_logado"])
        self.assertNotIn("usr_anexo_pronto_1", estado)
        self.assertNotIn("exportacao_privacidade_1", estado)
        self.assertNotIn("totp_secret_temp", estado)
        self.assertNotIn("filtro_status_ativa", estado)


class IndicadoresExecutivos(unittest.TestCase):
    def test_carga_departamento_inclui_historico_e_separa_ativos(self):
        registros = [chamado(id=i, status=estado) for i, estado in enumerate(
            ("Novo", "Em Andamento", "Em Espera", "Resolvido", "Fechado", "Fechado", "Cancelado"))]
        registros += [chamado(id=10+i, status="Fechado", departamento_usuario="Recursos Humanos") for i in range(12)]
        self.assertEqual(resumir_carga_departamentos(registros), [
            {"Departamento": "Recursos Humanos", "Ativos": 0, "Fechados": 12, "Cancelados": 0},
            {"Departamento": "Financeiro", "Ativos": 4, "Fechados": 2, "Cancelados": 1},
        ])
        self.assertEqual(len(resumir_operacao(registros)["ativos"]), 4)

    def test_carga_departamento_respeita_periodo_e_demais_filtros(self):
        agora = datetime(2026, 11, 24, 12)
        registros = [chamado(id=1, criado_em=agora, status="Fechado", urgencia="Alta"),
                     chamado(id=2, criado_em=agora - timedelta(days=40), status="Fechado", urgencia="Alta"),
                     chamado(id=3, criado_em=agora, categoria="Rede", urgencia="Alta"),
                     chamado(id=4, criado_em=agora, urgencia="Baixa")]
        filtrados = filtrar_chamados_dashboard(registros, agora - timedelta(days=30), agora,
                                               categoria="Acesso", urgencia="Alta")
        self.assertEqual(resumir_carga_departamentos(filtrados), [
            {"Departamento": "Financeiro", "Ativos": 0, "Fechados": 1, "Cancelados": 0}])
        self.assertEqual(resumir_carga_departamentos([]), [])

    def test_duracao_de_atendimento_respeita_fim_de_semana_e_pausas(self):
        from decimal import Decimal
        c = chamado(criado_em=datetime(2026, 11, 13, 17, 30), resolvido_em=datetime(2026, 11, 16, 8, 30),
                    tempo_pausado_min=Decimal("15"), sla_configuracao={"usar_horario_comercial": True, "hora_inicio": "08:00", "hora_fim": "18:00"})
        self.assertEqual(duracao_resolucao_horas(c), 0.75)

    def test_duracao_sem_resolucao_nao_entra_na_media(self):
        import pandas as pd
        self.assertIsNone(duracao_resolucao_horas(chamado(resolvido_em=None)))
        self.assertIsNone(duracao_resolucao_horas(chamado(resolvido_em=pd.NaT)))

    def test_primeira_resposta_violada_entra_no_alerta(self):
        antigo = datetime(2020, 1, 1, 10)
        c = chamado(criado_em=antigo, prazo_resposta=antigo + timedelta(minutes=15),
                    prazo_resolucao=datetime(2099, 1, 1))
        resumo = resumir_operacao([c])
        self.assertEqual(resumo["violados"], 1)
        self.assertEqual(len(resumo["excecoes"]), 1)

    def test_violacao_nas_duas_etapas_conta_uma_vez(self):
        c = chamado(criado_em=datetime(2020, 1, 1), prazo_resposta=datetime(2020, 1, 2), prazo_resolucao=datetime(2020, 1, 3))
        self.assertEqual(resumir_operacao([c])["violados"], 1)

    def test_cancelados_nao_entram_nos_alertas_ou_cumprimento(self):
        resumo = resumir_operacao([chamado(status="Cancelado", urgencia="Critica")])
        self.assertEqual(resumo["ativos"], [])
        self.assertEqual(resumo["excecoes"], [])
        self.assertEqual(resumo["amostra"], 0)
        self.assertIsNone(resumo["taxa"])

    def test_sem_marcos_ou_prazos_nao_inventa_taxa(self):
        c = chamado(status="Fechado", resolvido_em=datetime(2020, 1, 3), primeira_resposta_em=datetime(2020, 1, 2), prazo_resposta=None)
        self.assertIsNone(resumir_operacao([c])["taxa"])
        self.assertIsNone(resumir_operacao([])["taxa"])

    def test_cumprimento_exige_as_duas_etapas(self):
        inicio = datetime(2020, 1, 1, 10)
        c = chamado(status="Fechado", criado_em=inicio, primeira_resposta_em=inicio + timedelta(hours=1),
                    prazo_resposta=inicio + timedelta(hours=2), resolvido_em=inicio + timedelta(hours=5),
                    prazo_resolucao=inicio + timedelta(hours=8))
        atrasado = {**c, "id": 2, "primeira_resposta_em": inicio + timedelta(hours=3)}
        resumo = resumir_operacao([c, atrasado])
        self.assertEqual(resumo["taxa"], 50)
        self.assertEqual(resumo["amostra"], 2)
        self.assertEqual(resumo["violados"], 0)


class FiltrosDashboard(unittest.TestCase):
    def test_janelas_moveis_respeitam_limites_e_horario(self):
        agora = datetime(2026, 3, 1, 14, 30)
        for periodo, dias in (("Último mês", 30), ("Última semana", 7), ("Último dia", 1)):
            with self.subTest(periodo=periodo):
                inicio, fim = intervalo_abertura(periodo, agora)
                self.assertEqual((inicio, fim), (agora - timedelta(days=dias), agora))
                registros = [chamado(id=i, criado_em=data) for i, data in enumerate(
                    (inicio - timedelta(microseconds=1), inicio, fim,
                     fim + timedelta(microseconds=1), None))]
                self.assertEqual([c["id"] for c in filtrar_chamados_dashboard(registros, inicio, fim)], [1, 2])

    def test_data_especifica_inclui_dia_completo_sem_dias_vizinhos(self):
        agora = datetime(2026, 3, 1, 14, 30)
        data = datetime(2026, 2, 28).date()
        inicio, fim = intervalo_abertura("Intervalo de datas", agora, (data, data))
        registros = [chamado(id=i, criado_em=abertura) for i, abertura in enumerate(
            (datetime(2026, 2, 27, 23, 59, 59), datetime(2026, 2, 28),
             datetime(2026, 2, 28, 23, 59, 59, 999999), datetime(2026, 3, 1)))]
        self.assertEqual([c["id"] for c in filtrar_chamados_dashboard(registros, inicio, fim)], [1, 2])

    def test_intervalo_inclui_primeiro_ultimo_e_dias_intermediarios(self):
        agora = datetime(2026, 3, 5, 14, 30)
        inicio, fim = intervalo_abertura("Intervalo de datas", agora,
                                        (datetime(2026, 2, 27).date(), datetime(2026, 3, 1).date()))
        datas = (inicio - timedelta(microseconds=1), inicio, datetime(2026, 2, 28, 12),
                 fim, fim + timedelta(microseconds=1))
        registros = [chamado(id=i, criado_em=data) for i, data in enumerate(datas)]
        self.assertEqual([c["id"] for c in filtrar_chamados_dashboard(registros, inicio, fim)], [1, 2, 3])

    def test_intervalo_rejeita_datas_incompletas_ou_invertidas(self):
        agora = datetime(2026, 3, 5, 14, 30)
        for datas in (None, (), (agora.date(),), (agora.date(), agora.date() - timedelta(days=1))):
            with self.subTest(datas=datas), self.assertRaises(ValueError):
                intervalo_abertura("Intervalo de datas", agora, datas)

    def test_ate_agora_inclui_antigos_e_exclui_futuros(self):
        agora = datetime(2026, 3, 5, 14, 30)
        inicio, fim = intervalo_abertura("Até agora", agora)
        registros = [chamado(id=1, criado_em=datetime(2000, 1, 1), urgencia="Alta"),
                     chamado(id=2, criado_em=agora, urgencia="Alta"),
                     chamado(id=3, criado_em=agora + timedelta(microseconds=1), urgencia="Alta"),
                     chamado(id=4, criado_em=agora, urgencia="Baixa"),
                     chamado(id=5, criado_em=None)]
        self.assertIsNone(inicio)
        self.assertEqual([c["id"] for c in filtrar_chamados_dashboard(registros, inicio, fim)], [1, 2, 4])
        self.assertEqual([c["id"] for c in filtrar_chamados_dashboard(registros, inicio, fim, urgencia="Alta")], [1, 2])

    def test_combina_categoria_urgencia_e_situacao(self):
        agora = datetime(2026, 11, 24, 12)
        registros = [chamado(id=1, criado_em=agora, urgencia="Alta"),
                     chamado(id=2, criado_em=agora, urgencia="Baixa"),
                     chamado(id=3, criado_em=agora, urgencia="Alta", categoria="Rede"),
                     chamado(id=4, criado_em=agora, urgencia="Alta", status="Fechado")]
        filtrados = filtrar_chamados_dashboard(registros, agora - timedelta(days=1), agora,
                                               "Acesso", "Alta", "Novo")
        self.assertEqual([c["id"] for c in filtrados], [1])


class TelasStreamlit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pages import _telas
        cls.telas = _telas

    def executar_tela(self, expressao, registros=(), permissoes=()):
        at = AppTest.from_string(
            'import streamlit as st\nfrom pages import _telas as t\n'
            't.inicializar_estado_sessao()\n'
            'usuario = {"id": 10, "nome": "Pessoa de teste"}\n' + expressao,
            default_timeout=30,
        )
        at.session_state["registros_teste"] = list(registros)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.telas, "usuario_tem_permissao", side_effect=lambda _, codigo: codigo in permissoes))
        self.stack.enter_context(patch.object(self.telas, "usuario_eh_administrador", return_value=False))
        for nome in ("listar_usuarios", "listar_departamentos", "listar_casos_base_ia", "listar_pesquisas_satisfacao", "listar_casos_avaliacao_ia", "listar_artigos", "listar_mensagens_chamado", "listar_anexos_chamado"):
            self.stack.enter_context(patch.object(self.telas, nome, return_value=[]))
        self.stack.enter_context(patch.object(self.telas, "relatorio_qualidade_ia", return_value={"classificacao": {}, "orientacoes": {}}))
        self.stack.enter_context(patch.object(self.telas, "listar_chamados", return_value=list(registros)))
        return at

    def sem_erros(self, at):
        self.assertEqual(len(at.exception), 0, [e.message for e in at.exception])

    def test_dashboard_relatorios_sem_fila_operacional(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado()], {"administracao.acessar", "relatorios.visualizar"})
        with patch.object(self.telas, "listar_historico_chamado", side_effect=AssertionError("histórico indevido")):
            at.run()
        self.sem_erros(at)
        self.assertEqual(at.sidebar.radio[0].value, "Dashboards")
        self.assertEqual(at.metric[0].label, "Chamados ativos")
        self.assertFalse(any(b.label == "Inserir dados provisórios" for b in at.button))

    def test_dashboard_sem_dados(self):
        at = self.executar_tela('t.tela_admin(usuario)', [], {"administracao.acessar", "relatorios.visualizar"}).run()
        self.sem_erros(at)
        self.assertEqual(at.metric[0].value, "0")
        self.assertEqual(at.metric[3].value, "Sem amostra")

    def test_relatorios_usam_tres_situacoes_sem_perder_chamados(self):
        from ui.charts import exibir_grafico_situacao, SITUACOES_CHAMADOS
        registros = [chamado(id=i, status=estado, analista_id=20, nome_analista="Ana",
                             criado_em=datetime(2026, 1, i),
                             resolvido_em=datetime(2026, 1, i, 12) if estado in {"Resolvido", "Fechado"} else None)
                     for i, estado in enumerate(("Novo", "Em Andamento", "Em Espera", "Resolvido", "Cancelado", "Fechado"), 1)]
        casos = [("relatorio_operacional", ", usuario", 2, 6),
                 ("relatorio_chamados_abertos_por_departamento", "", 1, 6),
                 ("relatorio_demanda_por_departamento_categoria", "", 1, 6),
                 ("relatorio_produtividade_equipe", "", 1, 6),
                 ("relatorio_cancelamentos", "", 1, 1),
                 ("relatorio_ia", ", usuario", 1, 6),
                 ("_relatorio_executivo_complementar", ", usuario", 1, 6)]
        for funcao, argumentos, quantidade_graficos, total in casos:
            with self.subTest(funcao=funcao):
                at = self.executar_tela(f't.{funcao}(st.session_state.registros_teste{argumentos})',
                                        registros, {"relatorios.visualizar"})
                grafico = self.stack.enter_context(patch.object(self.telas, "exibir_grafico_situacao", wraps=exibir_grafico_situacao))
                at.run()
                self.sem_erros(at)
                self.assertEqual(grafico.call_count, quantidade_graficos)
                for chamada in grafico.call_args_list:
                    contagens = chamada.args[0][list(SITUACOES_CHAMADOS)]
                    self.assertEqual(int(contagens.sum().sum()), total)
                self.stack.close()

    def test_demo_admin_adiciona_lote_e_remove_por_botoes(self):
        at = self.executar_tela('t.painel_dados_demonstracao(usuario)')
        self.stack.enter_context(patch.object(self.telas, "usuario_eh_administrador", return_value=True))
        contador = self.stack.enter_context(patch.object(self.telas, "contar_dados_demonstracao_dashboard", return_value=0))
        inserir = self.stack.enter_context(patch.object(self.telas, "inserir_dados_demonstracao_dashboard", return_value=24))
        remover = self.stack.enter_context(patch.object(self.telas, "remover_dados_demonstracao_dashboard", return_value=24))
        at.run()
        self.sem_erros(at)
        self.assertTrue(at.button(key="remover_demo_dashboard").disabled)
        at.number_input(key="demo_quantidade").set_value(24).run()
        at.button(key="inserir_demo_dashboard").click().run()
        self.sem_erros(at)
        inserir.assert_called_once_with(10, quantidade=24)
        contador.return_value = 24
        at.run()
        at.button(key="remover_demo_dashboard").click().run()
        self.sem_erros(at)
        remover.assert_called_once_with(10)

    def test_demo_nao_admin_nao_consulta_ou_oferece_operacoes(self):
        at = self.executar_tela('t.painel_dados_demonstracao(usuario)')
        contador = self.stack.enter_context(patch.object(self.telas, "contar_dados_demonstracao_dashboard"))
        at.run()
        self.sem_erros(at)
        contador.assert_not_called()
        self.assertEqual(len(at.button), 0)

    def test_dashboard_apenas_cancelados(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado(status="Cancelado")], {"administracao.acessar", "relatorios.visualizar"}).run()
        self.sem_erros(at)

    def test_dashboard_oferece_periodos_e_remove_filtros_avancados(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado()], {"administracao.acessar", "relatorios.visualizar"}).run()
        self.sem_erros(at)
        self.assertEqual(at.selectbox(key="dashboard_periodo_abertura").options,
                         ["Último mês", "Última semana", "Último dia", "Intervalo de datas", "Até agora"])
        self.assertEqual(at.selectbox(key="dashboard_periodo_abertura").value, "Último mês")
        self.assertEqual(len(at.date_input), 0)
        self.assertFalse(any(e.label == "Filtros avançados do dashboard" for e in at.expander))

    def test_intervalo_de_datas_atualiza_chamados_do_dashboard(self):
        inicio = datetime.now().date() - timedelta(days=4)
        fim = inicio + timedelta(days=2)
        registros = [chamado(id=1, criado_em=datetime.combine(inicio, datetime.min.time())),
                     chamado(id=2, criado_em=datetime.combine(fim, datetime.max.time())),
                     chamado(id=3, criado_em=datetime.combine(fim + timedelta(days=1), datetime.min.time())),
                     chamado(id=4, criado_em=datetime.combine(inicio + timedelta(days=1), datetime.min.time()))]
        at = self.executar_tela('t.tela_admin(usuario)', registros, {"administracao.acessar", "relatorios.visualizar"})
        relatorio = self.stack.enter_context(patch.object(self.telas, "relatorio_executivo_suporte"))
        at.run()
        at.selectbox(key="dashboard_periodo_abertura").set_value("Intervalo de datas").run()
        at.date_input(key="dashboard_intervalo_datas").set_value((inicio, fim)).run()
        self.sem_erros(at)
        self.assertEqual([c["id"] for c in relatorio.call_args.args[0]], [1, 2, 4])
        relatorio.reset_mock()
        at.date_input(key="dashboard_intervalo_datas").set_value((inicio,)).run()
        self.sem_erros(at)
        relatorio.assert_not_called()
        self.assertTrue(any("data inicial e a data final" in aviso.value for aviso in at.info))

    def test_ate_agora_carrega_todas_as_paginas_do_historico(self):
        recente = datetime.now() - timedelta(days=1)
        registros = [chamado(id=i, criado_em=recente) for i in range(1, 5001)]
        antigo = chamado(id=5001, criado_em=datetime(2000, 1, 1))
        at = self.executar_tela('t.tela_admin(usuario)', permissoes={"administracao.acessar", "relatorios.visualizar"})
        consulta = self.telas.listar_chamados
        consulta.side_effect = lambda **kwargs: list(registros) if kwargs.get("pagina", 0) == 0 else [antigo]
        relatorio = self.stack.enter_context(patch.object(self.telas, "relatorio_executivo_suporte"))
        at.run()
        self.sem_erros(at)
        self.assertEqual(len(relatorio.call_args.args[0]), 5000)
        consulta.reset_mock()
        at.selectbox(key="dashboard_periodo_abertura").set_value("Até agora").run()
        self.sem_erros(at)
        self.assertEqual(len(relatorio.call_args.args[0]), 5001)
        self.assertEqual(relatorio.call_args.args[0][-1]["id"], 5001)
        self.assertEqual(consulta.call_count, 2)
        consulta.assert_called_with(limite=5000, executor_id=10, para_relatorio=True, pagina=1)
        self.assertTrue(any("Todo o histórico até" in legenda.value for legenda in at.caption))

    def test_data_especifica_anterior_migra_para_intervalo_do_mesmo_dia(self):
        data = datetime.now().date() - timedelta(days=2)
        at = self.executar_tela('t.tela_admin(usuario)', permissoes={"administracao.acessar", "relatorios.visualizar"})
        at.session_state["dashboard_periodo_abertura"] = "Data específica"
        at.session_state["dashboard_data_especifica"] = data
        at.run()
        self.sem_erros(at)
        self.assertEqual(at.selectbox(key="dashboard_periodo_abertura").value, "Intervalo de datas")
        self.assertEqual(at.date_input(key="dashboard_intervalo_datas").value, (data, data))

    def test_filtros_dashboard_combinam_preservam_e_limpam_selecao(self):
        ontem = datetime.now() - timedelta(days=1)
        registros = [chamado(id=1, criado_em=ontem, urgencia="Alta"),
                     chamado(id=2, criado_em=ontem, urgencia="Baixa"),
                     chamado(id=3, criado_em=ontem, urgencia="Alta", categoria="Rede"),
                     chamado(id=4, criado_em=ontem, urgencia="Alta", status="Fechado")]
        at = self.executar_tela('t.tela_admin(usuario)', registros, {"administracao.acessar", "relatorios.visualizar"})
        relatorio = self.stack.enter_context(patch.object(self.telas, "relatorio_executivo_suporte"))
        at.run()
        at.selectbox(key="dashboard_categoria").set_value("Acesso")
        at.selectbox(key="dashboard_urgencia").set_value("Alta")
        at.selectbox(key="dashboard_situacao").set_value("Novo").run()
        self.sem_erros(at)
        self.assertEqual([c["id"] for c in relatorio.call_args.args[0]], [1])
        at.selectbox(key="dashboard_periodo_abertura").set_value("Última semana").run()
        self.sem_erros(at)
        self.assertEqual(at.selectbox(key="dashboard_categoria").value, "Acesso")
        self.assertEqual([c["id"] for c in relatorio.call_args.args[0]], [1])
        at.selectbox(key="dashboard_situacao").set_value("Cancelado").run()
        self.sem_erros(at)
        self.assertEqual(relatorio.call_args.args[0], [])
        at.button(key="limpar_filtros_dashboard").click().run()
        self.sem_erros(at)
        self.assertEqual(at.selectbox(key="dashboard_periodo_abertura").value, "Último mês")
        self.assertEqual(len(relatorio.call_args.args[0]), 4)

    def test_portal_consulta_nao_exibe_assistente_sem_permissao(self):
        at = self.executar_tela('t.tela_usuario(usuario)', [], {"chamados.visualizar_proprios"}).run()
        self.sem_erros(at)
        self.assertEqual(at.sidebar.radio[0].value, "Meus chamados ativos")
        self.assertNotIn("Abrir novo chamado", at.sidebar.radio[0].options)

    def test_central_redireciona_para_conversa_sem_abrir_chamado(self):
        at = self.executar_tela('t.tela_usuario(usuario)', [], {"chamados.visualizar_proprios", "ia.utilizar", "conhecimento.visualizar"}).run()
        with patch.object(self.telas, "salvar_chamado") as salvar:
            next(b for b in at.button if b.label == "Descrever um problema ou tirar uma dúvida").click().run()
            self.sem_erros(at)
            self.assertEqual(at.sidebar.radio[0].value, "Abrir novo chamado")
            self.assertEqual(len(at.chat_input), 1)
            salvar.assert_not_called()

    def test_confirmacao_sem_permissao_de_abertura_nao_exibe_formulario(self):
        at = self.executar_tela('t._aba_abrir_chamado(usuario)', [], {"ia.utilizar"})
        at.session_state["chat_resultado_final"] = {"status": "aguardando_confirmacao", "titulo": "Falha", "descricao": "Descrição"}
        at.run()
        self.sem_erros(at)
        self.assertFalse(any(b.label == "Confirmar e abrir chamado" for b in at.button))

    def test_fila_preserva_filtros_ao_selecionar_chamado(self):
        c = chamado()
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)', [c], {"chamados.visualizar_fila"}).run()
        at.text_input(key="busca_chamado_ativa").set_value("#1").run()
        self.stack.enter_context(patch.object(self.telas, "buscar_chamado_por_id", return_value=c))
        next(b for b in at.button if b.label == "Ver detalhes").click().run()
        self.sem_erros(at)
        self.assertEqual(at.text_input(key="busca_chamado_ativa").value, "#1")
        self.assertEqual(at.session_state["chamado_selecionado_analista"], 1)
        self.assertFalse(any(b.label in {"Assumir chamado", "Cancelar chamado"} for b in at.button))

    def test_segundo_fator_antecede_privacidade_e_telas(self):
        at = self.executar_tela('t.executar_aplicacao("admin")')
        at.session_state["usuario_pendente_2fa"] = {"id": 10}
        self.stack.enter_context(patch.object(self.telas, "schema_pronto", return_value=True))
        segundo_fator = self.stack.enter_context(patch.object(self.telas, "tela_2fa"))
        privacidade = self.stack.enter_context(patch.object(self.telas, "usuario_aceitou_politica"))
        fechar = self.stack.enter_context(patch.object(self.telas, "fechar_chamados_resolvidos_automaticamente"))
        at.run()
        self.sem_erros(at)
        segundo_fator.assert_called_once()
        privacidade.assert_not_called()
        fechar.assert_not_called()

    def test_privacidade_antecede_redirecionamento(self):
        at = self.executar_tela('t.executar_aplicacao()')
        at.session_state["usuario_logado"] = {"id": 10}
        at.session_state["login_auditoria_registrada"] = True
        self.stack.enter_context(patch.object(self.telas, "schema_pronto", return_value=True))
        self.stack.enter_context(patch.object(self.telas, "fechar_chamados_resolvidos_automaticamente"))
        self.stack.enter_context(patch.object(self.telas, "usuario_aceitou_politica", return_value=False))
        aviso = self.stack.enter_context(patch.object(self.telas, "tela_aceite_privacidade"))
        destino = self.stack.enter_context(patch.object(self.telas, "destino_inicial"))
        at.run()
        self.sem_erros(at)
        aviso.assert_called_once_with({"id": 10})
        destino.assert_not_called()

    def test_atalho_direto_nao_expoe_fila(self):
        at = self.executar_tela('t.tela_analista(usuario)', [chamado()], {"relatorios.visualizar"}).run()
        self.sem_erros(at)
        self.telas.listar_chamados.assert_not_called()
        self.assertEqual(len(at.error), 1)

    def test_conversa_exige_confirmacao_antes_de_persistir(self):
        at = self.executar_tela('t._aba_abrir_chamado(usuario)', [], {"ia.utilizar", "chamados.abrir"})
        at.session_state["chat_resultado_final"] = {"status": "aguardando_confirmacao", "titulo": "Falha", "descricao": "Descrição"}
        salvar = self.stack.enter_context(patch.object(self.telas, "salvar_chamado", return_value=123))
        classificar = self.stack.enter_context(patch.object(self.telas, "classificar_chamado", return_value={"categoria": "Acesso", "urgencia": "Media"}))
        at.run()
        salvar.assert_not_called()
        next(b for b in at.button if b.label == "Confirmar e abrir chamado").click().run()
        self.sem_erros(at)
        salvar.assert_called_once()
        classificar.assert_called_once_with("Falha", "Descrição")
        self.assertEqual(at.session_state["chat_resultado_final"]["id"], 123)

    def test_login_vazio_orienta_sem_chamar_autenticacao(self):
        at = self.executar_tela('t.tela_login()').run()
        autenticar = self.stack.enter_context(patch.object(self.telas, "autenticar"))
        next(b for b in at.button if b.label == "Entrar").click().run()
        self.sem_erros(at)
        autenticar.assert_not_called()
        self.assertIn("Informe seu e-mail", at.warning[0].value)

    def test_recuperacao_vazia_nao_envia_email(self):
        at = self.executar_tela('t.tela_esqueci_senha_pedir()').run()
        enviar = self.stack.enter_context(patch.object(self.telas, "enviar_email"))
        next(b for b in at.button if b.label == "Enviar código de recuperação").click().run()
        self.sem_erros(at)
        enviar.assert_not_called()
        self.assertEqual(len(at.warning), 1)

    def test_departamentos_consulta_nao_renderiza_formulario_de_edicao(self):
        at = self.executar_tela('t.painel_departamentos_admin(usuario)', permissoes={"departamentos.gerenciar"})
        self.telas.listar_departamentos.return_value = [{"id": 2, "nome": "TI", "descricao": "Suporte", "ativo": 1, "total_usuarios": 2}]
        at.run()
        self.sem_erros(at)
        self.assertEqual(len(at.dataframe), 1)
        self.assertFalse(any(b.label == "Salvar departamento" for b in at.button))

    def test_cadastro_departamento_mantem_erro_visivel(self):
        at = self.executar_tela('t.painel_departamentos_admin(usuario)', permissoes={"departamentos.gerenciar"})
        at.session_state["departamentos_modo"] = "Cadastrar"
        criar = self.stack.enter_context(patch.object(self.telas, "criar_departamento", side_effect=ValueError("Já existe um departamento com esse nome.")))
        at.run()
        next(b for b in at.button if b.label == "Cadastrar departamento").click().run()
        self.sem_erros(at)
        criar.assert_called_once()
        self.assertIn("Já existe", at.error[0].value)

    def test_edicao_departamento_preserva_contrato_e_feedback(self):
        at = self.executar_tela('t.painel_departamentos_admin(usuario)', permissoes={"departamentos.gerenciar"})
        at.session_state["departamentos_modo"] = "Editar"
        self.telas.listar_departamentos.return_value = [{"id": 2, "nome": "TI", "descricao": "Suporte", "ativo": 1, "total_usuarios": 2}]
        atualizar = self.stack.enter_context(patch.object(self.telas, "atualizar_departamento"))
        at.run()
        next(b for b in at.button if b.label == "Salvar departamento").click().run()
        self.sem_erros(at)
        atualizar.assert_called_once_with(2, "TI", "Suporte", True, autor_id=10)
        self.assertEqual(len(at.toast), 1)

    def test_sla_preserva_configuracao_vigente_ao_salvar(self):
        import sla
        config = sla.normalizar_configuracao({"usar_horario_comercial": False})
        at = self.executar_tela('t.painel_sla_admin(usuario)', permissoes={"sla.gerenciar"})
        self.stack.enter_context(patch.object(self.telas, "obter_configuracao_sla", return_value=config))
        atualizar = self.stack.enter_context(patch.object(self.telas, "atualizar_configuracao_sla"))
        at.run()
        next(b for b in at.button if b.label == "Salvar configurações para novos chamados").click().run()
        self.sem_erros(at)
        self.assertFalse(atualizar.call_args.args[0]["usar_horario_comercial"])
        self.assertEqual(atualizar.call_args.args[0]["matriz"], config["matriz"])
        self.assertEqual(atualizar.call_args.args[1], 10)

    def test_auditoria_periodo_incompleto_nao_consulta_sem_filtro(self):
        at = self.executar_tela('t.painel_auditoria_admin(usuario)', permissoes={"relatorios.visualizar"})
        listar = self.stack.enter_context(patch.object(self.telas, "listar_auditoria", return_value=[]))
        at.session_state["auditoria_periodo"] = (datetime.now().date(),)
        at.run()
        self.sem_erros(at)
        listar.assert_not_called()

    def test_privacidade_busca_invalida_descarta_titular_anterior(self):
        at = self.executar_tela('t.painel_privacidade_admin(usuario)', permissoes={"privacidade.gerenciar"})
        at.session_state["titular_privacidade_id"] = 15
        self.stack.enter_context(patch.object(self.telas, "buscar_titular_por_identificador", return_value=(None, "Nenhum titular encontrado.")))
        at.run()
        next(b for b in at.button if b.label == "Localizar titular").click().run()
        self.sem_erros(at)
        self.assertNotIn("titular_privacidade_id", at.session_state)

    def test_perfis_sem_dados_exibe_orientacao(self):
        at = self.executar_tela('t.painel_perfis_admin(usuario)', permissoes={"perfis.gerenciar"})
        self.stack.enter_context(patch.object(self.telas, "listar_perfis", return_value=[]))
        self.stack.enter_context(patch.object(self.telas, "listar_permissoes", return_value=[]))
        at.run()
        self.sem_erros(at)
        self.assertEqual(len(at.info), 1)

    def test_cadastro_perfil_limpa_campos_apos_confirmacao(self):
        at = self.executar_tela('t.painel_perfis_admin(usuario)', permissoes={"perfis.gerenciar"})
        self.stack.enter_context(patch.object(self.telas, "listar_perfis", return_value=[]))
        self.stack.enter_context(patch.object(self.telas, "listar_permissoes", return_value=[]))
        criar = self.stack.enter_context(patch.object(self.telas, "criar_perfil"))
        at.session_state["perfis_modo"] = "Criar perfil"
        at.run()
        at.text_input(key="novo_perfil_nome").set_value("Consulta").run()
        at.button(key="novo_perfil_cadastrar").click().run()
        self.sem_erros(at)
        criar.assert_called_once_with("Consulta", "", [], 10)
        self.assertEqual(at.text_input(key="novo_perfil_nome").value, "")

    def test_fila_paginada_nao_renderiza_todos_os_cartoes(self):
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)',
                                [chamado(id=i) for i in range(1, 13)], {"chamados.visualizar_fila"}).run()
        self.sem_erros(at)
        self.assertEqual(sum(b.label == "Ver detalhes" for b in at.button), 5)
        at.number_input(key="pagina_fila_ativa").set_value(3).run()
        self.sem_erros(at)
        self.assertEqual(sum(b.label == "Ver detalhes" for b in at.button), 2)

    def test_erro_ao_assumir_nao_desaparece_com_recarregamento(self):
        c = chamado()
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)', [c], {"chamados.visualizar_fila", "chamados.assumir"})
        at.session_state["chamado_selecionado_analista"] = c["id"]
        self.stack.enter_context(patch.object(self.telas, "buscar_chamado_por_id", return_value=c))
        assumir = self.stack.enter_context(patch.object(self.telas, "atribuir_chamado", side_effect=ValueError("Este chamado já foi atribuído.")))
        at.run()
        next(b for b in at.button if b.label == "Assumir chamado").click().run()
        self.sem_erros(at)
        assumir.assert_called_once()
        self.assertIn("já foi atribuído", at.error[0].value)

    def test_dashboard_nao_consulta_paineis_que_nao_estao_abertos(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado()], {"administracao.acessar", "relatorios.visualizar"})
        for nome in ("relatorio_operacional", "relatorio_sla_desempenho", "relatorio_ia", "relatorio_usuarios"):
            self.stack.enter_context(patch.object(self.telas, nome, side_effect=AssertionError("painel fechado")))
        at.run()
        self.sem_erros(at)

    def test_edicao_conta_sem_permissao_nao_consulta_dados(self):
        at = self.executar_tela('t.painel_perfil_usuario_admin(usuario)')
        buscar = self.stack.enter_context(patch.object(self.telas, "buscar_usuario_por_id"))
        at.run()
        self.sem_erros(at)
        buscar.assert_not_called()

    def test_falha_conexao_exibe_recuperacao_sem_dados_tecnicos(self):
        at = self.executar_tela('t.executar_aplicacao()')
        self.stack.enter_context(patch.object(self.telas, "schema_pronto", side_effect=self.telas.mysql.connector.Error("detalhe interno")))
        at.run()
        self.sem_erros(at)
        self.assertIn("MySQL", at.error[0].value)
        self.assertNotIn("detalhe interno", at.error[0].value)

    def test_consulta_usuarios_nao_exibe_acoes_de_edicao(self):
        at = self.executar_tela('t.tela_admin(usuario)', permissoes={"administracao.acessar", "usuarios.visualizar"})
        self.telas.listar_usuarios.return_value = [{"id": 12, "nome": "Teste", "sobrenome": "Pessoa", "email": "teste@example.com", "perfil_nome": "Consulta", "ultimo_login": None}]
        at.run()
        self.sem_erros(at)
        self.assertEqual(len(at.dataframe), 1)
        self.assertFalse(any("Abrir perfil" in b.label for b in at.button))

    def test_perfil_protegido_nao_libera_alteracao_de_permissoes(self):
        at = self.executar_tela('t.painel_perfis_admin(usuario)', permissoes={"perfis.gerenciar"})
        perfil = {"id": 1, "chave": "administrador", "nome": "Administrador", "descricao": "Acesso protegido", "ativo": 1, "sistema": 1, "total_usuarios": 1, "total_permissoes": 1}
        self.stack.enter_context(patch.object(self.telas, "listar_perfis", return_value=[perfil]))
        self.stack.enter_context(patch.object(self.telas, "listar_permissoes", return_value=[{"id": 1, "codigo": "administracao.acessar", "nome": "Administração", "descricao": "Acesso à área"}]))
        self.stack.enter_context(patch.object(self.telas, "permissoes_do_perfil", return_value=[1]))
        at.session_state["perfis_modo"] = "Editar perfil"
        at.run()
        self.sem_erros(at)
        self.assertTrue(at.checkbox(key="perfil_1_1").disabled)
        self.assertTrue(at.button(key="perfil_1_salvar").disabled)
        self.assertTrue(at.button(key="perfil_1_excluir").disabled)

    def test_privacidade_autorizada_nao_exige_consulta_geral_de_usuarios(self):
        at = self.executar_tela('t.acoes_privacidade_admin(usuario)', permissoes={"privacidade.gerenciar"})
        at.session_state["titular_privacidade_id"] = 15
        at.session_state["titular_privacidade_email"] = "titular@example.com"
        self.stack.enter_context(patch.object(self.telas, "buscar_titular_por_identificador", return_value=({"id": 15, "email": "titular@example.com"}, None)))
        buscar_usuario = self.stack.enter_context(patch.object(self.telas, "buscar_usuario_por_id", side_effect=AssertionError("acesso geral indevido")))
        at.run()
        self.sem_erros(at)
        buscar_usuario.assert_not_called()
        self.assertTrue(at.button(key="privacidade_anonimizar_15").disabled)

    def test_historico_e_cancelados_renderizam_com_paginacao(self):
        for funcao, estado in (("_aba_historico_analista", "Fechado"), ("_aba_cancelados_analista", "Cancelado")):
            with self.subTest(estado=estado):
                at = self.executar_tela(f't.{funcao}(usuario, st.session_state.registros_teste)', [chamado(id=i, status=estado) for i in range(1, 8)], {"chamados.visualizar_fila"}).run()
                self.sem_erros(at)
                self.assertEqual(sum(b.label == "Ver detalhes" for b in at.button), 5)

    def test_historico_tem_cards_compactos_e_paginacao_no_rodape(self):
        registros = [chamado(id=i, status="Fechado", nome_usuario="Maria Silva", nome_analista="Ana Souza",
                             criado_em=datetime(2026, 1, i), resolvido_em=datetime(2026, 1, i, 12))
                     for i in range(1, 13)]
        at = self.executar_tela('t._aba_historico_analista(usuario, st.session_state.registros_teste)',
                                registros, {"chamados.visualizar_fila"}).run()
        self.sem_erros(at)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"],
                         ["hist_12", "hist_11", "hist_10", "hist_9", "hist_8"])
        botoes = [b.key for b in at.button]
        self.assertLess(botoes.index("hist_8"), botoes.index("historico_pagina_anterior"))
        self.assertTrue(at.button(key="historico_pagina_anterior").disabled)
        self.assertFalse(at.button(key="historico_pagina_proxima").disabled)
        textos = " ".join(c.value for c in at.caption)
        self.assertIn("Aberto por: Maria Silva", textos)
        self.assertIn("Responsável: Ana Souza", textos)
        self.assertIn("Abertura: 12/01/2026", textos)
        self.assertIn("Resolução: 12/01/2026", textos)
        self.assertIn("Mostrando 1–5 de 12 chamados", textos)
        self.assertFalse(any(e.label == "Chamados fechados" for e in at.expander))
        at.button(key="historico_pagina_proxima").click().run()
        self.sem_erros(at)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"],
                         ["hist_7", "hist_6", "hist_5", "hist_4", "hist_3"])
        at.number_input(key="pagina_historico").set_value(3).run()
        self.sem_erros(at)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"], ["hist_2", "hist_1"])
        self.assertTrue(at.button(key="historico_pagina_proxima").disabled)
        at.button(key="historico_pagina_anterior").click().run()
        self.sem_erros(at)
        self.assertEqual(at.number_input(key="pagina_historico").value, 2)

    def test_historico_busca_reinicia_pagina_e_mostra_estado_vazio(self):
        registros = [chamado(id=i, status="Fechado", nome_usuario=f"Pessoa {i}") for i in range(1, 13)]
        at = self.executar_tela('t._aba_historico_analista(usuario, st.session_state.registros_teste)',
                                registros, {"chamados.visualizar_fila"}).run()
        at.number_input(key="pagina_historico").set_value(3).run()
        at.text_input(key="busca_historico").set_value("Pessoa 1").run()
        self.sem_erros(at)
        self.assertEqual(at.number_input(key="pagina_historico").value, 1)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"],
                         ["hist_12", "hist_11", "hist_10", "hist_1"])
        at.text_input(key="busca_historico").set_value("inexistente").run()
        self.sem_erros(at)
        self.assertEqual(sum(b.label == "Ver detalhes" for b in at.button), 0)
        self.assertTrue(at.button(key="historico_pagina_anterior").disabled)
        self.assertTrue(at.button(key="historico_pagina_proxima").disabled)
        self.assertTrue(any("Nenhum chamado fechado com os filtros" in aviso.value for aviso in at.info))

    def test_historico_detalhe_preserva_pagina_e_fecha_ao_navegar(self):
        registros = [chamado(id=i, status="Fechado") for i in range(1, 13)]
        at = self.executar_tela('t._aba_historico_analista(usuario, st.session_state.registros_teste)',
                                registros, {"chamados.visualizar_fila"})
        buscar = self.stack.enter_context(patch.object(self.telas, "buscar_chamado_por_id", return_value=registros[6]))
        for nome in ("painel_conversa_chamado", "painel_anexos_chamado", "listar_historico_chamado"):
            self.stack.enter_context(patch.object(self.telas, nome, return_value=[]))
        at.run()
        at.number_input(key="pagina_historico").set_value(2).run()
        at.button(key="hist_7").click().run()
        self.sem_erros(at)
        buscar.assert_called_with(7, 10)
        self.assertEqual(at.number_input(key="pagina_historico").value, 2)
        at.button(key="historico_fechar_detalhes").click().run()
        self.sem_erros(at)
        self.assertIsNone(at.session_state["chamado_selecionado_historico"])
        self.assertEqual(at.number_input(key="pagina_historico").value, 2)
        at.button(key="hist_7").click().run()
        buscar.reset_mock()
        at.button(key="historico_pagina_proxima").click().run()
        self.sem_erros(at)
        buscar.assert_not_called()
        self.assertIsNone(at.session_state["chamado_selecionado_historico"])

    def test_historico_consulta_fechados_anteriores_ao_limite_de_200(self):
        recentes = [chamado(id=i, status="Fechado") for i in range(1, 201)]
        antigo = chamado(id=9999, status="Fechado", titulo="Registro antigo", criado_em=datetime(2000, 1, 1))
        at = self.executar_tela('t.tela_analista(usuario)', permissoes={"chamados.visualizar_fila"})
        at.session_state["analista_nav"] = "Histórico (fechados)"
        consulta = self.telas.listar_chamados
        consulta.side_effect = lambda **kwargs: list(recentes) if kwargs["pagina"] == 0 else [antigo]
        at.run()
        self.sem_erros(at)
        consulta.assert_called_with(limite=200, executor_id=10, pagina=1, status="Fechado")
        at.number_input(key="pagina_historico").set_value(41).run()
        self.sem_erros(at)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"], ["hist_9999"])
        at.text_input(key="busca_historico").set_value("Registro antigo").run()
        self.sem_erros(at)
        self.assertEqual(at.number_input(key="pagina_historico").value, 1)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"], ["hist_9999"])

    def test_atalho_meus_chamados_filtra_pelo_id_do_responsavel(self):
        registros = [chamado(id=1, analista_id=10, nome_analista="Pessoa de teste"),
                     chamado(id=2, analista_id=20, nome_analista="Pessoa de teste"),
                     chamado(id=3, analista_id=None)]
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)', registros, {"chamados.visualizar_fila"}).run()
        at.toggle(key="somente_meus_ativa").set_value(True).run()
        self.sem_erros(at)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"], ["sel_1"])
        self.assertIn("Atribuídos a mim", " ".join(c.value for c in at.caption))

    def test_atalho_meus_remove_conflito_com_analista_anterior(self):
        registros = [chamado(id=1, analista_id=10, nome_analista="Eu"),
                     chamado(id=2, analista_id=20, nome_analista="Outro analista")]
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)', registros, {"chamados.visualizar_fila"}).run()
        at.selectbox(key="filtro_analista_ativa").set_value("Outro analista").run()
        at.toggle(key="somente_meus_ativa").set_value(True).run()
        self.sem_erros(at)
        self.assertEqual(at.selectbox(key="filtro_analista_ativa").value, "Todos")
        self.assertTrue(at.selectbox(key="filtro_analista_ativa").disabled)
        self.assertEqual([b.key for b in at.button if b.label == "Ver detalhes"], ["sel_1"])

    def test_filtro_meus_nao_mantem_detalhe_de_outro_analista(self):
        outro = chamado(id=2, analista_id=20, nome_analista="Outro")
        at = self.executar_tela('t._aba_fila_ativa_analista(usuario, st.session_state.registros_teste)',
                                [chamado(id=1, analista_id=10), outro], {"chamados.visualizar_fila"})
        buscar = self.stack.enter_context(patch.object(self.telas, "buscar_chamado_por_id", return_value=outro))
        at.session_state["chamado_selecionado_analista"] = 2
        at.run()
        buscar.reset_mock()
        at.toggle(key="somente_meus_ativa").set_value(True).run()
        self.sem_erros(at)
        buscar.assert_not_called()
        self.assertTrue(any("fora dos filtros" in i.value for i in at.info))
        # A seleção pode ser recuperada ao voltar ao escopo anterior.
        self.assertEqual(at.session_state["chamado_selecionado_analista"], 2)


if __name__ == '__main__':
    unittest.main()
