import json
import re
import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime, time, timedelta
from pathlib import Path

from ia_engine import (
    classificar_chamado, conversar_coleta, identificar_intencao, responder_duvida, avaliar_classificador,
)
from rag import listar_artigos
import sla
from database import (
    salvar_chamado, listar_departamentos, criar_departamento,
    atualizar_departamento, listar_perfis, listar_perfis_para_atribuicao,
    listar_permissoes, permissoes_do_perfil, criar_perfil,
    atualizar_perfil, excluir_perfil, usuario_tem_permissao,
    usuario_eh_administrador, listar_chamados, buscar_chamado_por_id,
    atribuir_chamado, listar_mensagens_chamado, registrar_resolucao_chamado,
    transferir_chamado, escalar_chamado, listar_analistas_para_transferencia,
    listar_historico_chamado, enviar_mensagem_chamado, listar_usuarios,
    criar_usuario, buscar_usuario_por_email, redefinir_senha_com_codigo,
    salvar_totp_secret, salvar_codigo_verificacao, verificar_codigo,
    buscar_usuario_por_id, atualizar_usuario, excluir_usuario,
    buscar_titular_por_identificador, buscar_usuario_por_cpf, normalizar_cpf,
    exportar_dados_titular, anonimizar_titular, salvar_anexo_chamado,
    listar_anexos_chamado, baixar_anexo_chamado, buscar_pesquisa_satisfacao,
    listar_pesquisas_satisfacao, salvar_pesquisa_satisfacao, salvar_atendimento_ia,
    registrar_resultado_atendimento_ia, registrar_feedback_atendimento_ia, relatorio_qualidade_ia,
    cadastrar_caso_avaliacao_ia, listar_casos_avaliacao_ia, registrar_execucao_avaliacao_ia,
    listar_casos_base_ia, registrar_auditoria, registrar_login,
    usuario_aceitou_politica, registrar_aceite_privacidade, VERSAO_POLITICA_PRIVACIDADE,
    cancelar_chamado_sem_atribuicao, confirmar_resolucao_usuario, reabrir_chamado_usuario,
    obter_configuracao_sla, atualizar_configuracao_sla, fechar_chamados_resolvidos_automaticamente,
    listar_auditoria, inserir_dados_demonstracao_dashboard, remover_dados_demonstracao_dashboard,
    contar_dados_demonstracao_dashboard, para_horario_local,
)
from auth import (
    autenticar, gerar_hash_senha, gerar_codigo_numerico, gerar_totp_secret,
    gerar_qrcode_totp, verificar_totp,
)
from email_utils import enviar_email
from migrations import schema_pronto
from core.navigation import PAGINAS_POR_PERMISSAO, paginas_autorizadas, destino_inicial
from core.session import ESTADO_INICIAL_SESSAO, inicializar_sessao, limpar_sessao
from ui.components import (
    cabecalho, exibir_tabela_tematica, exibir_cartao_chamado,
    painel_metricas_chamado, bloco_sla_detalhe, indicadores,
    exibir_grafico_barras as _exibir_grafico_barras,
    painel_acesso, recarregar_com_feedback, notificar, exibir_notificacao,
    paginar_registros, tabela_usuarios, rotulo,
    indicadores_destaque_chamado,
    exibir_status_chamado,
)
from ui.admin_dashboard import renderizar_dashboard, duracao_resolucao_horas, departamento_relatorio as _departamento_relatorio, filtros_dashboard
from ui.charts import (
    SITUACOES_CHAMADOS, resumir_por_situacao, resumir_evolucao_por_situacao,
    exibir_grafico_situacao,
)
from ui.analyst_view import (
    filtros_fila, filtrar_fila, resumo_filtros, cartao_fila_compacto,
    cartao_historico_compacto, paginar_historico, reiniciar_consulta_historico,
    fechar_detalhe_historico,
)
from ui.requester_view import boas_vindas, contexto_conversa, acompanhar_chamado


STATUS_OPCOES = ["Novo", "Em Andamento", "Em Espera", "Resolvido", "Fechado"]
STATUS_ENCERRADOS = {"Fechado", "Cancelado"}
MOTIVOS_CANCELAMENTO = [
    "Desisti da solicitação",
    "Problema resolvido sem suporte",
    "Chamado aberto por engano",
    "Chamado duplicado",
]

MOTIVOS_CANCELAMENTO_ANALISTA = [
    "Chamado duplicado",
    "Chamado aberto indevidamente",
    "Solicitação fora do escopo de atendimento",
    "Informações insuficientes para atendimento",
]

def injetar_css():
    """Compatibilidade com as telas existentes; utiliza apenas o tema nativo."""
    return


ICONE_SECAO = {
    "exemplos de chamados típicos": "📋",
    "informações que devem constar no chamado": "📝",
    "criticidade sugerida": "⚠️",
    "perguntas para a coleta da ia": "❓",
    "casos recorrentes": "📌",
    "casos recorrentes e encaminhamento": "📌",
    "procedimentos seguros": "🔒",
    "segurança": "🔒",
    "cuidados": "🔒",
    "regras de urgência": "⏱️",
    "procedimento padrão": "🛠️",
    "verificações iniciais": "🛠️",
    "evidências úteis para o chamado": "🔎",
    "boas práticas de diagnóstico": "🛠️",
}


def _renderizar_secoes_artigo(corpo):
    partes = corpo.split("\n", 1)
    resto = partes[1] if len(partes) > 1 else corpo
    blocos = re.split(r"(?=^##\s)", resto, flags=re.MULTILINE)
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
        if bloco.startswith("##"):
            linhas = bloco.split("\n", 1)
            titulo_secao = linhas[0].lstrip("#").strip()
            conteudo_secao = linhas[1] if len(linhas) > 1 else ""
            icone = ICONE_SECAO.get(titulo_secao.lower(), "🔹")
            st.markdown(f"##### {icone} {titulo_secao}")
            st.markdown(conteudo_secao)
        else:
            st.markdown(bloco)




def _quem_precisa_agir(chamado):
    if chamado["status"] == "Novo":
        return "A equipe de suporte precisa assumir o chamado."
    if chamado["status"] == "Em Espera":
        return "Você precisa responder à solicitação da equipe para o atendimento continuar."
    if chamado["status"] == "Resolvido":
        return "Você precisa confirmar a solução ou solicitar reabertura."
    if chamado["status"] == "Fechado":
        return "Atendimento concluído."
    if chamado["status"] == "Cancelado":
        return "Chamado cancelado; não serão aceitas novas mensagens."
    return "A equipe responsável está trabalhando no chamado."


def linha_do_tempo_chamado(chamado, executor_id):
    """Apresenta marcos operacionais sem esconder o histórico estrutrado."""
    st.markdown("##### Linha do tempo")
    marcos = [(chamado.get("criado_em"), "Chamado aberto")]
    if chamado.get("primeira_resposta_em"):
        marcos.append((chamado["primeira_resposta_em"], "Primeira resposta da equipe"))
    if chamado.get("pausado_em"):
        marcos.append((chamado["pausado_em"], "Em espera — aguardando retorno"))
    if chamado.get("resolvido_em"):
        marcos.append((chamado["resolvido_em"], "Solução registrada"))
    for evento in listar_historico_chamado(chamado["id"], executor_id):
        marcos.append((evento.get("criado_em"), evento["tipo"].replace("_", " ").capitalize()))
    vistos = set()
    for data, descricao in sorted(marcos, key=lambda item: item[0] or datetime.min):
        chave = (str(data), descricao)
        if data and chave not in vistos:
            vistos.add(chave)
            st.caption(f"● {sla.formatar_data(data)} — {descricao}")


def inicializar_estado_sessao():
    """Preserva as chaves públicas utilizadas pelas páginas."""
    inicializar_sessao(st.session_state)
    exibir_notificacao()
    for prefixo in st.session_state.pop("ui_limpar_prefixos", []):
        for chave in list(st.session_state):
            if chave.startswith(prefixo):
                st.session_state.pop(chave, None)


def tela_login():
    injetar_css()
    with painel_acesso():
        st.title("Seu suporte começa aqui")
        st.write("Entre para tirar dúvidas, acompanhar chamados e acessar sua área de trabalho.")

        with st.container(border=True):
            with st.form("form_login"):
                email = st.text_input("E-mail", placeholder="voce@empresa.com.br")
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar", width="stretch", type="primary")

            if entrar:
                if not email.strip() or not senha:
                    st.warning("Informe seu e-mail e sua senha para entrar.")
                    return
                usuario = autenticar(email.strip(), senha)
                if usuario is None:
                    registrar_auditoria(None, "LOGIN_FALHOU", "sessao", resultado="FALHA")
                    st.error("Email ou senha inválidos.")
                elif usuario.get("senha_deve_ser_redefinida"):
                    registrar_auditoria(usuario["id"], "LOGIN_BLOQUEADO_CREDENCIAL_INVALIDADA", "sessao", resultado="FALHA")
                    st.warning("Esta credencial foi invalidada. Use “Esqueci minha senha” para definir uma nova senha.")
                elif usuario_eh_administrador(usuario["id"]):
                    st.session_state.usuario_pendente_2fa = usuario
                    if not usuario.get("totp_secret"):
                        codigo = gerar_codigo_numerico()
                        salvar_codigo_verificacao(usuario["id"], codigo, tipo="login_2fa")
                        registrar_auditoria(usuario["id"], "CODIGO_2FA_SOLICITADO", "sessao")
                        try:
                            enviar_email(
                                usuario["email"],
                                "Seu código de verificação",
                                f"Seu código de login é: {codigo}\nEle expira em 10 minutos.",
                            )
                            st.info("Enviamos um código de verificação para o seu e-mail.")
                        except Exception as e:
                            st.error(f"Não foi possível enviar o e-mail: {e}")
                    st.rerun()
                else:
                    st.session_state.usuario_logado = usuario
                    registrar_login(usuario["id"])
                    st.session_state.login_auditoria_registrada = True
                    st.rerun()

            if st.button("Esqueci minha senha", width="stretch"):
                st.session_state.tela_atual = "esqueci_senha_pedir"
                st.rerun()


def tela_2fa():
    injetar_css()
    usuario = st.session_state.usuario_pendente_2fa
    with painel_acesso():
        st.title("Confirme seu acesso")
        st.caption("Etapa de segurança · informe o código de seis dígitos.")

        usa_app = bool(usuario.get("totp_secret"))
        with st.container(border=True):
            if usa_app:
                st.write("Abra seu aplicativo autenticador (Google Authenticator, Authy, etc) e digite o código de 6 dígitos.")
            else:
                st.write(f"Enviamos um código para **{usuario['email']}**. Confira sua caixa de entrada (e o spam).")

            with st.form("form_2fa"):
                codigo = st.text_input("Código de verificação", max_chars=6, placeholder="000000")
                confirmar = st.form_submit_button("Confirmar", width="stretch", type="primary")

            if confirmar:
                if usa_app:
                    valido = verificar_totp(usuario["totp_secret"], codigo)
                else:
                    valido = verificar_codigo(usuario["id"], codigo, tipo="login_2fa")

                if valido:
                    st.session_state.usuario_logado = usuario
                    st.session_state.usuario_pendente_2fa = None
                    registrar_login(usuario["id"])
                    st.session_state.login_auditoria_registrada = True
                    st.rerun()
                else:
                    registrar_auditoria(usuario["id"], "LOGIN_2FA_FALHOU", "sessao", resultado="FALHA")
                    st.error("Código inválido ou expirado.")

            if st.button("Cancelar e voltar", width="stretch"):
                st.session_state.usuario_pendente_2fa = None
                st.rerun()


def tela_esqueci_senha_pedir():
    injetar_css()
    with painel_acesso():
        st.title("Recuperar acesso")
        with st.container(border=True):
            with st.form("form_pedir_codigo"):
                email = st.text_input("Digite seu email cadastrado")
                enviar = st.form_submit_button("Enviar código de recuperação", width="stretch", type="primary")

            if enviar:
                if not email.strip():
                    st.warning("Informe o e-mail da sua conta para receber as instruções.")
                    return
                usuario = buscar_usuario_por_email(email)
                if usuario is not None:
                    codigo = gerar_codigo_numerico()
                    salvar_codigo_verificacao(usuario["id"], codigo, tipo="reset_senha")
                    registrar_auditoria(usuario["id"], "RECUPERACAO_SENHA_SOLICITADA", "sessao")
                    try:
                        enviar_email(
                            email,
                            "Recuperação de senha",
                            f"Seu código de recuperação é: {codigo}\nEle expira em 10 minutos.",
                        )
                    except Exception:
                        registrar_auditoria(usuario["id"], "RECUPERACAO_SENHA_ENVIO_FALHOU", "sessao", resultado="FALHA")
                else:
                    registrar_auditoria(None, "RECUPERACAO_SENHA_SOLICITADA", "sessao", resultado="FALHA")
                st.session_state.email_recuperacao = email
                st.session_state.tela_atual = "esqueci_senha_confirmar"
                st.info("Se existir uma conta para este e-mail, enviaremos instruções de recuperação.")
                st.rerun()

            if st.button("Voltar ao login", width="stretch"):
                st.session_state.tela_atual = "login"
                st.rerun()


def tela_esqueci_senha_confirmar():
    injetar_css()
    with painel_acesso():
        st.title("Recuperar acesso")
        st.caption(f"Se houver uma conta para {st.session_state.email_recuperacao}, verifique as instruções recebidas por e-mail.")

        with st.container(border=True):
            with st.form("form_confirmar_codigo"):
                codigo = st.text_input("Código recebido por e-mail", max_chars=6, placeholder="000000")
                nova_senha = st.text_input("Nova senha", type="password")
                confirmar = st.form_submit_button("Redefinir senha", width="stretch", type="primary")

            if confirmar:
                usuario = buscar_usuario_por_email(st.session_state.email_recuperacao)
                redefinida = False
                if not nova_senha:
                    st.error("Informe uma nova senha.")
                elif usuario:
                    try:
                        redefinir_senha_com_codigo(usuario["id"], codigo, gerar_hash_senha(nova_senha))
                        redefinida = True
                    except ValueError:
                        pass
                if redefinida:
                    st.success("Senha redefinida com sucesso! Faça login com a nova senha.")
                    st.session_state.tela_atual = "login"
                    st.session_state.email_recuperacao = None
                elif nova_senha:
                    registrar_auditoria(
                        usuario["id"] if usuario else None, "RECUPERACAO_SENHA_FALHOU",
                        "sessao", resultado="FALHA",
                    )
                    st.error("Código inválido ou expirado.")

            if st.button("Voltar ao login", width="stretch"):
                st.session_state.tela_atual = "login"
                st.rerun()


def sair():
    usuario = st.session_state.get("usuario_logado")
    if usuario:
        registrar_auditoria(usuario["id"], "LOGOUT_REALIZADO", "sessao")
    limpar_sessao(st.session_state)
    st.switch_page("app.py")


def painel_conversa_chamado(chamado, usuario_atual, papel_atual, key_prefix):
    mensagens = listar_mensagens_chamado(chamado["id"], usuario_atual["id"])

    caixa = st.container(height=320, border=True)
    with caixa:
        if not mensagens:
            st.caption("Nenhuma mensagem ainda. Inicie a conversa abaixo.")
        for msg in mensagens:
            eh_proprio_autor = msg["autor_papel"] == papel_atual
            icone = "🧑‍💻" if msg["autor_papel"] == "analista" else "🙋"
            with st.chat_message("assistant" if msg["autor_papel"] == "analista" else "user"):
                st.markdown(f"**{msg['autor_nome']}** · {icone} {msg['autor_papel'].capitalize()}")
                st.write(msg["mensagem"])

    if chamado["status"] in STATUS_ENCERRADOS:
        st.caption("Chamado encerrado — não é possível enviar novas mensagens.")
        return

    permissao = "chamados.responder_proprios" if chamado.get("usuario_id") == usuario_atual["id"] else "chamados.responder_atribuidos"
    if not usuario_tem_permissao(usuario_atual["id"], permissao):
        st.caption("Seu perfil permite consultar esta conversa, mas não enviar mensagens.")
        return
    entrada = st.chat_input("Escreva uma mensagem...", key=f"{key_prefix}_chat_{chamado['id']}")
    if entrada:
        enviar_mensagem_chamado(
            chamado_id=chamado["id"],
            autor_id=usuario_atual["id"],
            autor_nome=usuario_atual["nome"],
            autor_papel=papel_atual,
            mensagem=entrada,
        )
        st.rerun()


def painel_anexos_chamado(chamado, usuario, key_prefix):
    anexos = listar_anexos_chamado(chamado["id"], usuario["id"])
    if anexos:
        st.markdown("##### Anexos")
        for anexo in anexos:
            tamanho = anexo.get("tamanho_bytes") or 0
            st.caption(f"{anexo['nome_arquivo']} · {tamanho / 1024:.1f} KB")
            chave_download = f"{key_prefix}_anexo_pronto_{anexo['id']}"
            if st.button("Preparar download", key=f"{key_prefix}_preparar_{anexo['id']}"):
                try:
                    st.session_state[chave_download] = baixar_anexo_chamado(
                        anexo["id"], chamado["id"], usuario["id"],
                    )
                except ValueError as erro:
                    st.warning(str(erro))
            arquivo = st.session_state.get(chave_download)
            if arquivo:
                st.download_button(
                    f"Baixar {anexo['nome_arquivo']}", data=arquivo["conteudo"],
                    file_name=anexo["nome_arquivo"],
                    mime=anexo.get("tipo_arquivo") or "application/octet-stream",
                    key=f"{key_prefix}_baixar_{anexo['id']}",
                )

    if chamado["status"] in STATUS_ENCERRADOS:
        return

    permissao = "chamados.anexar_proprios" if chamado.get("usuario_id") == usuario["id"] else "chamados.anexar_atribuidos"
    if not usuario_tem_permissao(usuario["id"], permissao):
        return
    with st.form(f"{key_prefix}_form_anexo_{chamado['id']}", clear_on_submit=True):
        arquivo = st.file_uploader(
            "Adicionar anexo à conversa (máximo de 10 MB)",
            key=f"{key_prefix}_anexo_{chamado['id']}",
        )
        enviar = st.form_submit_button("Enviar anexo", width="stretch")

    if enviar:
        if arquivo is None:
            st.warning("Selecione um arquivo antes de enviar.")
        else:
            conteudo = arquivo.getvalue()
            if len(conteudo) > 10 * 1024 * 1024:
                st.error("O anexo deve ter no máximo 10 MB.")
            else:
                try:
                    salvar_anexo_chamado(
                        chamado["id"], usuario["id"], arquivo.name, arquivo.type, conteudo
                    )
                except Exception as erro:
                    st.error(f"Não foi possível enviar o anexo: {erro}")
                else:
                    recarregar_com_feedback('Anexo adicionado ao chamado.')


