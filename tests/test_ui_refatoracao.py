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
from ui.admin_dashboard import resumir_operacao, duracao_resolucao_horas
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

    def test_dashboard_apenas_cancelados(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado(status="Cancelado")], {"administracao.acessar", "relatorios.visualizar"}).run()
        self.sem_erros(at)

    def test_periodo_incompleto_nao_mostra_dados_sem_recorte(self):
        at = self.executar_tela('t.tela_admin(usuario)', [chamado()], {"administracao.acessar", "relatorios.visualizar"}).run()
        at.date_input(key="dashboard_periodo").set_value((datetime.now().date(),)).run()
        self.sem_erros(at)
        self.assertEqual(len(at.metric), 0)

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