def painel_pesquisa_satisfacao(chamado, usuario):
    if chamado["status"] != "Fechado":
        return
    pesquisa = buscar_pesquisa_satisfacao(chamado["id"], usuario["id"])
    st.markdown("##### Pesquisa de satisfação")
    if pesquisa:
        st.success(f"Pesquisa respondida: {pesquisa['nota']}/5")
        if pesquisa.get("comentario"):
            st.caption(pesquisa["comentario"])
        return
    if not usuario_tem_permissao(usuario["id"], "chamados.confirmar_resolucao"):
        return
    with st.form(f"pesquisa_{chamado['id']}"):
        nota = st.radio("Como foi o atendimento?", [1, 2, 3, 4, 5], horizontal=True, format_func=lambda n: f"{n} ★")
        comentario = st.text_area("Comentário (opcional)")
        responder = st.form_submit_button("Enviar avaliação")
    if responder:
        salvar_pesquisa_satisfacao(chamado["id"], nota, comentario.strip() or None, autor_id=usuario["id"])
        recarregar_com_feedback('Obrigado pela sua avaliação!')


def _aba_portal_conhecimento():
    st.caption("Consulte as orientações disponíveis antes de abrir um chamado. Talvez você consiga resolver aqui mesmo.")

    artigos = listar_artigos()
    if not artigos:
        st.info("A Central de ajuda ainda não possui orientações disponíveis.")
        return

    col_busca, col_categoria = st.columns([2.4, 1])
    with col_busca:
        termo_busca = st.text_input(
            "🔍 Pesquisar orientação",
            placeholder="Ex.: senha bloqueada, impressora, wi-fi, e-mail não envia...",
            key="busca_portal_artigos",
        ).strip().lower()
    with col_categoria:
        categorias_disponiveis = ["Todas"] + sorted({a["categoria"] for a in artigos})
        categoria_filtro = st.selectbox("Categoria", categorias_disponiveis, key="filtro_categoria_artigos")
    with st.expander("Refinar a busca", expanded=False):
        dispositivo = st.text_input("Dispositivo", placeholder="Notebook, celular, impressora").strip().lower()
        servico = st.text_input("Serviço", placeholder="E-mail, VPN, Wi-Fi").strip().lower()
        sintoma = st.text_input("Sintoma", placeholder="Erro, lento, bloqueado").strip().lower()

    def _artigo_corresponde(artigo):
        if categoria_filtro != "Todas" and artigo["categoria"] != categoria_filtro:
            return False
        termos = " ".join(filter(None, [termo_busca, dispositivo, servico, sintoma])).split()
        if not termos:
            return True
        alvo = " ".join([
            artigo["titulo"],
            artigo["resumo"],
            artigo["categoria"],
            " ".join(artigo["tags"]),
            artigo["corpo"],
        ]).lower()
        return all(palavra in alvo for palavra in termos)

    artigos_filtrados = [a for a in artigos if _artigo_corresponde(a)]

    st.caption(f"{len(artigos_filtrados)} de {len(artigos)} orientação(ões)")

    if not artigos_filtrados:
        st.info("Nenhuma orientação encontrada. Tente outro termo ou use o assistente pelo menu do portal.")
        return

    for artigo in artigos_filtrados:
        with st.expander(artigo["titulo"]):
            st.caption(f"{artigo['categoria']} · {artigo['resumo']}")
            if artigo["tags"]:
                st.caption(" · ".join(artigo["tags"][:8]))


            _renderizar_secoes_artigo(artigo["corpo"])


def tela_usuario(usuario):
    if not usuario_tem_permissao(usuario["id"], "chamados.visualizar_proprios"):
        st.error("Você não tem permissão para acessar o portal.")
        return
    injetar_css()
    cabecalho("Central de Chamados", f"Bem-vindo(a), {usuario['nome']}", "🎫")
    chamados_resolvidos = [
        chamado for chamado in listar_chamados(
            limite=50, usuario_id=usuario["id"], executor_id=usuario["id"],
        ) if chamado["status"] == "Resolvido"
    ]
    if chamados_resolvidos:
        numeros = ", ".join(f"#{chamado['id']}" for chamado in chamados_resolvidos[:4])
        complemento = "" if len(chamados_resolvidos) <= 4 else "…"
        st.warning(
            f"🔔 Você tem {len(chamados_resolvidos)} chamado(s) resolvido(s) aguardando sua confirmação: "
            f"{numeros}{complemento}. Acesse **Meus chamados ativos** para fechar ou solicitar reabertura."
        )

    pode_usar_ia = usuario_tem_permissao(usuario["id"], "ia.utilizar")
    pode_ver_conhecimento = usuario_tem_permissao(usuario["id"], "conhecimento.visualizar")
    opcoes_navegacao = []
    if pode_ver_conhecimento or pode_usar_ia:
        opcoes_navegacao.append("Central de ajuda")
    if pode_usar_ia:
        opcoes_navegacao.append("Abrir novo chamado")
    opcoes_navegacao += [
        "Meus chamados ativos",
        "Meus chamados fechados",
        "Meus chamados cancelados",
    ]
    if st.session_state.get("usuario_nav") not in opcoes_navegacao:
        st.session_state.usuario_nav = opcoes_navegacao[0]
    with st.sidebar:
        st.caption("Portal do usuário")
        navegacao = st.radio(
            "Seções do portal", opcoes_navegacao, key="usuario_nav", label_visibility="collapsed",
        )

    if navegacao == "Central de ajuda":
        boas_vindas(pode_usar_ia)
        if pode_ver_conhecimento:
            _aba_portal_conhecimento()
    elif navegacao == "Abrir novo chamado":
        _aba_abrir_chamado(usuario)
    elif navegacao == "Meus chamados ativos":
        _aba_meus_chamados(usuario, "ativos")
    elif navegacao == "Meus chamados fechados":
        _aba_meus_chamados(usuario, "fechados")
    else:
        _aba_meus_chamados(usuario, "cancelados")


def _aba_abrir_chamado(usuario):
    if not usuario_tem_permissao(usuario["id"], "ia.utilizar"):
        st.error("Você não tem permissão para usar o assistente.")
        return
    if "chat_mensagens" not in st.session_state:
        st.session_state.chat_mensagens = [
            {"role": "assistant", "content": "Olá! Como posso ajudar? Você pode tirar uma dúvida ou descrever um problema."}
        ]
    if "chat_resultado_final" not in st.session_state:
        st.session_state.chat_resultado_final = None
    contexto_conversa(st.session_state.chat_resultado_final)

    def reiniciar_conversa():
        st.session_state.chat_mensagens = [
            {"role": "assistant", "content": "Olá! Como posso ajudar? Você pode tirar uma dúvida ou descrever um problema."}
        ]
        st.session_state.chat_resultado_final = None

    with st.container(border=True):
        for msg in st.session_state.chat_mensagens:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg.get("fontes"):
                    st.caption("Fonte: artigo oficial — " + ", ".join(f["titulo"] for f in msg["fontes"]))
                if msg.get("atendimento_ia_id"):
                    with st.expander("Avaliar esta orientação"):
                        with st.form(f"feedback_orientacao_{msg['atendimento_ia_id']}"):
                            nota_orientacao = st.select_slider("Utilidade", options=[1, 2, 3, 4, 5], value=3)
                            comentario_orientacao = st.text_area("Comentário opcional", max_chars=2000)
                            enviar_feedback_orientacao = st.form_submit_button("Enviar avaliação")
                        if enviar_feedback_orientacao:
                            registrar_feedback_atendimento_ia(msg["atendimento_ia_id"], nota_orientacao, comentario_orientacao, usuario["id"])
                            st.success("Avaliação registrada.")

        if st.session_state.chat_resultado_final is None:
            entrada = st.chat_input("Digite sua resposta...")
            if entrada:
                st.session_state.chat_mensagens.append({"role": "user", "content": entrada})

                with st.spinner("A IA está processando..."):
                    mensagens_usuario = [m for m in st.session_state.chat_mensagens if m["role"] == "user"]
                    if len(mensagens_usuario) == 1 and identificar_intencao(entrada) == "duvida":
                        duvida = responder_duvida(entrada)
                        resultado = {"acao": "orientar", **duvida}
                    else:
                        resultado = conversar_coleta(st.session_state.chat_mensagens)

                if resultado["acao"] in {"orientar", "perguntar"}:
                    registro_ia = salvar_atendimento_ia(usuario["id"], resultado.get("metadados_ia")) if resultado["acao"] == "orientar" else None
                    st.session_state.chat_mensagens.append({"role": "assistant", "content": resultado["mensagem"], "fontes": resultado.get("fontes", []), "atendimento_ia_id": registro_ia})
                    st.rerun()
                elif resultado["acao"] == "solucionar":
                    atendimento_ia_id = salvar_atendimento_ia(usuario["id"], resultado.get("metadados_ia"))
                    st.session_state.chat_mensagens.append({"role": "assistant", "content": resultado["mensagem"], "fontes": resultado.get("fontes", [])})
                    st.session_state.chat_resultado_final = {
                        "status": "solucao_sugerida",
                        "atendimento_ia_id": atendimento_ia_id,
                        "titulo": resultado["titulo"],
                        "descricao": resultado["descricao"],
                        "solucao": resultado["solucao"],
                        "fontes": resultado.get("fontes", []),
                    }
                    st.rerun()
                else:
                    st.session_state.chat_mensagens.append({
                        "role": "assistant",
                        "content": resultado.get("mensagem") if resultado.get("restricao_seguranca") else "Preparei os dados do chamado. Revise-os abaixo e confirme a abertura quando estiver tudo correto.",
                        "fontes": resultado.get("fontes", []),
                    })
                    st.session_state.chat_resultado_final = {
                        "status": "aguardando_confirmacao",
                        "titulo": resultado["titulo"],
                        "descricao": resultado["descricao"],
                    }
                    st.rerun()

        else:
            resultado = st.session_state.chat_resultado_final
            if resultado.get("status") == "solucao_sugerida":
                st.info("Encontrei uma possível solução com base nos dados informados.")
                st.markdown("##### Solução sugerida")
                st.markdown(resultado["solucao"])
                if resultado.get("fontes"):
                    st.caption("Base da orientação: artigo oficial — " + ", ".join(f["titulo"] for f in resultado["fontes"]))
                st.caption("Siga apenas os passos indicados. Se não resolver, você poderá abrir o chamado com os dados já coletados.")

                with st.expander("Avaliar esta orientação"):
                    with st.form(f"feedback_ia_{resultado['atendimento_ia_id']}"):
                        nota = st.select_slider("Utilidade da orientação", options=[1, 2, 3, 4, 5], value=3)
                        comentario = st.text_area("Comentário opcional", max_chars=2000)
                        enviar_feedback = st.form_submit_button("Enviar avaliação")
                    if enviar_feedback:
                        registrar_feedback_atendimento_ia(resultado["atendimento_ia_id"], nota, comentario, usuario["id"])
                        st.success("Avaliação registrada.")

                col_resolvido, col_abrir = st.columns(2)
                with col_resolvido:
                    resolvido = st.button("A solução resolveu o problema", type="primary", width="stretch")
                with col_abrir:
                    abrir_chamado = st.button("Não resolveu — abrir chamado", width="stretch")

                if resolvido:
                    registrar_resultado_atendimento_ia(resultado["atendimento_ia_id"], "Resolvido", usuario_id=usuario["id"])
                    st.session_state.chat_mensagens.append({
                        "role": "assistant",
                        "content": "Ótimo! Fico feliz que o problema tenha sido resolvido."
                    })
                    st.session_state.chat_resultado_final = {"status": "resolvido_pelo_usuario"}
                    st.rerun()
                if abrir_chamado:
                    st.session_state.chat_resultado_final = {
                        "status": "aguardando_confirmacao",
                        "atendimento_ia_id": resultado["atendimento_ia_id"],
                        "titulo": resultado["titulo"],
                        "descricao": resultado["descricao"],
                    }
                    st.rerun()

            elif resultado.get("status") == "aguardando_confirmacao":
                if not usuario_tem_permissao(usuario["id"], "chamados.abrir"):
                    st.info("Seu perfil permite consultar o assistente, mas não abrir chamados. Solicite acesso à administração.")
                    return
                st.info("Confira ou ajuste os dados. O chamado só será aberto após sua confirmação.")
                with st.form("form_confirmar_abertura"):
                    titulo = st.text_input("Título", value=resultado["titulo"], max_chars=255)
                    descricao = st.text_area("Descrição", value=resultado["descricao"], height=180)
                    confirmar = st.form_submit_button("Confirmar e abrir chamado", type="primary")

                _, col_nova = st.columns(2)
                with col_nova:
                    nova_conversa = st.button("Iniciar nova conversa", width="stretch")

                if confirmar:
                    if not titulo.strip() or not descricao.strip():
                        st.error("Preencha o título e a descrição antes de abrir o chamado.")
                    else:
                        with st.spinner("Classificando e abrindo o chamado..."):
                            classificacao = classificar_chamado(titulo.strip(), descricao.strip())
                            chamado_id = salvar_chamado(
                                titulo=classificacao.get("titulo_resumido") or titulo.strip(),
                                descricao=classificacao.get("descricao_padronizada") or descricao.strip(),
                                categoria=classificacao.get("categoria"),
                                urgencia=classificacao.get("urgencia"),
                                sla_resposta=classificacao.get("tempo_sla_resposta"),
                                sla_resolucao=classificacao.get("tempo_sla_resolucao"),
                                equipe_destino=classificacao.get("equipe_destino"),
                                confiabilidade=classificacao.get("confiabilidade"),
                                usuario_id=usuario["id"],
                                metadados_ia=classificacao.get("metadados_ia"),
                            )
                            if resultado.get("atendimento_ia_id"):
                                registrar_resultado_atendimento_ia(
                                    resultado["atendimento_ia_id"], "Nao resolvido", chamado_id, usuario["id"],
                                )
                        st.session_state.chat_resultado_final = {
                            "status": "registrado", "id": chamado_id, **classificacao,
                        }
                        st.rerun()
                if nova_conversa:
                    reiniciar_conversa()
                    st.rerun()

            elif resultado.get("status") == "registrado":
                st.success(f"Chamado #{resultado['id']} registrado com sucesso!")
                st.write(f"**Equipe responsável:** {resultado.get('equipe_destino') or 'A definir'}")
                st.caption(f"Categoria: {resultado.get('categoria') or 'Não informada'} · Urgência: {resultado.get('urgencia') or 'Não informada'}")
                st.caption("Consulte os prazos vigentes e as próximas atualizações no acompanhamento do chamado.")
                st.button("Acompanhar meu chamado", type="primary", on_click=acompanhar_chamado,
                          args=(resultado["id"],), width="stretch")
                if st.button("Iniciar nova conversa"):
                    reiniciar_conversa()
                    st.rerun()

            else:
                st.success("Problema resolvido sem necessidade de abrir chamado.")
                if st.button("Iniciar nova conversa", type="primary"):
                    reiniciar_conversa()
                    st.rerun()

    if st.session_state.chat_resultado_final is None:
        if st.button("Iniciar nova conversa", key="nova_conversa_durante_atendimento"):
            reiniciar_conversa()
            st.rerun()


def _aba_meus_chamados(usuario, grupo):
    chamados = listar_chamados(limite=50, usuario_id=usuario["id"], executor_id=usuario["id"])

    if grupo == "ativos":
        chamados = [c for c in chamados if c["status"] not in STATUS_ENCERRADOS]
        titulo_grupo = "ativo(s)"
    elif grupo == "fechados":
        chamados = [c for c in chamados if c["status"] == "Fechado"]
        titulo_grupo = "fechado(s)"
    else:
        chamados = [c for c in chamados if c["status"] == "Cancelado"]
        titulo_grupo = "cancelado(s)"

    busca = st.text_input("Buscar em meus chamados", placeholder="Número ou título", key=f"busca_meus_{grupo}").strip().casefold().lstrip("#")
    if busca:
        chamados = [c for c in chamados if busca in f"{c['id']} {c['titulo']}".casefold()]
    if not chamados:
        st.info(f"Você não possui chamados {titulo_grupo}.")
        return

    st.caption(f"{len(chamados)} chamado(s) {titulo_grupo} — clique em um para ver detalhes.")

    lista_col = st.expander("Lista de chamados · selecione para ver detalhes", expanded=st.session_state.chamado_aberto_usuario is None)
    detalhe_col = st.container()

    with lista_col:
        for c in paginar_registros(chamados, f"pagina_meus_{grupo}"):
            selecionado = st.session_state.chamado_aberto_usuario == c["id"]
            estado_sla = sla.status_sla(c)
            contexto = f"Responsável: {c.get('nome_analista') or 'Aguardando atribuição'}"
            if exibir_cartao_chamado(c, estado_sla, contexto, selecionado, f"ver_{c['id']}"):
                st.session_state.chamado_aberto_usuario = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_aberto_usuario
        if chamado_id_sel is None:
            st.info("Selecione um chamado na lista acima.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
        if not chamado or chamado["usuario_id"] != usuario["id"]:
            st.warning("Chamado não encontrado.")
            return
        pertence_ao_grupo = (
            (grupo == "ativos" and chamado["status"] not in STATUS_ENCERRADOS)
            or (grupo == "fechados" and chamado["status"] == "Fechado")
            or (grupo == "cancelados" and chamado["status"] == "Cancelado")
        )
        if not pertence_ao_grupo:
            st.info("Selecione um chamado desta lista.")
            return

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
            exibir_status_chamado(chamado["status"])
            st.caption(f"Urgência: {rotulo(chamado['urgencia'])}")
            st.write(chamado["descricao"])

            st.markdown(painel_metricas_chamado(chamado))
            st.caption(f"Equipe: {chamado.get('equipe_destino') or '—'}")
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))
            st.caption(f"Analista responsável: {chamado.get('nome_analista') or 'Aguardando atribuição'}")
            st.info(f"**Status atual:** {chamado['status']}. {_quem_precisa_agir(chamado)}")
            if chamado["status"] == "Cancelado":
                st.warning(f"Cancelado: {chamado.get('motivo_cancelamento') or 'Não informado'}. O registro permanece disponível apenas para consulta e auditoria.")

        if chamado["status"] == "Novo" and chamado.get("analista_id") is None and usuario_tem_permissao(usuario["id"], "chamados.cancelar_proprios"):
            st.divider()
            chave_formulario = f"mostrar_cancelamento_{chamado['id']}"
            if not st.session_state.get(chave_formulario):
                if st.button("Cancelar chamado", key=f"cancelar_{chamado['id']}"):
                    st.session_state[chave_formulario] = True
                    st.rerun()
            else:
                with st.form(f"form_cancelar_{chamado['id']}"):
                    st.warning("Ao cancelar, o chamado será mantido somente para auditoria.")
                    motivo = st.selectbox("Motivo do cancelamento", MOTIVOS_CANCELAMENTO)
                    confirmar_cancelamento = st.form_submit_button("Confirmar cancelamento", type="primary")
                    voltar = st.form_submit_button("Voltar")

                if voltar:
                    st.session_state[chave_formulario] = False
                    st.rerun()
                if confirmar_cancelamento:
                    try:
                        cancelar_chamado_sem_atribuicao(chamado["id"], motivo, autor_id=usuario["id"])
                        st.session_state[chave_formulario] = False
                        recarregar_com_feedback('Chamado cancelado. Ele não será encaminhado para atendimento e ficará disponível apenas para consulta e auditoria.')
                    except ValueError as erro:
                        st.error(str(erro))

        elif chamado["status"] == "Resolvido" and usuario_tem_permissao(usuario["id"], "chamados.confirmar_resolucao"):
            st.divider()
            st.info("O analista marcou este chamado como resolvido. Confirme o resultado ou solicite a reabertura.")
            if chamado.get("diagnostico_final"):
                st.markdown("##### Diagnóstico e solução registrados")
                st.write(f"**Diagnóstico:** {chamado['diagnostico_final']}")
                st.write(f"**Solução:** {chamado.get('solucao_final') or 'Não informada'}")
            with st.form(f"form_confirmar_resolucao_{chamado['id']}"):
                confirmar_solucao = st.form_submit_button("Confirmar solução", type="primary")
            if confirmar_solucao:
                try:
                    confirmar_resolucao_usuario(chamado["id"], usuario["id"])
                    recarregar_com_feedback('Solução confirmada. Chamado fechado.')
                except ValueError as erro:
                    st.error(str(erro))
            with st.form(f"form_reabrir_{chamado['id']}"):
                motivo_reabertura = st.text_area("Motivo da reabertura", max_chars=500)
                reabrir = st.form_submit_button("Solicitar reabertura")
            if reabrir:
                try:
                    reabrir_chamado_usuario(chamado["id"], usuario["id"], motivo_reabertura)
                    recarregar_com_feedback('Chamado reaberto e devolvido para atendimento.')
                except ValueError as erro:
                    st.error(str(erro))

        conversa, arquivos, historico = st.tabs(["Conversa", "Anexos", "Histórico"])
        with conversa:
            painel_conversa_chamado(chamado, usuario, "usuario", key_prefix="usr")
        with arquivos:
            painel_anexos_chamado(chamado, usuario, key_prefix="usr")
        with historico:
            linha_do_tempo_chamado(chamado, usuario["id"])
        painel_pesquisa_satisfacao(chamado, usuario)


def tela_analista(usuario):
    if not usuario_tem_permissao(usuario["id"], "chamados.visualizar_fila"):
        st.error("Você não tem permissão para acessar a fila de atendimento.")
        return
    injetar_css()
    cabecalho("Central de Serviços — Analista", f"{usuario['nome']} · Gestão de Incidentes")

    opcoes_navegacao = ["Fila ativa", "Histórico (fechados)", "Cancelados"]
    if st.session_state.get("analista_nav") not in opcoes_navegacao:
        st.session_state.analista_nav = opcoes_navegacao[0]
    with st.sidebar:
        st.caption("Atendimento")
        navegacao = st.radio(
            "Seções de atendimento", opcoes_navegacao, key="analista_nav", label_visibility="collapsed",
        )

    if navegacao == "Histórico (fechados)":
        chamados = []
        pagina_consulta = 0
        while True:
            lote = listar_chamados(limite=200, executor_id=usuario["id"],
                                   pagina=pagina_consulta, status="Fechado")
            chamados.extend(lote)
            if len(lote) < 200:
                break
            pagina_consulta += 1
    else:
        chamados = listar_chamados(limite=200, executor_id=usuario["id"])

    if navegacao == "Fila ativa":
        _aba_fila_ativa_analista(usuario, chamados)
    elif navegacao == "Histórico (fechados)":
        _aba_historico_analista(usuario, chamados)
    else:
        _aba_cancelados_analista(usuario, chamados)


def _aba_fila_ativa_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] not in STATUS_ENCERRADOS]
    ordem_urgencia = {"Critica": 0, "Alta": 1, "Media": 2, "Baixa": 3}
    prioridade_sla = {"Violado": 0, "Em risco": 1, "Dentro do prazo": 2, "Pausado": 3, "Cumprido": 4}
    chamados.sort(key=lambda c: (prioridade_sla.get(sla.pior_status(sla.status_sla(c)), 5), ordem_urgencia.get(c.get("urgencia"), 4), c.get("criado_em")))

    total = len(chamados)
    novos = sum(1 for c in chamados if c["status"] == "Novo")
    em_andamento = sum(1 for c in chamados if c["status"] == "Em Andamento")
    meus = sum(1 for c in chamados if c.get("analista_id") == usuario["id"])

    indicadores([
        ("Chamados ativos", total, "Recorte carregado: todos exceto fechados e cancelados."),
        ("Novos", novos, "Chamados do recorte ainda no estado Novo."),
        ("Em andamento", em_andamento, "Chamados do recorte no estado Em Andamento."),
        ("Atribuídos a mim", meus, "Ativos do recorte sob sua responsabilidade."),
    ])
    st.caption("Fila carregada: até 200 registros mais recentes. Ordenação por situação de SLA, urgência e abertura.")
    # Migra apenas valores que não pertencem à fila ativa antes de criar o widget.
    if "filtro_status_ativa" in st.session_state:
        st.session_state.filtro_status_ativa = [valor for valor in st.session_state.filtro_status_ativa
                                               if valor in {"Novo", "Em Andamento", "Em Espera", "Resolvido"}]
    filtros = filtros_fila(chamados)
    chamados_filtrados = filtrar_fila(chamados, filtros, usuario["id"])
    if resumo_filtros(filtros):
        st.caption("Filtros ativos: " + resumo_filtros(filtros))

    st.caption(f"{len(chamados_filtrados)} de {len(chamados)} chamado(s) exibido(s).")

    fila_col, detalhe_col = st.columns([1, 1.8], gap="large")

    with fila_col:
        st.markdown("##### Fila de chamados")
        if not chamados_filtrados:
            st.caption("Nenhum chamado com os filtros selecionados.")
        for c in paginar_registros(chamados_filtrados, "pagina_fila_ativa"):
            selecionado = st.session_state.chamado_selecionado_analista == c["id"]
            estado_sla = sla.status_sla(c)
            responsavel = c.get("nome_analista") or "Sem atribuição"
            contexto = f"Solicitante: {c.get('nome_usuario') or '—'} · Responsável: {responsavel}"
            if cartao_fila_compacto(c, estado_sla, contexto, selecionado, f"sel_{c['id']}"):
                st.session_state.chamado_selecionado_analista = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_selecionado_analista
        if chamado_id_sel is None:
            st.info("Selecione um chamado na fila para atender.")
            return
        if chamado_id_sel not in {c["id"] for c in chamados_filtrados}:
            st.info("Selecione um chamado nos resultados atuais. A seleção anterior está fora dos filtros aplicados.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
        if not chamado:
            st.warning("Chamado não encontrado.")
            st.session_state.chamado_selecionado_analista = None
            return

        with st.container(border=True):
            topo_esq, topo_dir = st.columns([3, 1])
            with topo_esq:
                st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
                exibir_status_chamado(chamado["status"])
                st.caption(f"Urgência: {rotulo(chamado['urgencia'])}")
            with topo_dir:
                analista_atribuido = chamado.get("analista_id")
                ja_atribuido_a_mim = analista_atribuido == usuario["id"]
                if analista_atribuido is None and chamado["status"] == "Novo":
                    if usuario_tem_permissao(usuario["id"], "chamados.assumir") and st.button("Assumir chamado", type="primary", width="stretch"):
                        try:
                            atribuir_chamado(chamado["id"], usuario["id"])
                            recarregar_com_feedback("Chamado atribuído a você. Envie a primeira resposta ao solicitante.")
                        except ValueError as erro:
                            st.error(str(erro))
                    if usuario_tem_permissao(usuario["id"], "chamados.cancelar_fila") and st.button("Cancelar chamado", key=f"cancelar_analista_{chamado['id']}", width="stretch"):
                        st.session_state[f"mostrar_cancelamento_analista_{chamado['id']}"] = True
                        st.rerun()
                else:
                    if ja_atribuido_a_mim:
                        st.success("Você está atendendo")
                    else:
                        st.warning(f"Atribuído a {chamado.get('nome_analista') or 'outro analista'}")

            st.write(chamado["descricao"])

            estado_sla = sla.status_sla(chamado)
            indicadores_destaque_chamado(chamado, estado_sla)
            bloco_sla_detalhe(chamado, estado_sla)
            with st.expander("Informações da classificação assistida"):
                st.write(f"Confiança informada pela IA: {chamado.get('confiabilidade') or 'Não informada'}")
            st.caption(f"Solicitante: {chamado.get('nome_usuario') or '-'} · Aberto em {chamado.get('criado_em').strftime('%d/%m/%Y %H:%M:%S')}")

            if ja_atribuido_a_mim and chamado["status"] == "Em Andamento" and not chamado.get("primeira_resposta_em") and usuario_tem_permissao(usuario["id"], "chamados.responder_atribuidos"):
                st.warning("A primeira resposta ainda não foi registrada. Ela é obrigatória antes de resolver o chamado e inicia o indicador de atendimento.")
                with st.form(f"form_primeira_resposta_{chamado['id']}"):
                    primeira_resposta = st.text_area("Primeira resposta ao solicitante", placeholder="Confirme que está analisando e informe o próximo passo.", max_chars=4000)
                    enviar_primeira_resposta = st.form_submit_button("Enviar primeira resposta", type="primary")
                if enviar_primeira_resposta:
                    if not primeira_resposta.strip():
                        st.error("Escreva uma mensagem antes de enviar.")
                    else:
                        enviar_mensagem_chamado(chamado["id"], usuario["id"], usuario["nome"], "analista", primeira_resposta.strip())
                        recarregar_com_feedback('Primeira resposta registrada e enviada ao solicitante.')

            if (
                ja_atribuido_a_mim
                and usuario_tem_permissao(usuario["id"], "chamados.registrar_resolucao")
                and chamado["status"] in ("Em Andamento", "Em Espera")
                and chamado.get("primeira_resposta_em")
            ):
                st.divider()
                st.caption("A primeira resposta foi registrada. Você pode continuar a conversa ou registrar a resolução para que o solicitante confirme o resultado. A aprovação para a base interna da IA é uma decisão separada e opcional.")
                with st.expander("Registrar diagnóstico e solução", expanded=False):
                    with st.form(f"form_resolucao_{chamado['id']}"):
                        st.markdown("##### Classificação final")
                        st.caption(
                            "Sugestão da IA: "
                            f"{chamado.get('categoria_ia') or chamado.get('categoria') or '—'} · "
                            f"{chamado.get('urgencia_ia') or chamado.get('urgencia') or '—'} · "
                            f"{chamado.get('equipe_ia') or chamado.get('equipe_destino') or '—'}"
                        )
                        coluna_categoria, coluna_urgencia, coluna_equipe = st.columns(3)
                        categorias = ["Acesso", "Software", "Hardware", "Rede", "Outros"]
                        urgencias = ["Baixa", "Media", "Alta", "Critica"]
                        equipes = ["Suporte", "Software", "Hardware", "Redes"]
                        with coluna_categoria:
                            categoria_final = st.selectbox(
                                "Categoria final", categorias,
                                index=categorias.index(chamado.get("categoria_ia") or chamado.get("categoria") or "Outros"),
                            )
                        with coluna_urgencia:
                            urgencia_final = st.selectbox(
                                "Urgência final", urgencias,
                                index=urgencias.index(chamado.get("urgencia_ia") or chamado.get("urgencia") or "Media"),
                            )
                        with coluna_equipe:
                            equipe_final = st.selectbox(
                                "Equipe final", equipes,
                                index=equipes.index(chamado.get("equipe_ia") or chamado.get("equipe_destino") or "Suporte"),
                            )
                        diagnostico = st.text_area(
                            "Diagnóstico identificado", height=75,
                            placeholder="Ex.: A senha da conta havia expirado.",
                        )
                        solucao = st.text_area(
                            "Solução aplicada", height=90,
                            placeholder="Ex.: Senha redefinida e Outlook reconfigurado.",
                        )
                        compartilhar = st.checkbox(
                            "Aprovar este caso como referência interna para a IA",
                            value=False,
                            help="Opcional. A decisão é exclusiva do analista responsável; o conteúdo é anonimizado e não é exibido aos solicitantes.",
                        )
                        marcar_resolvido = st.form_submit_button("Registrar resolução", type="primary", width="stretch")
                if marcar_resolvido:
                    try:
                        registrar_resolucao_chamado(
                            chamado["id"], usuario["id"], diagnostico, solucao, compartilhar,
                            categoria_final, urgencia_final, equipe_final,
                        )
                        recarregar_com_feedback('Resolução registrada. O solicitante poderá confirmar ou solicitar reabertura.')
                    except ValueError as erro:
                        st.error(str(erro))
            elif ja_atribuido_a_mim and chamado["status"] == "Em Espera":
                st.info("Aguardando a resposta do solicitante. Você ainda pode enviar mensagens ou registrar a resolução, se o atendimento já estiver concluído.")
            elif ja_atribuido_a_mim and chamado["status"] == "Resolvido":
                st.info("Aguardando a confirmação do solicitante para fechar ou reabrir o chamado.")

            if ja_atribuido_a_mim and chamado["status"] not in STATUS_ENCERRADOS and usuario_tem_permissao(usuario["id"], "chamados.alterar_status"):
                with st.expander("Transferir ou escalar chamado"):
                    analistas = [item for item in listar_analistas_para_transferencia(usuario["id"]) if item["id"] != usuario["id"]]
                    if analistas:
                        por_id = {item["id"]: item for item in analistas}
                        with st.form(f"form_transferir_{chamado['id']}"):
                            novo_analista = st.selectbox("Novo responsável", list(por_id), format_func=lambda item: por_id[item]["nome"])
                            motivo_transferencia = st.text_area("Motivo da transferência", max_chars=500)
                            transferir = st.form_submit_button("Transferir")
                        if transferir:
                            try:
                                transferir_chamado(chamado["id"], novo_analista, motivo_transferencia, usuario["id"])
                                recarregar_com_feedback('Chamado transferido.')
                            except (ValueError, PermissionError) as erro:
                                st.error(str(erro))
                    with st.form(f"form_escalar_{chamado['id']}"):
                        nova_urgencia = st.selectbox("Nova urgência", ["Baixa", "Media", "Alta", "Critica"], index=["Baixa", "Media", "Alta", "Critica"].index(chamado["urgencia"]))
                        nova_equipe = st.selectbox("Nova equipe", ["Suporte", "Software", "Hardware", "Redes"], index=["Suporte", "Software", "Hardware", "Redes"].index(chamado.get("equipe_destino") or "Suporte"))
                        motivo_escalonamento = st.text_area("Motivo do escalonamento", max_chars=500)
                        escalar = st.form_submit_button("Escalonar")
                    if escalar:
                        try:
                            escalar_chamado(chamado["id"], nova_urgencia, nova_equipe, motivo_escalonamento, usuario["id"])
                            recarregar_com_feedback('Chamado escalado.')
                        except (ValueError, PermissionError) as erro:
                            st.error(str(erro))

        chave_cancelamento_analista = f"mostrar_cancelamento_analista_{chamado['id']}"
        if chamado.get("analista_id") is None and chamado["status"] == "Novo" and usuario_tem_permissao(usuario["id"], "chamados.cancelar_fila") and st.session_state.get(chave_cancelamento_analista):
            with st.form(f"form_cancelar_analista_{chamado['id']}"):
                st.warning("O chamado será cancelado sem ser atribuído e mantido para auditoria.")
                motivo_analista = st.selectbox(
                    "Motivo do cancelamento",
                    MOTIVOS_CANCELAMENTO_ANALISTA,
                    key=f"motivo_cancelamento_analista_{chamado['id']}",
                )
                confirmar_cancelamento_analista = st.form_submit_button("Confirmar cancelamento", type="primary")
                voltar_cancelamento_analista = st.form_submit_button("Voltar")

            if voltar_cancelamento_analista:
                st.session_state[chave_cancelamento_analista] = False
                st.rerun()
            if confirmar_cancelamento_analista:
                try:
                    cancelar_chamado_sem_atribuicao(chamado["id"], motivo_analista, autor_id=usuario["id"])
                    st.session_state[chave_cancelamento_analista] = False
                    recarregar_com_feedback('Chamado cancelado.')
                except ValueError as erro:
                    st.error(str(erro))

        if chamado.get("analista_id") != usuario["id"]:
            st.info("Atribua este chamado a você para enviar mensagens, anexos ou executar ações de atendimento.")
            return

        conversa, arquivos, historico = st.tabs(["Conversa", "Anexos", "Histórico"])
        with conversa:
            painel_conversa_chamado(chamado, usuario, "analista", key_prefix="ana")
        with arquivos:
            painel_anexos_chamado(chamado, usuario, key_prefix="ana")
        with historico:
            linha_do_tempo_chamado(chamado, usuario["id"])


def _aba_historico_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] == "Fechado"]
    chamados.sort(key=lambda c: (c.get("criado_em") or datetime.min, c["id"]), reverse=True)
    st.subheader("Histórico de chamados fechados")
    st.caption("Consulte por número, título ou solicitante. Os chamados aparecem do mais recente ao mais antigo pela abertura.")

    if not chamados:
        st.info("Nenhum chamado fechado ainda.")
        return

    total_fechados = len(chamados)
    dentro_prazo = sum(
        1 for c in chamados
        if sla.status_sla(c)["resposta"]["status"] == "Cumprido"
        and sla.status_sla(c)["resolucao"]["status"] == "Cumprido"
    )
    taxa_cumprimento = f"{(dentro_prazo / total_fechados * 100):.0f}%" if total_fechados else "—"

    with st.expander("Indicadores do histórico"):
        m1, m2, m3 = st.columns(3)
        m1.metric("Total fechados", total_fechados)
        m2.metric("SLA cumprido", dentro_prazo)
        m3.metric("Taxa de cumprimento", taxa_cumprimento)
        st.caption("Indicadores do histórico completo, antes dos filtros. A taxa considera somente chamados fechados. "
                   "Cancelados ficam em uma lista separada e não compõem este indicador.")

    with st.container(border=True):
        busca = st.text_input("Buscar chamado", placeholder="Número, título ou solicitante", key="busca_historico",
                              on_change=reiniciar_consulta_historico).strip().casefold().lstrip("#")
        filtro_col1, filtro_col2 = st.columns([1.2, 1], vertical_alignment="bottom")
        filtro_urgencia_hist = filtro_col1.multiselect(
            "Urgência", options=["Critica", "Alta", "Media", "Baixa"], format_func=rotulo,
            key="filtro_urgencia_hist", on_change=reiniciar_consulta_historico)
        somente_meus_hist = filtro_col2.checkbox("Somente atendidos por mim", key="somente_meus_hist",
                                                on_change=reiniciar_consulta_historico)

    chamados_filtrados = chamados
    if filtro_urgencia_hist:
        chamados_filtrados = [c for c in chamados_filtrados if c["urgencia"] in filtro_urgencia_hist]
    if somente_meus_hist:
        chamados_filtrados = [c for c in chamados_filtrados if c.get("analista_id") == usuario["id"]]

    if busca:
        chamados_filtrados = [c for c in chamados_filtrados if busca in f"{c['id']} {c['titulo']} {c.get('nome_usuario') or ''}".casefold()]

    st.caption(f"{len(chamados_filtrados)} chamado(s) encontrado(s) de {total_fechados} fechados")
    lista_col = st.container()
    # Reserva a lista antes de montar o rodapé, que decide qual página renderizar.
    registros_pagina = paginar_historico(chamados_filtrados)

    with lista_col:
        if not chamados_filtrados:
            st.info("Nenhum chamado fechado com os filtros selecionados. Ajuste a busca ou a urgência.")
        for c in registros_pagina:
            selecionado = st.session_state.get("chamado_selecionado_historico") == c["id"]
            if cartao_historico_compacto(c, selecionado):
                st.session_state.chamado_selecionado_historico = c["id"]
                st.rerun()

    with st.container():
        chamado_id_sel = st.session_state.get("chamado_selecionado_historico")
        if chamado_id_sel is None:
            return
        if chamado_id_sel not in {c["id"] for c in registros_pagina}:
            st.session_state.chamado_selecionado_historico = None
            return

        st.divider()
        st.button("Fechar detalhes", key="historico_fechar_detalhes", on_click=fechar_detalhe_historico)
        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
        if not chamado or chamado["status"] != "Fechado":
            st.warning("Chamado não encontrado no histórico.")
            st.session_state.chamado_selecionado_historico = None
            return

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
            exibir_status_chamado(chamado["status"])
            st.caption(f"Urgência: {rotulo(chamado['urgencia'])}")
            st.write(chamado["descricao"])

            st.markdown(painel_metricas_chamado(chamado))

            st.caption(f"Categoria: {chamado.get('categoria') or '—'} · Confiança da classificação: {chamado.get('confiabilidade') or '—'}")
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))

            st.caption(
                f"Solicitante: {chamado.get('nome_usuario') or '—'} · "
                f"Atendido por: {chamado.get('nome_analista') or '—'}"
            )
            st.caption(
                f"Aberto em {sla.formatar_data(chamado.get('criado_em'))} · "
                f"Resolvido em {sla.formatar_data(chamado.get('resolvido_em'))}"
            )
            if chamado.get("diagnostico_final"):
                st.divider()
                st.markdown("##### Resolução técnica")
                st.write(f"**Diagnóstico:** {chamado['diagnostico_final']}")
                st.write(f"**Solução aplicada:** {chamado.get('solucao_final') or 'Não informada'}")

        st.markdown("#####  Histórico da conversa")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="hist")
        painel_anexos_chamado(chamado, usuario, key_prefix="hist")
        with st.expander("Decisões e alterações de status"):
            for evento in listar_historico_chamado(chamado["id"], usuario["id"]):
                st.caption(f"{sla.formatar_data(evento['criado_em'])} · {evento['tipo'].replace('_', ' ').title()} · {evento.get('autor_nome') or 'Sistema'}")


def _aba_cancelados_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] == "Cancelado"]
    if not chamados:
        st.info("Nenhum chamado cancelado ainda.")
        return

    st.metric("Total cancelados", len(chamados))
    st.caption("Cancelamentos são mantidos para auditoria e não impactam a taxa de cumprimento de SLA.")

    busca = st.text_input("Buscar chamado", placeholder="Número, título ou solicitante", key="busca_cancelados").strip().casefold().lstrip("#")
    if busca:
        chamados = [c for c in chamados if busca in f"{c['id']} {c['titulo']} {c.get('nome_usuario') or ''}".casefold()]

    lista_col = st.expander("Chamados cancelados", expanded=st.session_state.chamado_selecionado_cancelado is None)
    detalhe_col = st.container()
    with lista_col:
        st.markdown("##### Chamados cancelados")
        for c in paginar_registros(chamados, "pagina_cancelados"):
            selecionado = st.session_state.chamado_selecionado_cancelado == c["id"]
            estado_sla = sla.status_sla(c)
            contexto = f"Solicitante: {c.get('nome_usuario') or '—'} · Responsável: {c.get('nome_analista') or 'Sem atribuição'}"
            if exibir_cartao_chamado(c, estado_sla, contexto, selecionado, f"cancel_{c['id']}"):
                st.session_state.chamado_selecionado_cancelado = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_selecionado_cancelado
        if chamado_id_sel is None:
            st.info("Selecione um chamado cancelado para consultar o registro.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
        if not chamado or chamado["status"] != "Cancelado":
            st.info("Selecione um chamado desta lista.")
            return

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
            exibir_status_chamado(chamado["status"])
            st.caption(f"Urgência: {rotulo(chamado['urgencia'])}")
            st.write(chamado["descricao"])
            st.markdown(painel_metricas_chamado(chamado))
            st.caption(
                f"Solicitante: {chamado.get('nome_usuario') or '—'} · "
                "SLA: não aplicável (cancelado pelo usuário)."
            )
            st.caption(f"Motivo do cancelamento: {chamado.get('motivo_cancelamento') or 'Não informado'}")

        st.markdown("##### Histórico da conversa")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="cancel_hist")
        painel_anexos_chamado(chamado, usuario, key_prefix="cancel_hist")
        with st.expander("Decisões e alterações de status"):
            for evento in listar_historico_chamado(chamado["id"], usuario["id"]):
                st.caption(f"{sla.formatar_data(evento['criado_em'])} · {evento['tipo'].replace('_', ' ').title()} · {evento.get('autor_nome') or 'Sistema'}")




def relatorio_usuarios(usuarios):
    st.markdown("### Relatório de usuários")
    st.caption("Distribuição das contas cadastradas por perfil de acesso.")
    dados = pd.DataFrame(usuarios)
    distribuicao = (
        dados["perfil_nome"].fillna("Sem perfil").value_counts()
        .rename_axis("Perfil").reset_index(name="Quantidade")
    ) if not dados.empty else pd.DataFrame({"Perfil": [], "Quantidade": []})

    metricas = st.columns(2)
    metricas[0].metric("Total de contas", int(distribuicao["Quantidade"].sum()))
    metricas[1].metric("Perfis em uso", int(len(distribuicao)))

    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        _exibir_grafico_barras(distribuicao, "Contas por perfil", "Perfil", "Quantidade")
    with tabela:
        exibir_tabela_tematica(distribuicao)


def relatorio_sla_desempenho(chamados):
    st.markdown("### Prazos de atendimento (SLA)")
    st.caption("Uma leitura rápida dos prazos prometidos para responder e resolver chamados. Cancelados não entram no cálculo.")
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados para calcular os indicadores de SLA.")
        return

    chamados_para_lista = dados.copy()
    dados = dados[dados["status"] != "Cancelado"].copy()
    dados["SLA resposta"] = [sla.status_sla(c)["resposta"]["status"] for c in dados.to_dict("records")]
    dados["SLA resolução"] = [sla.status_sla(c)["resolucao"]["status"] for c in dados.to_dict("records")]
    resolucoes_concluidas = dados[dados["resolvido_em"].notna()]
    resolucao_cumprida = int((resolucoes_concluidas["SLA resolução"] == "Cumprido").sum())
    taxa_resolucao = resolucao_cumprida / len(resolucoes_concluidas) * 100 if len(resolucoes_concluidas) else 0

    ativos = dados[~dados["status"].isin(STATUS_ENCERRADOS | {"Resolvido"})]
    atrasados = int((ativos["SLA resolução"] == "Violado").sum())
    em_risco = int((ativos["SLA resolução"] == "Em risco").sum())
    em_espera = int((ativos["status"] == "Em Espera").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Resoluções no prazo",
        f"{taxa_resolucao:.0f}%" if len(resolucoes_concluidas) else "Sem resoluções",
        f"{resolucao_cumprida} de {len(resolucoes_concluidas)} concluídas no prazo" if len(resolucoes_concluidas) else "Ainda não há chamados resolvidos",
    )
    c2.metric(
        "Atenção agora", f"{atrasados + em_risco} chamado(s)",
        f"{atrasados} atrasado(s) · {em_risco} perto do prazo",
    )
    c3.metric(
        "Em atendimento", len(ativos),
        f"{em_espera} aguardando retorno do solicitante",
    )

    if atrasados:
        st.error(f"Prioridade: há {atrasados} chamado(s) com prazo de resolução vencido.")
    elif em_risco:
        st.warning(f"Atenção: {em_risco} chamado(s) está(ão) próximo(s) do prazo de resolução.")
    else:
        st.success("Os chamados em atendimento estão dentro dos prazos configurados.")

    resumo = pd.DataFrame([
        {
            "Etapa": "Primeira resposta",
            "No prazo": int((dados["SLA resposta"].isin(["Cumprido", "Dentro do prazo"])).sum()),
            "Em risco": int((dados["SLA resposta"] == "Em risco").sum()),
            "Atrasado": int((dados["SLA resposta"] == "Violado").sum()),
        },
        {
            "Etapa": "Resolução",
            "No prazo": int((dados["SLA resolução"].isin(["Cumprido", "Dentro do prazo"])).sum()),
            "Em risco": int((dados["SLA resolução"] == "Em risco").sum()),
            "Atrasado": int((dados["SLA resolução"] == "Violado").sum()),
        },
    ])
    st.markdown("#### Situação dos prazos")
    exibir_tabela_tematica(resumo)

    st.markdown("#### Todos os chamados e situação atual")
    def situacao_chamado(chamado):
        status = chamado.get("status")
        if status == "Cancelado":
            return "Cancelado"
        if status == "Fechado":
            return "Fechado"
        if status == "Resolvido":
            return "Resolvido — aguardando confirmação"
        return "Aberto"

    def situacao_sla(chamado):
        if chamado.get("status") == "Cancelado":
            return "Não se aplica"
        return sla.status_sla(chamado)["resolucao"]["status"]

    visao_chamados = pd.DataFrame({
        "Chamado": [f"#{item['id']}" for item in chamados_para_lista.to_dict("records")],
        "Título": chamados_para_lista["titulo"].fillna("—"),
        "Situação": [situacao_chamado(item) for item in chamados_para_lista.to_dict("records")],
        "Status atual": chamados_para_lista["status"],
        "SLA de resolução": [situacao_sla(item) for item in chamados_para_lista.to_dict("records")],
        "Equipe": chamados_para_lista["equipe_destino"].fillna("—"),
    })
    visao_chamados["Ordem"] = visao_chamados["SLA de resolução"].map(
        {"Violado": 0, "Em risco": 1, "Dentro do prazo": 2, "Cumprido": 3, "Pausado": 4, "Não se aplica": 5}
    ).fillna(6)
    visao_chamados = visao_chamados.sort_values(["Ordem", "Chamado"]).drop(columns="Ordem")
    exibir_tabela_tematica(visao_chamados)


def relatorio_ia(chamados, admin):
    st.markdown("### Qualidade da classificação da IA")
    st.caption("As métricas de qualidade usam a amostra global disponível. A distribuição de confiança abaixo usa os chamados do recorte selecionado.")
    st.caption(
        "Taxas de acerto usam a classificação final validada por analista. A confiança textual "
        "do modelo é exibida apenas como contexto e não é uma métrica de qualidade."
    )
    qualidade = relatorio_qualidade_ia(admin["id"])
    classificacao = qualidade["classificacao"] or {}
    total_validado = int(classificacao.get("total") or 0)
    if total_validado:
        col_categoria, col_urgencia, col_equipe = st.columns(3)
        col_categoria.metric("Acerto de categoria", f"{100 * (classificacao.get('categoria_corretos') or 0) / total_validado:.1f}%")
        col_urgencia.metric("Acerto de urgência", f"{100 * (classificacao.get('urgencia_corretos') or 0) / total_validado:.1f}%")
        col_equipe.metric("Acerto de equipe", f"{100 * (classificacao.get('equipe_corretos') or 0) / total_validado:.1f}%")
    else:
        st.info("Ainda não há classificações finais humanas para medir acurácia.")
    orientacoes = qualidade["orientacoes"] or {}
    if orientacoes.get("total_feedback"):
        st.caption(f"Qualidade das orientações: nota média {float(orientacoes.get('nota_media') or 0):.1f}/5 em {orientacoes['total_feedback']} retorno(s).")
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados classificados pela IA para analisar.")
        return

    niveis = ["Alta", "Média", "Baixa", "Não informada"]
    confianca = (
        dados["confiabilidade"].fillna("Não informada").astype(str).str.strip()
        .replace({"Media": "Média", "media": "Média", "alta": "Alta", "baixa": "Baixa"})
    )
    distribuicao = confianca.value_counts().reindex(niveis, fill_value=0)
    total_classificado = int(distribuicao.sum())
    percentual_alta = distribuicao["Alta"] / total_classificado * 100 if total_classificado else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados classificados", total_classificado)
    c2.metric("Confiança alta", f"{percentual_alta:.1f}%", f"{distribuicao['Alta']} classificações")
    c3.metric("Confiança média", int(distribuicao["Média"]))
    c4.metric("Confiança baixa", int(distribuicao["Baixa"]))

    dados["Confiança da classificação"] = confianca
    resultados = resumir_por_situacao(dados.to_dict("records"), "Confiança da classificação",
                                       lambda c: c["Confiança da classificação"], grupos=niveis)
    exibir_grafico_situacao(resultados, "Confiança da classificação", "Distribuição da confiança da classificação")
    st.caption("Chamados do recorte por confiança registrada, separados em ativos, cancelados e fechados.")


def relatorio_aprendizado_por_casos(admin):
    """Mostra a memória selecionada que está disponível ao RAG em novas consultas."""
    st.markdown("### Aprendizado por casos validados")
    st.caption(
        "Estes são os únicos casos operacionais disponíveis para a IA consultar. "
        "Cada um foi selecionado pelo analista após o registro de diagnóstico e solução."
    )
    casos = listar_casos_base_ia(executor_id=admin["id"])
    if not casos:
        st.info(
            "Ainda não há casos ensinando a IA. Para incluir um, o analista deve selecionar "
            "o uso como referência ao registrar a resolução."
        )
        return

    dados = pd.DataFrame(casos)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos disponíveis à IA", len(dados))
    c2.metric("Categorias com experiência", int(dados["categoria_final"].fillna("Outros").nunique()))
    c3.metric("Última seleção", pd.to_datetime(dados["confirmado_em"]).max().strftime("%d/%m/%Y %H:%M"))
    c4.metric("Classificações corrigidas", int(dados["classificacao_corrigida"].fillna(False).astype(bool).sum()))

    exibicao = dados[["chamado_id", "titulo", "categoria_ia", "categoria_final", "urgencia_ia", "urgencia_final", "equipe_ia", "equipe_final", "diagnostico", "solucao", "confirmado_em"]].copy()
    exibicao.columns = ["Chamado", "Título", "Categoria IA", "Categoria final", "Urgência IA", "Urgência final", "Equipe IA", "Equipe final", "Diagnóstico", "Solução", "Selecionado em"]
    exibicao["Selecionado em"] = pd.to_datetime(exibicao["Selecionado em"]).dt.strftime("%d/%m/%Y %H:%M")
    exibir_tabela_tematica(exibicao)


def relatorio_produtividade_equipe(chamados):
    st.markdown("### Relatório de produtividade da equipe")
    st.caption("Produção por analista, baseada nos chamados atribuídos. O tempo de resolução usa o calendário de SLA de cada chamado e desconta as pausas registradas.")
    dados = pd.DataFrame(chamados)
    if dados.empty or "analista_id" not in dados:
        st.info("Ainda não há chamados atribuídos à equipe.")
        return

    dados = dados[dados["analista_id"].notna()].copy()
    if dados.empty:
        st.info("Ainda não há chamados atribuídos à equipe.")
        return
    dados["Analista"] = dados["nome_analista"].fillna("Analista removido")
    dados["criado_em"] = pd.to_datetime(dados["criado_em"])
    dados["resolvido_em"] = pd.to_datetime(dados["resolvido_em"])
    dados["tempo_resolucao_horas"] = [duracao_resolucao_horas(c) for c in dados.to_dict("records")]
    produtividade = dados.groupby("Analista", as_index=False).agg(
        Atribuídos=("id", "count"),
        Ativos=("status", lambda status: int((~status.isin(STATUS_ENCERRADOS)).sum())),
        Cancelados=("status", lambda status: int((status == "Cancelado").sum())),
        Fechados=("status", lambda status: int((status == "Fechado").sum())),
        Resolvidos=("resolvido_em", lambda data: int(data.notna().sum())),
        **{"Tempo médio de resolução (h de atendimento)": ("tempo_resolucao_horas", "mean")},
    ).sort_values(["Fechados", "Atribuídos"], ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Analistas com demanda", len(produtividade))
    c2.metric("Chamados atribuídos", len(dados))
    c3.metric("Chamados fechados", int((dados["status"] == "Fechado").sum()))
    exibir_grafico_situacao(produtividade, "Analista", "Chamados por analista")
    st.caption("Chamados atribuídos no recorte, separados em ativos, cancelados e fechados. Chamados sem atribuição não entram nesta comparação.")
    tabela = produtividade.copy()
    tabela["Tempo médio de resolução (h de atendimento)"] = tabela["Tempo médio de resolução (h de atendimento)"].map(lambda valor: f"{valor:.1f}" if pd.notna(valor) else "—")
    exibir_tabela_tematica(tabela)


def relatorio_cancelamentos(chamados):
    st.markdown("### Relatório de cancelamento de chamados")
    st.caption("Motivos informados no cancelamento. Chamados cancelados não são considerados nos indicadores de SLA.")
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados registrados para analisar cancelamentos.")
        return

    cancelados = dados[dados["status"] == "Cancelado"].copy()
    total_cancelados = len(cancelados)
    taxa_cancelamento = total_cancelados / len(dados) * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Chamados cancelados", total_cancelados)
    c2.metric("Taxa de cancelamento", f"{taxa_cancelamento:.1f}%")
    c3.metric("Chamados totais", len(dados))

    if cancelados.empty:
        st.info("Nenhum chamado foi cancelado até o momento.")
        return

    cancelados["Motivo"] = cancelados["motivo_cancelamento"].fillna("Motivo não informado").replace("", "Motivo não informado")
    motivos = (
        cancelados.groupby("Motivo", as_index=False).size()
        .rename(columns={"size": "Quantidade"})
        .sort_values("Quantidade", ascending=False)
    )
    motivos["Percentual"] = (motivos["Quantidade"] / total_cancelados * 100).map(lambda valor: f"{valor:.1f}%")
    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        distribuicao = resumir_por_situacao(cancelados.to_dict("records"), "Motivo", lambda c: c["Motivo"])
        exibir_grafico_situacao(distribuicao, "Motivo", "Cancelamentos por motivo")
        st.caption("Este recorte considera somente cancelamentos; as séries Ativos e Fechados ficam zeradas.")
    with tabela:
        exibir_tabela_tematica(motivos)


def abrir_perfil_usuario_admin(usuario_id):
    st.session_state.usuario_admin_aberto = usuario_id
    st.session_state.admin_nav = "Perfil do usuário"


def fechar_perfil_usuario_admin():
    st.session_state.usuario_admin_aberto = None
    st.session_state.admin_nav = "Usuários"


def excluir_perfil_usuario_admin(usuario_id, admin_id):
    anonimizar_titular(usuario_id, autor_id=admin_id)
    st.session_state.usuario_admin_aberto = None
    st.session_state.admin_nav = "Usuários"
    st.session_state.mensagem_admin = "Usuário anonimizado; o histórico técnico foi preservado sem identificadores diretos."


def painel_privacidade_admin(admin):
    if not usuario_tem_permissao(admin["id"], "privacidade.gerenciar"):
        st.error("Seu perfil não permite consultar os dados de privacidade.")
        return
    st.subheader("Direitos do titular")
    st.caption("Localize a pessoa para gerar uma cópia de seus dados ou executar a anonimização autorizada. A busca por CPF é exata.")
    with st.form("privacidade_busca"):
        identificador = st.text_input("E-mail ou CPF do titular", key="privacidade_identificador", placeholder="Informe um identificador completo")
        localizar = st.form_submit_button("Localizar titular", type="primary", key="privacidade_localizar")
    if not localizar:
        return
    st.session_state.pop("titular_privacidade_id", None)
    st.session_state.pop("titular_privacidade_email", None)
    try:
        titular, erro = buscar_titular_por_identificador(identificador, executor_id=admin["id"])
    except (ValueError, PermissionError) as erro:
        st.error(str(erro))
        return
    if erro:
        st.warning(erro)
        return
    st.session_state.titular_privacidade_id = titular["id"]
    st.session_state.titular_privacidade_email = titular["email"]
    st.rerun()


def tela_aceite_privacidade(usuario):
    injetar_css()
    with painel_acesso():
        st.title("Sua privacidade")
        st.caption(f"Política de privacidade — versão {VERSAO_POLITICA_PRIVACIDADE}")
        st.write("Leia a política de privacidade antes de continuar.")
        caminho_politica = Path(__file__).resolve().parent.parent / "PRIVACIDADE.md"
        try:
            with st.expander("Ler a política de privacidade", expanded=True):
                st.markdown(caminho_politica.read_text(encoding="utf-8"))
        except OSError:
            st.error("A política de privacidade não está disponível. Contate o administrador.")
            return
        with st.form("form_aceite_privacidade"):
            aceito = st.checkbox(
                "Li e aceito fornecer os dados pessoais necessários ao uso do sistema, "
                "ciente de que serão tratados conforme este Aviso de Privacidade e a "
                "Lei nº 13.709/2018 (LGPD)."
            )
            confirmar = st.form_submit_button("Aceitar e continuar", type="primary", width="stretch")
        if confirmar:
            if not aceito:
                st.warning("Para continuar, confirme a leitura e o aceite do Aviso de Privacidade.")
            else:
                registrar_aceite_privacidade(usuario["id"], "uso_do_sistema")
                st.session_state.aceite_privacidade_validado = True
                st.rerun()


def acoes_privacidade_admin(admin):
    if not usuario_tem_permissao(admin["id"], "privacidade.gerenciar"):
        return
    titular_id = st.session_state.get("titular_privacidade_id")
    if not titular_id:
        return
    email_titular = st.session_state.get("titular_privacidade_email")
    if not email_titular:
        st.info("Localize novamente o titular para consultar as ações disponíveis.")
        return
    titular, erro = buscar_titular_por_identificador(email_titular, executor_id=admin["id"])
    if erro or not titular or titular["id"] != titular_id:
        st.session_state.pop("titular_privacidade_id", None)
        st.session_state.pop("titular_privacidade_email", None)
        st.info("O titular não está mais disponível nesta seleção. Faça uma nova busca.")
        return

    st.divider()
    st.markdown(f"#### Titular localizado: {titular['email']}")
    if titular.get("conta_anonimizada_em"):
        st.info("Esta conta já foi anonimizada.")
        return

    chave_exportacao = f"privacidade_exportacao_{titular_id}"
    if st.button("Gerar arquivo de acesso", key=f"privacidade_gerar_{titular_id}"):
        try:
            st.session_state[chave_exportacao] = {
                "conteudo": exportar_dados_titular(titular_id, autor_id=admin["id"]),
                "expira_em": datetime.utcnow() + timedelta(days=7),
            }
        except ValueError as erro:
            st.error(str(erro))
    if chave_exportacao in st.session_state:
        exportacao = st.session_state[chave_exportacao]
        if datetime.utcnow() >= exportacao["expira_em"]:
            st.session_state.pop(chave_exportacao, None)
            st.warning("O arquivo de exportação expirou. Gere um novo arquivo se ainda for necessário.")
        else:
            st.download_button(
                "Baixar arquivo de acesso (ZIP)", data=exportacao["conteudo"],
                file_name=f"dados_titular_{titular_id}.zip", mime="application/zip",
                width="stretch",
            )
            st.caption(f"Arquivo disponível até {exportacao['expira_em'].strftime('%d/%m/%Y %H:%M')} UTC.")
    st.caption("O arquivo contém os dados acessíveis do titular e anexos. Senha, segredo TOTP e códigos não são exportados.")

    with st.expander("Anonimização permanente do titular"):
        st.warning("Esta operação remove ou anonimiza dados e conteúdos associados. Confirme a identidade e a autorização antes de continuar.")
        confirmar = st.checkbox(
            "Confirmo a anonimização permanente: conteúdo de chamados, mensagens, anexos e dados derivados serão removidos ou anonimizados; métricas e auditoria técnica permanecerão.",
            key=f"privacidade_confirmar_{titular_id}",
        )
        if st.button("Anonimizar dados do titular", type="primary", disabled=not confirmar, key=f"privacidade_anonimizar_{titular_id}"):
            try:
                resumo = anonimizar_titular(titular_id, autor_id=admin["id"])
                st.success(
                    f"Dados anonimizados: {resumo['chamados']} chamado(s), {resumo['mensagens']} mensagem(ns), "
                    f"{resumo['anexos']} anexo(s) e {resumo['casos_ia']} caso(s) de IA."
                )
                st.session_state.pop("titular_privacidade_id", None)
            except ValueError as erro:
                st.error(str(erro))


def painel_departamentos_admin(admin):
    if not usuario_tem_permissao(admin["id"], "departamentos.gerenciar"):
        st.error("Seu perfil não permite gerenciar departamentos.")
        return
    st.subheader("Departamentos")
    st.caption("Mantenha a estrutura da organização. A inativação preserva os vínculos e o histórico.")
    departamentos = listar_departamentos()
    indicadores([
        ("Departamentos ativos", sum(bool(d["ativo"]) for d in departamentos), "Disponíveis para novos cadastros."),
        ("Pessoas vinculadas", sum(d["total_usuarios"] for d in departamentos), "Vínculos registrados nos departamentos cadastrados."),
    ])
    modo = st.segmented_control("O que deseja fazer?", ["Consultar", "Cadastrar", "Editar"], default="Consultar", required=True, key="departamentos_modo")
    if modo == "Cadastrar":
        with st.form("form_novo_departamento", clear_on_submit=True):
            st.markdown("#### Novo departamento")
            nome = st.text_input("Nome do departamento", placeholder="Ex.: Recursos Humanos")
            descricao = st.text_area("Descrição (opcional)", help="Explique a área de atuação para facilitar a escolha no cadastro.")
            cadastrar = st.form_submit_button("Cadastrar departamento", type="primary")
        if cadastrar:
            try:
                criar_departamento(nome, descricao, autor_id=admin["id"])
                recarregar_com_feedback("Departamento cadastrado.")
            except (ValueError, PermissionError) as erro:
                st.error(str(erro))
        return
    if not departamentos:
        st.info("Nenhum departamento cadastrado. Use Cadastrar para adicionar o primeiro.")
        return
    if modo == "Consultar":
        busca = st.text_input("Buscar departamento", placeholder="Nome ou descrição", key="departamentos_busca").strip().casefold()
        selecionados = [d for d in departamentos if not busca or busca in f"{d['nome']} {d.get('descricao') or ''}".casefold()]
        tabela = pd.DataFrame([{"Departamento": d["nome"], "Descrição": d.get("descricao"), "Situação": "Ativo" if d["ativo"] else "Inativo", "Pessoas vinculadas": d["total_usuarios"]} for d in selecionados])
        exibir_tabela_tematica(tabela)
        return
    por_id = {d["id"]: d for d in departamentos}
    departamento_id = st.selectbox("Departamento para editar", list(por_id), format_func=lambda item: por_id[item]["nome"], key="departamento_edicao")
    departamento = por_id[departamento_id]
    with st.form(f"form_editar_departamento_{departamento_id}"):
        nome = st.text_input("Nome", value=departamento["nome"])
        descricao = st.text_area("Descrição", value=departamento.get("descricao") or "")
        ativo = st.toggle("Departamento ativo", value=bool(departamento["ativo"]), help="Ao inativar, o histórico e os usuários já vinculados são preservados.")
        salvar = st.form_submit_button("Salvar departamento", type="primary")
    if salvar:
        try:
            atualizar_departamento(departamento_id, nome, descricao, ativo, autor_id=admin["id"])
            recarregar_com_feedback("Departamento atualizado.")
        except (ValueError, PermissionError) as erro:
            st.error(str(erro))


def painel_sla_admin(admin):
    if not usuario_tem_permissao(admin["id"], "sla.gerenciar"):
        st.error("Seu perfil não permite alterar o SLA.")
        return
    st.subheader("SLA e horário de atendimento")
    st.info("As alterações valem para novos chamados. Os chamados existentes mantêm sua configuração original.")
    configuracao = obter_configuracao_sla()
    nomes_dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dias_atuais = [nomes_dias[dia] for dia in configuracao["dias_uteis"]]
    with st.expander("Consultar a configuração vigente", expanded=False):
        st.caption("Fuso de referência: America/Sao_Paulo.")
        exibir_tabela_tematica(pd.DataFrame([
            {"Dia": dia, "Atendimento": f"{configuracao['hora_inicio']} — {configuracao['hora_fim']}" if indice in configuracao["dias_uteis"] else "Fechado"}
            for indice, dia in enumerate(nomes_dias)
        ]))
    with st.form("form_configuracao_sla"):
        agenda, metas, operacao = st.tabs(["Agenda de atendimento", "Metas por urgência", "Regras operacionais"])
        with agenda:
            st.markdown("#### Dias e horários")
            st.caption("Horários em America/Sao_Paulo. Selecione os dias em que a equipe atende.")
            dias = st.multiselect("Dias de atendimento", nomes_dias, default=dias_atuais)
            col_inicio, col_fim = st.columns(2)
            inicio = col_inicio.time_input("Início do expediente", value=time.fromisoformat(configuracao["hora_inicio"]))
            fim = col_fim.time_input("Fim do expediente", value=time.fromisoformat(configuracao["hora_fim"]))
        with metas:
            st.caption("Tempo em minutos comerciais, conforme a configuração de SLA vigente. Resposta e resolução são metas independentes.")
            matriz = {}
            for urgencia in ["Critica", "Alta", "Media", "Baixa"]:
                st.markdown(f"**Urgência {rotulo(urgencia)}**")
                resposta_col, resolucao_col = st.columns(2)
                resposta = resposta_col.number_input("Primeira resposta (min)", min_value=1, value=int(configuracao["matriz"][urgencia]["resposta"]), key=f"sla_resp_{urgencia}")
                resolucao = resolucao_col.number_input("Resolução (min)", min_value=1, value=int(configuracao["matriz"][urgencia]["resolucao"]), key=f"sla_res_{urgencia}")
                matriz[urgencia] = {"resposta": resposta, "resolucao": resolucao}
        with operacao:
            fechamento = st.number_input("Fechamento automático (horas comerciais)", min_value=1, max_value=720, value=configuracao["horas_fechamento_automatico"], help="Prazo para fechar chamados resolvidos, conforme a regra existente de validação.")
            risco = st.number_input("Alertar risco após consumir (%)", min_value=1, max_value=99, value=int(configuracao["limiar_risco"] * 100), help="Ex.: 80 significa alertar quando 80% do tempo disponível tiver sido consumido.")
            limite_chamados = st.number_input("Limite de chamados ativos por pessoa", min_value=1, max_value=100, value=int(configuracao["limite_chamados_ativos_por_usuario"]), help="Conta os estados Novo, Em Andamento, Em Espera e Resolvido.")
        salvar = st.form_submit_button("Salvar configurações para novos chamados", type="primary", width="stretch")
    if salvar:
        try:
            atualizar_configuracao_sla({**configuracao, "dias_uteis": [nomes_dias.index(dia) for dia in dias], "hora_inicio": inicio.strftime("%H:%M"), "hora_fim": fim.strftime("%H:%M"), "horas_fechamento_automatico": fechamento, "limiar_risco": risco / 100, "limite_chamados_ativos_por_usuario": limite_chamados, "matriz": matriz}, admin["id"])
            recarregar_com_feedback("Configurações de SLA atualizadas para novos chamados.")
        except (ValueError, PermissionError) as erro:
            st.error(str(erro))


def painel_auditoria_admin(admin):
    if not usuario_tem_permissao(admin["id"], "relatorios.visualizar"):
        st.error("Seu perfil não permite consultar a auditoria.")
        return
    st.subheader("Auditoria")
    st.caption("Consulte as operações registradas. Os resultados e a exportação não incluem o conteúdo de chamados ou credenciais.")
    with st.form("filtros_auditoria"):
        periodo = st.date_input("Período dos eventos", value=(), key="auditoria_periodo")
        resultado = st.selectbox("Resultado da operação", ["", "SUCESSO", "FALHA"], format_func=lambda valor: {"": "Todos", "SUCESSO": "Sucesso", "FALHA": "Falha"}[valor])
        with st.expander("Filtros avançados"):
            usuario_id = st.number_input("ID do usuário", min_value=0, value=0, help="Deixe 0 para consultar todos os usuários autorizados.")
            acao = st.text_input("Ação exata", placeholder="Ex.: LOGIN_REALIZADO")
            entidade = st.text_input("Entidade", placeholder="Ex.: chamado")
            limite = st.selectbox("Eventos por página", [50, 100, 200], index=1)
            pagina = st.number_input("Página", min_value=1, value=1, step=1)
        st.form_submit_button("Consultar eventos", type="primary")
    inicio = fim = None
    if isinstance(periodo, (tuple, list)) and len(periodo) == 1:
        st.info("Complete a data final para consultar esse período.")
        return
    if isinstance(periodo, (tuple, list)) and len(periodo) == 2:
        inicio = datetime.combine(periodo[0], time.min)
        fim = datetime.combine(periodo[1] + timedelta(days=1), time.min)
    eventos = listar_auditoria(limite=limite, usuario_id=usuario_id or None, acao=acao.strip() or None,
                              entidade=entidade.strip() or None, resultado=resultado or None,
                              inicio=inicio, fim=fim, pagina=pagina - 1, executor_id=admin["id"])
    if not eventos:
        st.info("Nenhum evento encontrado. Ajuste os filtros ou volte à primeira página.")
        return
    st.caption(f"Página {pagina} · {len(eventos)} evento(s) · horários apresentados pelo sistema em America/Sao_Paulo")
    dados = pd.DataFrame(eventos)
    busca = st.text_input("Buscar nos eventos desta página", placeholder="Ação ou entidade", key="auditoria_busca_pagina").strip().casefold()
    if busca:
        dados = dados[dados.apply(lambda linha: busca in f"{linha.get('acao', '')} {linha.get('entidade', '')}".casefold(), axis=1)]
    exibicao = dados[["criado_em", "acao", "entidade", "entidade_id", "resultado"]].copy()
    exibicao.columns = ["Data", "Ação", "Entidade", "ID", "Resultado"]
    st.dataframe(exibicao, hide_index=True, width="stretch", column_config={"Data": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
    st.download_button("Exportar os eventos exibidos (CSV)", exibicao.to_csv(index=False).encode("utf-8-sig"), "auditoria.csv", "text/csv")


def relatorio_operacional(chamados, admin):
    """Indicadores compactos, sem expor dados pessoais em exportações."""
    dados = pd.DataFrame(chamados)
    if dados.empty:
        return
    ativos = dados[~dados["status"].isin(STATUS_ENCERRADOS)]
    resolvidos = dados[dados["status"].isin(["Resolvido", "Fechado"])]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Backlog atual", len(ativos))
    c2.metric("Em risco ou violados", sum(sla.pior_status(sla.status_sla(c)) in {"Em risco", "Violado"} for c in ativos.to_dict("records")))
    if usuario_tem_permissao(admin["id"], "chamados.visualizar_fila"):
        reabertos = 0
        for chamado_id in dados["id"].tolist():
            reabertos += sum(evento["tipo"] == "REABERTURA" for evento in listar_historico_chamado(chamado_id, admin["id"]))
        c3.metric("Reaberturas", reabertos, help="Eventos de reabertura nos chamados do recorte.")
    else:
        c3.metric("Reaberturas", "—", help="A consulta de histórico operacional exige acesso à fila.")
    c4.metric("Resolvidos/fechados", len(resolvidos))
    ids_periodo = set(dados["id"].tolist())
    pesquisas = [
        pesquisa for pesquisa in listar_pesquisas_satisfacao(admin["id"])
        if pesquisa["chamado_id"] in ids_periodo
    ]
    if pesquisas:
        st.caption(f"Satisfação média: {sum(item['nota'] for item in pesquisas) / len(pesquisas):.1f}/5 em {len(pesquisas)} avaliação(ões).")
    carga = resumir_por_situacao(chamados, "Equipe", lambda c: c.get("equipe_destino") or "Sem equipe")
    tendencia = resumir_evolucao_por_situacao(chamados)
    carga_coluna, tendencia_coluna = st.columns(2)
    with carga_coluna:
        exibir_grafico_situacao(carga, "Equipe", "Chamados por equipe")
        st.caption("Todos os chamados do recorte por equipe, separados em ativos, cancelados e fechados.")
    with tendencia_coluna:
        exibir_grafico_situacao(tendencia, "Data", "Tendência de abertura no período", horizontal=False)
        st.caption("Situação atual dos chamados por data de abertura no recorte: ativos, cancelados e fechados.")
    exportacao = dados[["id", "status", "categoria", "urgencia", "equipe_destino", "criado_em", "resolvido_em"]].copy()
    st.download_button("Exportar indicadores operacionais (CSV)", exportacao.to_csv(index=False).encode("utf-8-sig"), "indicadores_operacionais.csv", "text/csv")


def _formatar_percentual(valor):
    return f"{valor:.1f}%"


def _gerar_insights_executivos(dados, ativos, violacoes, satisfacao, casos_ia):
    """Traduz sinais já classificados pela IA em recomendações rastreáveis.

    Não faz diagnóstico automático a partir de textos livres: os sinais utilizam
    somente classificações, SLA e dados agregados que já existem no sistema.
    """
    total = len(dados)
    categoria = dados["Categoria"].value_counts().index[0] if total else "—"
    concentracao = (
        dados["Categoria"].value_counts().iloc[0] / total * 100 if total else 0
    )
    insights = []
    if concentracao >= 40:
        insights.append(
            f"A IA agrupou {_formatar_percentual(concentracao)} da demanda em **{categoria}**; "
            "priorize uma ação preventiva nesse tema."
        )
    if violacoes:
        insights.append(
            f"Há **{violacoes}** chamado(s) em violação de SLA; trate a fila crítica antes de ampliar a capacidade."
        )
    if len(ativos):
        insights.append(
            f"O backlog representa **{_formatar_percentual(len(ativos) / total * 100)}** do período; "
            "acompanhe-o diariamente por equipe e urgência."
        )
    if satisfacao is not None and satisfacao < 4:
        insights.append("A satisfação está abaixo de 4/5; revise comunicação de status e qualidade da solução entregue.")
    if casos_ia:
        insights.append(
            f"A base de casos validados já tem **{casos_ia}** referência(s): use-a para padronizar os temas recorrentes."
        )
    return insights or ["Ainda não há volume suficiente para recomendações automatizadas no período selecionado."]


def _exibir_diagrama_ishikawa(sinais, efeito):
    st.markdown(f"**Efeito a investigar: {efeito.replace(chr(10), ' ')}**")
    for dimensao, evidencias in sinais.items():
        with st.container(border=True):
            st.markdown(f"**{dimensao}**")
            for evidencia in evidencias:
                st.write(evidencia)


def relatorio_executivo_suporte(chamados, admin):
    renderizar_dashboard(chamados)
    if chamados:
        with st.expander("Análises complementares: concentração de demanda e hipóteses"):
            _relatorio_executivo_complementar(chamados, admin)


def _relatorio_executivo_complementar(chamados, admin):
    """Visão estratégica: Pareto, SWOT e Ishikawa sem expor dados pessoais."""
    st.markdown("### Dashboard executivo de suporte")
    st.caption(
        "Leitura gerencial baseada em dados agregados do período. Os sinais de IA usam as "
        "classificações já revisáveis no sistema; hipóteses de causa devem ser validadas pela gestão."
    )
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados no período selecionado para gerar a visão executiva.")
        return

    dados["Categoria"] = dados["categoria"].fillna("Não classificada").replace("", "Não classificada")
    dados["Equipe"] = dados["equipe_destino"].fillna("Sem equipe").replace("", "Sem equipe")
    dados["Urgência"] = dados["urgencia"].fillna("Não informada").replace("", "Não informada")
    dados["SLA resolução"] = [sla.status_sla(item)["resolucao"]["status"] for item in dados.to_dict("records")]
    ativos = dados[~dados["status"].isin(STATUS_ENCERRADOS)].copy()
    violacoes = int((dados["SLA resolução"] == "Violado").sum())
    em_risco = int((ativos["SLA resolução"] == "Em risco").sum())
    criticos_ativos = int(((ativos["Urgência"] == "Critica") | (ativos["Urgência"] == "Alta")).sum())
    ids_periodo = set(dados["id"].tolist())
    pesquisas = [
        pesquisa for pesquisa in listar_pesquisas_satisfacao(admin["id"])
        if pesquisa["chamado_id"] in ids_periodo
    ]
    satisfacao = (sum(item["nota"] for item in pesquisas) / len(pesquisas)) if pesquisas else None
    casos_ia = len(listar_casos_base_ia(executor_id=admin["id"]))

    prazo_concluido = dados[(dados["status"] != "Cancelado") & dados["resolvido_em"].notna()]
    resolvidos_no_prazo = int((prazo_concluido["SLA resolução"] == "Cumprido").sum())
    taxa_sla = resolvidos_no_prazo / len(prazo_concluido) * 100 if len(prazo_concluido) else 0
    categoria_lider = dados["Categoria"].value_counts().index[0]
    percentual_categoria_lider = dados["Categoria"].value_counts().iloc[0] / len(dados) * 100
    espera = int((ativos["status"] == "Em Espera").sum())
    prioridade_imediata = dados[
        (dados["SLA resolução"] == "Violado") |
        ((~dados["status"].isin(STATUS_ENCERRADOS)) & dados["Urgência"].isin(["Critica", "Alta"]))
    ]

    if violacoes or criticos_ativos:
        situacao, icone, mensagem_situacao = "Crítica", "🔴", "Existem prazos vencidos ou solicitações de alta prioridade que exigem atuação imediata."
    elif em_risco or espera or (satisfacao is not None and satisfacao < 4):
        situacao, icone, mensagem_situacao = "Atenção", "🟡", "A operação funciona, mas há sinais que precisam de acompanhamento nesta semana."
    else:
        situacao, icone, mensagem_situacao = "Controlada", "🟢", "Não há alertas críticos no recorte selecionado. Continue acompanhando os principais temas."

    st.markdown("#### Em resumo")
    st.info(f"{icone} **Situação da operação: {situacao}.** {mensagem_situacao}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados no período", len(dados), help="Total de solicitações abertas no período selecionado.")
    c2.metric("Pendentes na fila", len(ativos), help="Chamados que ainda precisam de atendimento ou confirmação.")
    c3.metric("Prioridade imediata", len(prioridade_imediata), f"{violacoes} prazo(s) vencido(s)", help="Chamados únicos com prazo vencido ou ainda abertos em alta/crítica urgência.")
    c4.metric("Maior tema", categoria_lider, _formatar_percentual(percentual_categoria_lider), help="Tema que mais gera chamados no período.")

    st.markdown("#### Próximas ações")
    acoes = []
    if violacoes:
        acoes.append(("🚨", "Resolver prazos vencidos", f"{violacoes} chamado(s)"))
    if criticos_ativos:
        acoes.append(("🔴", "Acompanhar prioridades altas", f"{criticos_ativos} chamado(s)"))
    if espera:
        acoes.append(("🟡", "Destravar chamados em espera", f"{espera} chamado(s)"))
    acoes.append(("💡", f"Prevenir ocorrências de {categoria_lider}", _formatar_percentual(percentual_categoria_lider) + " da demanda"))
    if satisfacao is not None and satisfacao < 4:
        acoes.append(("💬", "Melhorar comunicação com usuários", f"Satisfação atual: {satisfacao:.1f}/5"))
    for coluna, (icone_acao, titulo_acao, detalhe_acao) in zip(st.columns(min(4, len(acoes))), acoes[:4]):
        with coluna:
            with st.container(border=True):
                st.markdown(f"### {icone_acao}")
                st.markdown(f"**{titulo_acao}**")
                st.caption(detalhe_acao)

    with st.expander("Indicadores de apoio", expanded=False):
        apoio1, apoio2, apoio3, apoio4 = st.columns(4)
        apoio1.metric("SLA de resolução", _formatar_percentual(taxa_sla) if len(prazo_concluido) else "Sem amostra", f"{resolvidos_no_prazo}/{len(prazo_concluido)} concluídos")
        apoio2.metric("Em risco de atraso", em_risco)
        apoio3.metric("Em espera", espera)
        apoio4.metric("Satisfação", f"{satisfacao:.1f}/5" if satisfacao is not None else "Sem avaliação")

    st.markdown("#### Onde concentrar o esforço (Pareto 80/20)")
    pareto_col, resumo_col = st.columns([1.45, 1])
    with pareto_col:
        recorte = st.radio(
            "O que você quer priorizar?",
            ["Problemas mais frequentes", "Fila pendente por equipe", "Prazos vencidos por equipe"],
            horizontal=True,
            key="pareto_prioridade",
        )
        if recorte == "Problemas mais frequentes":
            base_pareto, dimensao, titulo_pareto = dados, "Categoria", "Problemas que mais geram chamados"
        elif recorte == "Fila pendente por equipe":
            base_pareto, dimensao, titulo_pareto = ativos, "Equipe", "Fila pendente por equipe"
        else:
            base_pareto, dimensao, titulo_pareto = dados[dados["SLA resolução"] == "Violado"], "Equipe", "Prazos vencidos por equipe"
        if base_pareto.empty:
            st.success("Não há dados neste recorte. Isso é um bom sinal para o acompanhamento atual.")
            pareto = pd.DataFrame(columns=[dimensao, "Chamados", "% acumulado"])
        else:
            pareto = base_pareto[dimensao].value_counts().rename_axis(dimensao).reset_index(name="Chamados")
            pareto["% acumulado"] = pareto["Chamados"].cumsum() / pareto["Chamados"].sum() * 100
        if not pareto.empty:
            distribuicao = resumir_por_situacao(base_pareto.to_dict("records"), dimensao, lambda c: c[dimensao])
            exibir_grafico_situacao(distribuicao, dimensao, titulo_pareto)
            st.caption("Ativos, cancelados e fechados dentro do recorte escolhido para a priorização.")
            st.caption("A participação acumulada é apresentada na tabela ao lado; 80% é uma referência, não uma causa comprovada.")


    with resumo_col:
        st.markdown("##### Decisão recomendada")
        if pareto.empty:
            st.write("Não há item crítico para priorizar neste recorte.")
        else:
            pareto_80 = pareto[pareto["% acumulado"].shift(fill_value=0) < 80]
            if pareto_80.empty:
                pareto_80 = pareto.head(1)
            participacao = pareto_80["Chamados"].sum() / pareto["Chamados"].sum() * 100
            st.write(
                f"Comece por **{', '.join(pareto_80[dimensao].astype(str).tolist())}**: "
                f"esses itens representam **{_formatar_percentual(participacao)}** deste problema."
            )
            st.caption("A tabela mostra a participação acumulada para apoiar a priorização.")
            pareto_exibicao = pareto.copy()
            pareto_exibicao["% acumulado"] = pareto_exibicao["% acumulado"].map(_formatar_percentual)
            exibir_tabela_tematica(pareto_exibicao)

    with st.expander("Diagnóstico FOFA — pontos fortes e alertas", expanded=False):
        st.caption("Resumo para decidir o que manter, corrigir, aproveitar e acompanhar.")
        strengths = [f"{_formatar_percentual(taxa_sla)} de resolução no prazo" if len(prazo_concluido) else "Indicador de SLA ainda sem amostra concluída"]
        if satisfacao is not None:
            strengths.append(f"Satisfação média de {satisfacao:.1f}/5")
        if casos_ia:
            strengths.append(f"{casos_ia} caso(s) validado(s) ampliando a memória da IA")
        fraquezas = [f"{violacoes} violação(ões) de SLA", f"{len(ativos)} chamado(s) ainda no backlog"]
        oportunidades = [f"Prevenir ocorrências em {categoria_lider}", "Transformar soluções recorrentes em autoatendimento"]
        ameacas = [f"{criticos_ativos} prioridade(s) alta/crítica em aberto", "Concentração de demanda pode ampliar o risco"]
        for coluna, titulo, itens in zip(st.columns(4), ["Forças", "Alertas", "Oportunidades", "Riscos"], [strengths, fraquezas, oportunidades, ameacas]):
            with coluna:
                with st.container(border=True):
                    st.markdown(f"**{titulo}**")
                    for item in itens[:2]:
                        st.write(f"• {item}")

    with st.expander("Possíveis causas dos alertas — evidências e hipóteses", expanded=False):
        st.caption(
            "Efeito analisado: atrasos e pressão no atendimento. Cada ramo apresenta uma evidência "
            "do sistema e uma hipótese a validar pela equipe; não representa causa raiz confirmada."
        )
        equipe_lider = ativos["Equipe"].value_counts().index[0] if not ativos.empty else "Sem backlog"
        dados["Departamento"] = dados.apply(_departamento_relatorio, axis=1)
        departamento_lider = dados["Departamento"].value_counts().index[0]
        sinais = {
            "Método / processo": [f"{espera} chamado(s) em espera", "Etapas de aprovação, retorno e escalonamento"],
            "Pessoas": [f"Maior fila: equipe {equipe_lider}", "Distribuição de carga e cobertura da equipe"],
            "Sistemas": [f"Maior volume: {categoria_lider}", "Recorrência de falhas no serviço ou sistema"],
            "Medição": [f"{violacoes} prazo(s) de SLA vencido(s)", "Alertas e acompanhamento antes do vencimento"],
            "Ambiente": [f"Maior demanda: {departamento_lider}", "Picos locais, mudanças e sazonalidade"],
            "Conhecimento": [f"{casos_ia} caso(s) validado(s)", "Cobertura de artigos e orientação inicial"],
        }
        _exibir_diagrama_ishikawa(sinais, "Atrasos e pressão\nno atendimento")

    with st.expander("Leitura complementar da IA", expanded=False):
        st.caption("Sugestões baseadas nas classificações, nos prazos e nos casos validados já existentes no sistema.")
        for insight in _gerar_insights_executivos(dados, ativos, violacoes, satisfacao, casos_ia):
            st.write(f"• {insight}")


def relatorio_chamados_abertos_por_departamento(chamados):
    """Compara o volume do recorte, incluindo departamentos sem chamados."""
    st.markdown("### Chamados por departamento")
    st.caption("Todos os chamados do recorte por departamento do solicitante, separados em ativos, cancelados e fechados.")
    nomes = [d["nome"] for d in listar_departamentos()]
    distribuicao = resumir_por_situacao(chamados, "Departamento", _departamento_relatorio, grupos=nomes)
    distribuicao["Total"] = distribuicao[list(SITUACOES_CHAMADOS)].sum(axis=1)
    total = int(distribuicao["Total"].sum())
    sem_departamento = int(distribuicao.loc[distribuicao["Departamento"] == "Não informado", "Total"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Chamados no período", total)
    c2.metric("Departamento com maior demanda",
              distribuicao.iloc[0]["Departamento"] if total else "—",
              f"{int(distribuicao.iloc[0]['Total'])} chamado(s)" if total else None)
    c3.metric("Sem departamento informado", sem_departamento)
    if distribuicao.empty:
        st.info("Cadastre departamentos para acompanhar a distribuição dos chamados.")
        return
    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        exibir_grafico_situacao(distribuicao, "Departamento", "Volume por departamento")
    with tabela:
        exibir_tabela_tematica(distribuicao)


def relatorio_demanda_por_departamento_categoria(chamados):
    """Evidencia volume e motivos recorrentes de abertura por departamento."""
    st.markdown("### Demanda por departamento e categoria")
    st.caption(
        "Mostra todos os chamados criados no período selecionado, inclusive os já fechados. "
        "Use este recorte para identificar temas que podem ser tratados com treinamento ou melhoria de processo."
    )

    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados no período selecionado para analisar a demanda.")
        return

    dados["Departamento"] = dados.apply(_departamento_relatorio, axis=1)
    dados["Categoria"] = (
        dados["categoria"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Não classificada")
    )
    demanda_departamento = resumir_por_situacao(chamados, "Departamento", _departamento_relatorio)
    demanda_departamento["Chamados criados"] = demanda_departamento[list(SITUACOES_CHAMADOS)].sum(axis=1)
    departamento_selecionado = st.selectbox(
        "Analisar categorias do departamento",
        demanda_departamento["Departamento"].tolist(),
        key="dashboard_departamento_categoria",
    )
    categorias = (
        dados[dados["Departamento"] == departamento_selecionado]
        .groupby("Categoria", as_index=False)
        .size()
        .rename(columns={"size": "Chamados criados"})
        .sort_values(["Chamados criados", "Categoria"], ascending=[False, True])
    )

    categoria_principal = categorias.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Chamados criados no período", len(dados))
    c2.metric("Departamento com maior demanda", demanda_departamento.iloc[0]["Departamento"])
    c3.metric(
        f"Categoria mais recorrente em {departamento_selecionado}",
        categoria_principal["Categoria"],
        f"{int(categoria_principal['Chamados criados'])} chamado(s)",
    )

    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        distribuicao = resumir_por_situacao(
            dados[dados["Departamento"] == departamento_selecionado].to_dict("records"),
            "Categoria", lambda c: c["Categoria"])
        exibir_grafico_situacao(distribuicao, "Categoria", f"Categorias recorrentes — {departamento_selecionado}")
        st.caption("Chamados do departamento selecionado no recorte, separados em ativos, cancelados e fechados.")
    with tabela:
        exibir_tabela_tematica(demanda_departamento)

    matriz = pd.crosstab(dados["Departamento"], dados["Categoria"])
    matriz["Total"] = matriz.sum(axis=1)
    matriz = matriz.sort_values("Total", ascending=False).reset_index()
    st.markdown("#### Comparativo de demanda por categoria")
    exibir_tabela_tematica(matriz)


def painel_perfis_admin(admin):
    st.markdown("### Perfis e permissões")
    st.caption("Perfis definem o que cada pessoa pode acessar. Alterações refletem imediatamente nas contas vinculadas.")
    try:
        permissoes = listar_permissoes(admin["id"])
        perfis = listar_perfis(admin["id"])
    except PermissionError as erro:
        st.error(str(erro))
        return

    categorias = (
        ("Administração", {
            "administracao.acessar", "usuarios.visualizar", "usuarios.gerenciar",
            "departamentos.gerenciar", "privacidade.gerenciar", "relatorios.visualizar",
            "perfis.gerenciar", "sla.gerenciar",
        }),
        ("Abrir e acompanhar chamados", {
            "conhecimento.visualizar", "ia.utilizar", "chamados.visualizar_proprios",
            "chamados.abrir", "chamados.responder_proprios", "chamados.anexar_proprios",
            "chamados.cancelar_proprios", "chamados.confirmar_resolucao",
        }),
        ("Atender chamados", {
            "chamados.visualizar_fila", "chamados.assumir", "chamados.responder_atribuidos",
            "chamados.anexar_atribuidos", "chamados.alterar_status",
            "chamados.registrar_resolucao", "chamados.cancelar_fila",
        }),
    )
    permissoes_base = {
        "Administração": "administracao.acessar",
        "Abrir e acompanhar chamados": "chamados.visualizar_proprios",
        "Atender chamados": "chamados.visualizar_fila",
    }

    def renderizar_permissoes(chave, selecionadas=(), bloqueadas=False):
        selecionadas = set(selecionadas)
        permissao_ids = []
        por_codigo = {permissao["codigo"]: permissao for permissao in permissoes}
        for categoria, codigos in categorias:
            itens = [por_codigo[codigo] for codigo in codigos if codigo in por_codigo]
            if not itens:
                continue
            permissao_base = permissoes_base[categoria]
            if permissao_base not in por_codigo:
                continue
            acesso_grupo = permissao_base in selecionadas
            with st.expander(categoria, expanded=False):
                permissao_base_item = por_codigo[permissao_base]
                st.caption(
                    f"Ação-base: marque **{permissao_base_item['nome']}** para liberar as demais opções deste grupo."
                )
                for permissao in sorted(
                    itens,
                    key=lambda item: (item["codigo"] != permissao_base, item["nome"]),
                ):
                    eh_permissao_base = permissao["codigo"] == permissao_base
                    depende_acesso_grupo = not eh_permissao_base
                    marcada = bloqueadas or permissao["id"] in selecionadas
                    indisponivel_por_dependencia = depende_acesso_grupo and not acesso_grupo
                    ajuda = permissao["descricao"]
                    if bloqueadas:
                        rotulo = f"🔒 {permissao['nome']} — perfil protegido"
                        ajuda = "As permissões do perfil Administrador são fixas e não podem ser alteradas aqui."
                    elif eh_permissao_base:
                        rotulo = f"🔑 {permissao['nome']} — libera este grupo"
                    elif indisponivel_por_dependencia:
                        rotulo = f"🔒 {permissao['nome']} — requer ação-base"
                        ajuda = (
                            f"Indisponível até marcar '{permissao_base_item['nome']}', "
                            "a ação-base deste grupo."
                        )
                    else:
                        rotulo = f"🔓 {permissao['nome']}"
                    marcada = st.checkbox(
                        rotulo, value=marcada, help=ajuda,
                        disabled=bloqueadas or indisponivel_por_dependencia,
                        key=f"{chave}_{permissao['id']}",
                    )
                    if eh_permissao_base:
                        acesso_grupo = marcada
                        if not acesso_grupo:
                            for item in itens:
                                if item["codigo"] != permissao_base:
                                    st.session_state[f"{chave}_{item['id']}"] = False
                    if marcada:
                        permissao_ids.append(permissao["id"])
        return permissao_ids

    modo = st.segmented_control("Gerenciar perfis", ["Consultar", "Criar perfil", "Editar perfil"], default="Consultar", required=True, key="perfis_modo")
    if modo == "Consultar":
        if not perfis:
            st.info("Nenhum perfil disponível para consulta.")
            return
        tabela = pd.DataFrame(perfis)[["nome", "descricao", "ativo", "total_usuarios", "total_permissoes"]].copy()
        tabela.columns = ["Perfil", "Descrição", "Ativo", "Usuários vinculados", "Permissões"]
        tabela["Ativo"] = tabela["Ativo"].map(
            lambda valor: "Sim" if valor in (True, 1, "1", "true", "True", "Sim", "sim") else "Não"
        )
        exibir_tabela_tematica(tabela)

        return
    if modo == "Criar perfil":
        with st.expander("Cadastrar perfil", expanded=True):
            nome = st.text_input("Nome do perfil", placeholder="Ex.: Suporte N1", key="novo_perfil_nome")
            descricao = st.text_input("Descrição (opcional)", key="novo_perfil_descricao")
            st.caption("Marque a primeira permissão de cada grupo para liberar suas ações adicionais.")
            permissao_ids = renderizar_permissoes("novo_perfil")
            cadastrar = st.button("Cadastrar perfil", type="primary", key="novo_perfil_cadastrar")
            if cadastrar:
                try:
                    criar_perfil(nome, descricao, permissao_ids, admin["id"])
                    st.session_state.ui_limpar_prefixos = ["novo_perfil_"]
                    recarregar_com_feedback('Perfil cadastrado.')
                except (ValueError, PermissionError, mysql.connector.Error) as erro:
                    st.error(str(erro))

        return
    if not perfis:
        st.info("Cadastre um perfil antes de editar.")
        return

    perfis_por_id = {perfil["id"]: perfil for perfil in perfis}
    perfil_id = st.selectbox(
        "Editar perfil",
        options=list(perfis_por_id),
        format_func=lambda item: perfis_por_id[item]["nome"],
    )
    perfil = perfis_por_id[perfil_id]
    ids_selecionados = permissoes_do_perfil(perfil_id, admin["id"])
    administrador_protegido = perfil["chave"] == "administrador"
    pode_alterar_administrador = usuario_eh_administrador(admin["id"])

    nome = st.text_input(
        "Nome", value=perfil["nome"], key=f"perfil_{perfil_id}_nome",
        disabled=administrador_protegido and not pode_alterar_administrador,
    )
    descricao = st.text_input(
        "Descrição", value=perfil.get("descricao") or "", key=f"perfil_{perfil_id}_descricao",
        disabled=administrador_protegido and not pode_alterar_administrador,
    )
    ativo = st.checkbox(
        "Perfil ativo", value=bool(perfil["ativo"]), key=f"perfil_{perfil_id}_ativo",
        disabled=administrador_protegido,
    )
    if administrador_protegido:
        st.info("O perfil Administrador é protegido e sempre mantém todas as permissões.")
    st.caption("Marque a primeira permissão de cada grupo para liberar suas ações adicionais.")
    permissao_ids = renderizar_permissoes(
        f"perfil_{perfil_id}", ids_selecionados, bloqueadas=administrador_protegido,
    )
    salvar = st.button(
        "Salvar perfil", type="primary", key=f"perfil_{perfil_id}_salvar",
        disabled=administrador_protegido and not pode_alterar_administrador,
    )
    with st.expander("Excluir este perfil"):
        st.caption("Perfis do sistema e perfis com pessoas vinculadas não podem ser excluídos.")
        confirmar_exclusao = st.checkbox(
            "Confirmo a exclusão deste perfil sem usuários vinculados.", key=f"perfil_{perfil_id}_confirmar_exclusao",
            disabled=bool(perfil["sistema"]),
        )
        excluir = st.button(
            "Excluir perfil", key=f"perfil_{perfil_id}_excluir",
            disabled=bool(perfil["sistema"]) or not confirmar_exclusao,
        )

    if salvar:
        try:
            atualizar_perfil(perfil_id, nome, descricao, ativo, permissao_ids, admin["id"])
            recarregar_com_feedback('Perfil atualizado.')
        except (ValueError, PermissionError, mysql.connector.Error) as erro:
            st.error(str(erro))
    if excluir:
        try:
            excluir_perfil(perfil_id, admin["id"])
            recarregar_com_feedback('Perfil excluído.')
        except (ValueError, PermissionError, mysql.connector.Error) as erro:
            st.error(str(erro))


def painel_perfil_usuario_admin(admin):
    if not usuario_tem_permissao(admin["id"], "usuarios.gerenciar"):
        st.error("Seu perfil não permite editar contas de usuário.")
        return
    usuario_id = st.session_state.get("usuario_admin_aberto")
    conta = buscar_usuario_por_id(usuario_id, executor_id=admin["id"]) if usuario_id else None
    if not conta:
        st.info("Abra um usuário pela lista para consultar ou editar o perfil.")
        return
    if conta.get("perfil_chave") == "administrador" and not usuario_eh_administrador(admin["id"]):
        st.error("Somente um administrador pode alterar uma conta administrativa.")
        return

    st.button("← Voltar para usuários", on_click=fechar_perfil_usuario_admin)
    st.markdown(f"#### Perfil de {conta['nome']} {conta.get('sobrenome') or ''}".strip())
    m1, m2, m3 = st.columns(3)
    m1.metric("Perfil", conta.get("perfil_nome") or "Não informado")
    m2.metric("Departamento", conta.get("departamento") or "Não informado")
    m3.metric("Último login", para_horario_local(conta["ultimo_login_em"]).strftime("%d/%m/%Y %H:%M") if conta.get("ultimo_login_em") else "Nunca acessou")

    with st.container(border=True):
        st.caption("Dados de identificação e vínculo organizacional. Campos adicionais são opcionais.")
        departamentos = listar_departamentos()
        perfis = listar_perfis_para_atribuicao(admin["id"], incluir_inativos=True)
        perfis_por_id = {perfil["id"]: perfil for perfil in perfis}
        perfil_atual_id = conta.get("perfil_id")
        opcoes_perfil = [
            perfil["id"] for perfil in perfis
            if perfil["ativo"] or perfil["id"] == perfil_atual_id
        ]
        if not opcoes_perfil:
            st.error("Não há perfis ativos disponíveis para atribuição.")
            return
        departamentos_por_id = {departamento["id"]: departamento for departamento in departamentos}
        departamento_atual_id = conta.get("departamento_id")
        opcoes_departamento = [None] + [
            departamento["id"]
            for departamento in departamentos
            if departamento["ativo"] or departamento["id"] == departamento_atual_id
        ]
        with st.form(f"form_editar_usuario_{conta['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome", value=conta["nome"])
                novo_sobrenome = st.text_input("Sobrenome", value=conta.get("sobrenome") or "")
                novo_email = st.text_input("E-mail", value=conta["email"])
                novo_telefone = st.text_input("Telefone", value=conta.get("telefone") or "")
                novo_cpf = st.text_input(
                    "CPF (opcional)",
                    help="Informe somente para cadastrar ou substituir o CPF. O número não será exibido após o salvamento.",
                )
                if conta.get("cpf_hash"):
                    st.caption("CPF cadastrado com proteção para busca exata.")
            with col2:
                novo_perfil_id = st.selectbox(
                    "Perfil de acesso",
                    options=opcoes_perfil,
                    index=opcoes_perfil.index(perfil_atual_id) if perfil_atual_id in opcoes_perfil else 0,
                    format_func=lambda item: perfis_por_id[item]["nome"],
                )
                novo_departamento_id = st.selectbox(
                    "Departamento",
                    options=opcoes_departamento,
                    index=opcoes_departamento.index(departamento_atual_id) if departamento_atual_id in opcoes_departamento else 0,
                    format_func=lambda item: "Não informado" if item is None else departamentos_por_id[item]["nome"],
                )
                novo_cargo = st.text_input("Cargo", value=conta.get("cargo") or "")
                nova_senha = st.text_input("Nova senha (opcional)", type="password")
            salvar = st.form_submit_button("Salvar alterações", type="primary")

        if salvar:
            outro_usuario = buscar_usuario_por_email(novo_email)
            outro_cpf = None
            erro_cpf = None
            if novo_cpf and normalizar_cpf(novo_cpf):
                try:
                    outro_cpf = buscar_usuario_por_cpf(novo_cpf)
                except ValueError as erro:
                    erro_cpf = str(erro)
            if not novo_nome or not novo_sobrenome or not novo_email:
                st.warning("Nome, sobrenome e e-mail são obrigatórios.")
            elif novo_cpf and not normalizar_cpf(novo_cpf):
                st.warning("Informe um CPF válido.")
            elif erro_cpf:
                st.error(erro_cpf)
            elif outro_usuario and outro_usuario["id"] != conta["id"]:
                st.error("Já existe uma conta com esse e-mail.")
            elif outro_cpf and outro_cpf["id"] != conta["id"]:
                st.error("Já existe uma conta com esse CPF.")
            else:
                try:
                    novo_departamento = (
                        departamentos_por_id[novo_departamento_id]["nome"] if novo_departamento_id else None
                    )
                    atualizar_usuario(
                        conta["id"], novo_nome, novo_email, conta["papel"],
                        senha_hash=gerar_hash_senha(nova_senha) if nova_senha else None,
                        sobrenome=novo_sobrenome, telefone=novo_telefone, cpf=novo_cpf or None,
                        departamento=novo_departamento, departamento_id=novo_departamento_id, cargo=novo_cargo,
                        autor_id=admin["id"], perfil_id=novo_perfil_id,
                    )
                    recarregar_com_feedback('Perfil atualizado.')
                except ValueError as erro:
                    st.error(str(erro))

    if conta["id"] != admin["id"]:
        with st.expander("Anonimizar os dados desta conta"):
            st.warning("A anonimização é permanente. Confira a conta antes de confirmar.")
            confirmar_exclusao = st.checkbox("Confirmo a anonimização permanente desta conta e de seus dados associados.")
            st.button("Anonimizar usuário", disabled=not confirmar_exclusao, on_click=excluir_perfil_usuario_admin, args=(conta["id"], admin["id"]))

    if conta["id"] != admin["id"]:
        with st.expander("Zona de perigo — excluir conta", expanded=False):
            st.warning("A exclusão é permanente. Prefira a anonimização quando o pedido for relacionado à privacidade do titular.")
            confirmar_exclusao_definitiva = st.checkbox(
                "Confirmo que desejo excluir definitivamente esta conta.",
                key=f"usuario_{conta['id']}_confirmar_exclusao_definitiva",
            )
            if st.button(
                "Excluir usuário definitivamente", type="primary",
                disabled=not confirmar_exclusao_definitiva,
                key=f"usuario_{conta['id']}_excluir_definitivamente",
            ):
                try:
                    linhas = excluir_usuario(conta["id"], autor_id=admin["id"])
                    if not linhas:
                        st.error("Usuário não encontrado ou já excluído.")
                    else:
                        # O rádio admin_nav já foi criado nesta execução. A navegação
                        # será normalizada antes de ele ser recriado no próximo rerun.
                        st.session_state.usuario_admin_aberto = None
                        st.session_state.mensagem_admin = "Usuário excluído definitivamente. A ação foi registrada na auditoria."
                        st.rerun()
                except (ValueError, PermissionError, mysql.connector.Error) as erro:
                    st.error(str(erro))


def painel_dados_demonstracao(usuario):
    if not usuario_eh_administrador(usuario["id"]):
        return
    with st.expander("Chamados de demonstração", expanded=False):
        st.caption(
            "Gera exemplos usando os solicitantes, analistas e departamentos cadastrados, "
            "com mensagens, histórico, avaliações e prazos de SLA. "
            "Os chamados aparecem no portal, no atendimento e nos dashboards com a marca [DEMO DASHBOARD]."
        )
        st.caption("A quantidade de ativos respeita a capacidade dos solicitantes; os demais exemplos ficam no histórico.")
        existentes = contar_dados_demonstracao_dashboard(usuario["id"])
        st.caption(f"{existentes} chamado(s) de demonstração cadastrado(s).")
        quantidade = st.number_input("Quantidade de chamados a adicionar", min_value=12, max_value=500,
                                      value=120, step=12, key="demo_quantidade")
        adicionar, remover = st.columns(2)
        if adicionar.button("Adicionar chamados de demonstração", key="inserir_demo_dashboard", width="stretch"):
            try:
                with st.spinner("Criando chamados de demonstração..."):
                    inseridos = inserir_dados_demonstracao_dashboard(usuario["id"], quantidade=int(quantidade))
                recarregar_com_feedback(f"{inseridos} chamados de demonstração adicionados com os cadastros atuais.")
            except (ValueError, PermissionError, mysql.connector.Error) as erro:
                st.error(f"Não foi possível adicionar os chamados de demonstração: {erro}")
        if remover.button("Remover chamados de demonstração", key="remover_demo_dashboard",
                          disabled=existentes == 0, width="stretch",
                          help="Remove os chamados marcados como demonstração e suas mensagens, histórico e avaliações."):
            try:
                removidos = remover_dados_demonstracao_dashboard(usuario["id"])
                recarregar_com_feedback(f"{removidos} chamados de demonstração removidos. Os chamados reais foram preservados.")
            except (ValueError, PermissionError, mysql.connector.Error) as erro:
                st.error(f"Não foi possível remover os chamados de demonstração: {erro}")


def tela_admin(usuario):
    injetar_css()
    cabecalho("Administração", "Gerencie pessoas, operação, indicadores e conformidade", "🛡️")
    if not usuario_tem_permissao(usuario["id"], "administracao.acessar"):
        st.error("Você não tem permissão para acessar a área administrativa.")
        return

    pode_visualizar_usuarios = usuario_tem_permissao(usuario["id"], "usuarios.visualizar")
    pode_gerenciar_usuarios = usuario_tem_permissao(usuario["id"], "usuarios.gerenciar")
    pode_visualizar_relatorios = usuario_tem_permissao(usuario["id"], "relatorios.visualizar")
    usuarios = []

    opcoes_navegacao = []
    if pode_visualizar_usuarios or pode_gerenciar_usuarios:
        opcoes_navegacao.append("Usuários")
    if usuario_tem_permissao(usuario["id"], "departamentos.gerenciar"):
        opcoes_navegacao.append("Departamentos")
    if usuario_tem_permissao(usuario["id"], "perfis.gerenciar"):
        opcoes_navegacao.append("Perfis e permissões")
    if usuario_tem_permissao(usuario["id"], "sla.gerenciar"):
        opcoes_navegacao.append("SLA e horário comercial")
    if pode_visualizar_relatorios:
        opcoes_navegacao.append("Dashboards")
        opcoes_navegacao.append("Auditoria")
    if usuario_tem_permissao(usuario["id"], "privacidade.gerenciar"):
        opcoes_navegacao.append("Privacidade")
    if st.session_state.get("usuario_admin_aberto") and pode_gerenciar_usuarios:
        opcoes_navegacao.append("Perfil do usuário")

    if not opcoes_navegacao:
        st.info("Este perfil não possui funcionalidades administrativas adicionais.")
        return
    # Esta normalização acontece antes de instanciar o widget. Ela também cobre a
    # remoção de uma conta enquanto a tela de perfil estava aberta.
    if st.session_state.get("admin_nav") not in opcoes_navegacao:
        st.session_state.admin_nav = opcoes_navegacao[0]
    # As áreas administrativas ficam na lateral para manter a área principal
    # dedicada ao conteúdo e evitar uma segunda navegação horizontal.
    with st.sidebar:
        st.caption("Administração")
        navegacao = st.radio(
            "Seções administrativas",
            opcoes_navegacao,
            key="admin_nav",
            label_visibility="collapsed",
        )

    if navegacao == "Dashboards":
        chamados = listar_chamados(limite=5000, executor_id=usuario["id"], para_relatorio=True)
        lote = chamados
        pagina = 0
        while len(lote) == 5000:
            pagina += 1
            lote = listar_chamados(limite=5000, executor_id=usuario["id"], para_relatorio=True, pagina=pagina)
            chamados.extend(lote)
        st.subheader("Painel de indicadores")
        st.caption("Chamados filtrados pela data de abertura. Indicadores operacionais usam a situação atual desse recorte.")
        chamados = filtros_dashboard(chamados)
        if chamados is None:
            return
        st.caption("O recorte de chamados vale para Executivo, Visão geral e Operação e SLA. Pessoas mostra o cadastro atual; IA e conhecimento informa seu próprio escopo.")

        painel = st.segmented_control("Painel", ["Executivo", "Visão geral", "Operação e SLA", "Pessoas", "IA e conhecimento"], default="Executivo", required=True, key="dashboard_painel")
        if painel == "Executivo":
            relatorio_executivo_suporte(chamados, usuario)
        if painel == "Visão geral":
            relatorio_operacional(chamados, usuario)
            st.divider()
            relatorio_chamados_abertos_por_departamento(chamados)
            st.divider()
            relatorio_demanda_por_departamento_categoria(chamados)
        if painel == "Operação e SLA":
            relatorio_sla_desempenho(chamados)
            st.divider()
            relatorio_produtividade_equipe(chamados)
            st.divider()
            relatorio_cancelamentos(chamados)
        if painel == "Pessoas":
            usuarios = listar_usuarios(limite=5000, executor_id=usuario["id"], para_relatorio=True)
            relatorio_usuarios(usuarios)
        if painel == "IA e conhecimento":
            relatorio_ia(chamados, usuario)
            with st.expander("Adicionar caso anonimizado para avaliação da IA"):
                st.caption("Use apenas relatos reais já anonimizados e revisados. Estes casos medem a IA; não entram na base RAG.")
                with st.form("caso_avaliacao_ia"):
                    identificador = st.text_input("Identificador sem dado pessoal (ex.: AVAL-001)")
                    titulo_caso = st.text_input("Título anonimizado")
                    descricao_caso = st.text_area("Descrição anonimizada")
                    c1, c2, c3 = st.columns(3)
                    categoria_caso = c1.selectbox("Categoria esperada", ["Acesso", "Software", "Hardware", "Rede", "Outros"])
                    urgencia_caso = c2.selectbox("Urgência esperada", ["Baixa", "Media", "Alta", "Critica"])
                    equipe_caso = c3.selectbox("Equipe esperada", ["Suporte", "Software", "Hardware", "Redes"])
                    salvar_caso = st.form_submit_button("Salvar caso de avaliação")
                if salvar_caso:
                    cadastrar_caso_avaliacao_ia(identificador, titulo_caso, descricao_caso, categoria_caso, urgencia_caso, equipe_caso, usuario["id"])
                    st.success("Caso de avaliação anonimizado registrado.")
            casos_avaliacao = listar_casos_avaliacao_ia(usuario["id"])
            if casos_avaliacao and st.button("Executar avaliação de classificação", key="executar_avaliacao_ia"):
                with st.spinner("Executando conjunto de avaliação..."):
                    avaliacao = avaliar_classificador(casos_avaliacao)
                    registrar_execucao_avaliacao_ia(avaliacao, usuario["id"])
                c1, c2, c3 = st.columns(3)
                c1.metric("Categoria (benchmark)", f"{avaliacao['categoria'] * 100:.1f}%")
                c2.metric("Urgência (benchmark)", f"{avaliacao['urgencia'] * 100:.1f}%")
                c3.metric("Equipe (benchmark)", f"{avaliacao['equipe'] * 100:.1f}%")
                exibir_tabela_tematica(pd.DataFrame(avaliacao["resultados"]))
            st.divider()
            relatorio_aprendizado_por_casos(usuario)

        painel_dados_demonstracao(usuario)

    if navegacao == "Auditoria":
        painel_auditoria_admin(usuario)

    if navegacao == "Privacidade":
        painel_privacidade_admin(usuario)
        acoes_privacidade_admin(usuario)

    if navegacao == "Departamentos":
        painel_departamentos_admin(usuario)

    if navegacao == "Perfis e permissões":
        painel_perfis_admin(usuario)

    if navegacao == "SLA e horário comercial":
        painel_sla_admin(usuario)

    if navegacao == "Usuários":
        if pode_visualizar_usuarios or pode_visualizar_relatorios:
            usuarios = listar_usuarios(limite=200, executor_id=usuario["id"], para_relatorio=pode_visualizar_relatorios)
        if st.session_state.get("mensagem_admin"):
            st.success(st.session_state.pop("mensagem_admin"))
        modo_usuarios = st.segmented_control("Gerenciar pessoas", ["Consultar", "Cadastrar"] if pode_gerenciar_usuarios else ["Consultar"], default="Consultar", required=True, key="usuarios_modo")
        if pode_gerenciar_usuarios and modo_usuarios == "Cadastrar":
            with st.container(border=True):
                with st.form("form_novo_usuario", clear_on_submit=True):
                    departamentos_ativos = listar_departamentos(apenas_ativos=True)
                    departamentos_por_id = {departamento["id"]: departamento for departamento in departamentos_ativos}
                    perfis_ativos = listar_perfis_para_atribuicao(usuario["id"])
                    perfis_por_id = {perfil["id"]: perfil for perfil in perfis_ativos}
                    if not perfis_por_id:
                        st.info("Nenhum perfil disponível para atribuição. Revise as permissões de gerenciamento.")
                        return
                    col1, col2 = st.columns(2)
                    with col1:
                        nome = st.text_input("Nome")
                        sobrenome = st.text_input("Sobrenome")
                        senha = st.text_input("Senha", type="password")
                        telefone = st.text_input("Telefone (opcional)")
                        cpf = st.text_input("CPF (opcional)", help="Usado apenas para identificação e busca de privacidade.")
                    with col2:
                        email = st.text_input("E-mail")
                        perfil_id = st.selectbox(
                            "Perfil de acesso",
                            options=list(perfis_por_id),
                            format_func=lambda item: perfis_por_id[item]["nome"],
                        )
                        departamento_id = st.selectbox(
                            "Departamento",
                            options=[None] + list(departamentos_por_id),
                            format_func=lambda item: "Não informado" if item is None else departamentos_por_id[item]["nome"],
                        )
                        cargo = st.text_input("Cargo (opcional)")
                    cadastrar = st.form_submit_button("Cadastrar", type="primary")

                if cadastrar:
                    outro_cpf = None
                    erro_cpf = None
                    if cpf and normalizar_cpf(cpf):
                        try:
                            outro_cpf = buscar_usuario_por_cpf(cpf)
                        except ValueError as erro:
                            erro_cpf = str(erro)
                    if not nome or not sobrenome or not email or not senha:
                        st.warning("Nome, sobrenome, e-mail e senha são obrigatórios.")
                    elif cpf and not normalizar_cpf(cpf):
                        st.warning("Informe um CPF válido.")
                    elif erro_cpf:
                        st.error(erro_cpf)
                    elif buscar_usuario_por_email(email):
                        st.error("Já existe um usuário cadastrado com esse e-mail.")
                    elif outro_cpf:
                        st.error("Já existe uma conta com esse CPF.")
                    else:
                        try:
                            departamento = departamentos_por_id[departamento_id]["nome"] if departamento_id else None
                            criar_usuario(
                                nome, email, gerar_hash_senha(senha), "usuario",
                                sobrenome=sobrenome, telefone=telefone or None, cpf=cpf or None,
                                departamento=departamento, departamento_id=departamento_id, cargo=cargo or None,
                                autor_id=usuario["id"], perfil_id=perfil_id,
                            )
                            recarregar_com_feedback(f"Usuário {email} cadastrado no perfil '{perfis_por_id[perfil_id]['nome']}'.")
                        except ValueError as erro:
                            st.error(str(erro))

        if modo_usuarios == "Cadastrar":
            return

        if usuarios:
            filtro_usuario = st.text_input("Buscar por nome, e-mail ou perfil", key="filtro_usuarios").strip().lower()
            usuarios_filtrados = [
                u for u in usuarios
                if not filtro_usuario or filtro_usuario in f"{u['nome']} {u['email']} {u.get('perfil_nome') or ''}".lower()
            ]
            st.caption(f"{len(usuarios_filtrados)} conta(s) encontrada(s).")
            tabela_usuarios(usuarios_filtrados, pode_gerenciar_usuarios, abrir_perfil_usuario_admin, para_horario_local)

        else:
            st.info("Nenhum usuário cadastrado.")

    if navegacao == "Perfil do usuário":
        painel_perfil_usuario_admin(usuario)

def secao_configurar_autenticador(usuario):
    with st.sidebar.expander("Autenticação em duas etapas"):
        if usuario.get("totp_secret"):
            st.write("✅ App autenticador já configurado.")
            st.caption("Os códigos de login virão do seu app, não mais por e-mail.")
        else:
            st.write("Ainda usando código por e-mail. Para usar um app autenticador:")
            if "totp_secret_temp" not in st.session_state:
                st.session_state.totp_secret_temp = None

            if st.button("Gerar QR code"):
                st.session_state.totp_secret_temp = gerar_totp_secret()
                st.rerun()

            if st.session_state.totp_secret_temp:
                qr = gerar_qrcode_totp(st.session_state.totp_secret_temp, usuario["email"])
                st.image(qr, caption="Escaneie no Google Authenticator/Authy")
                codigo_confirmacao = st.text_input("Digite o código gerado pelo app para confirmar", key="confirma_totp")
                if st.button("Confirmar e ativar"):
                    if verificar_totp(st.session_state.totp_secret_temp, codigo_confirmacao):
                        salvar_totp_secret(usuario["id"], st.session_state.totp_secret_temp, autor_id=usuario["id"])
                        st.session_state.totp_secret_temp = None
                        st.success("Autenticador ativado!")
                        st.session_state.usuario_logado["totp_secret"] = "ativo"
                        st.rerun()
                    else:
                        st.error("Código incorreto. Tente novamente.")




def paginas_permitidas_usuario(usuario):
    """Retorna as páginas cuja permissão está ativa no perfil atual do usuário."""
    return paginas_autorizadas(lambda permissao: usuario_tem_permissao(usuario["id"], permissao))


def exibir_navegacao(usuario):
    """Monta links de página conforme as permissões efetivas do perfil."""
    paginas_permitidas = paginas_permitidas_usuario(usuario)
    with st.sidebar:
        st.caption("SERVICE DESK")
        st.markdown("### Central de Chamados")
        st.write(usuario['nome'])
        st.divider()
        st.caption("Áreas disponíveis")


        for _chave, (_permissao, pagina, rotulo, icone) in paginas_permitidas.items():
            st.page_link(pagina, label=rotulo, icon=icone)


def exibir_acoes_sessao(usuario):
    """Exibe ações da conta depois de qualquer submenu contextual da página."""
    with st.sidebar:
        st.divider()
        if usuario_eh_administrador(usuario["id"]):
            st.divider()
            secao_configurar_autenticador(usuario)
        st.divider()
        if st.button("Sair", width="stretch"):
            sair()


def _executar_aplicacao_legacy(pagina_solicitada=None):
    """Autenticação e autorização precedem qualquer tela de trabalho."""
    try:
        pronto = schema_pronto()
    except mysql.connector.Error:
        st.error("Não conseguimos conectar ao banco de dados. Verifique se o MySQL está em execução e tente novamente.")
        if st.button("Tentar conectar novamente"):
            st.rerun()
        return
    if not pronto:
        st.error("O banco não está atualizado. Um administrador deve executar `python migrations.py upgrade` em uma janela de manutenção.")
        return
    inicializar_estado_sessao()
    if st.session_state.usuario_pendente_2fa is not None:
        tela_2fa()
        return

    if st.session_state.usuario_logado is None:
        if pagina_solicitada:
            st.warning("Faça login para acessar esta página.")
            st.page_link("app.py", label="Ir para o login", icon="🔐")
        elif st.session_state.tela_atual == "esqueci_senha_pedir":
            tela_esqueci_senha_pedir()
        elif st.session_state.tela_atual == "esqueci_senha_confirmar":
            tela_esqueci_senha_confirmar()
        else:
            tela_login()
        return

    usuario = st.session_state.usuario_logado
    fechar_chamados_resolvidos_automaticamente()
    if not st.session_state.login_auditoria_registrada:
        registrar_login(usuario["id"])
        st.session_state.login_auditoria_registrada = True

    if not st.session_state.aceite_privacidade_validado:
        if not usuario_aceitou_politica(usuario["id"]):
            tela_aceite_privacidade(usuario)
            return
        st.session_state.aceite_privacidade_validado = True

    if pagina_solicitada is None:
        destino, secao = destino_inicial(lambda permissao: usuario_tem_permissao(usuario["id"], permissao))
        if destino:
            if secao:
                st.session_state[{"admin": "admin_nav", "analista": "analista_nav", "usuario": "usuario_nav"}[destino]] = secao
            st.switch_page(PAGINAS_POR_PERMISSAO[destino][1])


        st.error("Seu perfil não possui acesso a nenhuma área do sistema. Contate o administrador.")
        return

    exibir_navegacao(usuario)
    paginas_permitidas = paginas_permitidas_usuario(usuario)
    if pagina_solicitada not in paginas_permitidas:
        st.error("Você não tem permissão para acessar esta página.")
        st.page_link("app.py", label="Voltar ao login", icon="🔐")
        return

    try:
        if pagina_solicitada == "usuario":
            tela_usuario(usuario)
        elif pagina_solicitada == "analista":
            tela_analista(usuario)
        elif pagina_solicitada == "admin":
            tela_admin(usuario)
    except PermissionError:
        st.error("Sua permissão para esta operação não está disponível. Atualize a página ou solicite a revisão do acesso.")
    except ValueError as erro:
        st.error(str(erro))
    except mysql.connector.Error:
        st.error("Não foi possível concluir a operação no banco. Seus filtros foram mantidos; tente novamente.")

    exibir_acoes_sessao(usuario)


# Mantém o ponto de entrada público usado por app.py e pelas páginas multipágina.
executar_aplicacao = _executar_aplicacao_legacy
