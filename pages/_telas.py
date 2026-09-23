import re
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path

from ia_engine import (
    classificar_chamado, conversar_coleta,
)
from rag import listar_artigos
import sla
from database import (
    salvar_chamado, criar_tabela_usuarios, migrar_tabela_usuarios,
    criar_tabela_chamados, migrar_tabela_chamados, criar_tabela_mensagens,
    criar_tabela_codigos, listar_chamados, buscar_chamado_por_id,
    atualizar_status_chamado, atribuir_chamado, listar_mensagens_chamado,
    enviar_mensagem_chamado, listar_usuarios, criar_usuario,
    buscar_usuario_por_email, atualizar_senha, salvar_totp_secret,
    salvar_codigo_verificacao, verificar_codigo, buscar_usuario_por_id,
    atualizar_usuario, excluir_usuario,
    criar_tabela_anexos, salvar_anexo_chamado, listar_anexos_chamado,
    criar_tabela_pesquisas_satisfacao, buscar_pesquisa_satisfacao,
    salvar_pesquisa_satisfacao,
    criar_tabela_atendimentos_ia, salvar_atendimento_ia,
    registrar_resultado_atendimento_ia, listar_atendimentos_ia,
    criar_tabela_auditoria, registrar_auditoria, registrar_login,
    cancelar_chamado_sem_atribuicao,
    confirmar_resolucao_usuario,
    reabrir_chamado_usuario,
)
from auth import (
    autenticar, gerar_hash_senha, gerar_codigo_numerico, gerar_totp_secret,
    gerar_qrcode_totp, verificar_totp,
)
from email_utils import enviar_email

criar_tabela_usuarios()
migrar_tabela_usuarios()
criar_tabela_chamados()
migrar_tabela_chamados()
criar_tabela_mensagens()
criar_tabela_codigos()
criar_tabela_anexos()
criar_tabela_pesquisas_satisfacao()
criar_tabela_atendimentos_ia()
criar_tabela_auditoria()


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

CORES_STATUS = {
    "Novo": "#2563eb",          
    "Aberto": "#2563eb",        
    "Em Andamento": "#d97706",  
    "Em Espera": "#7c3aed",   
    "Resolvido": "#16a34a",    
    "Fechado": "#475569",      
    "Cancelado": "#64748b",
}

CORES_URGENCIA = {
    "Critica": "#dc2626",
    "Alta": "#ea580c",
    "Media": "#d97706",
    "Baixa": "#16a34a",
}


def injetar_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }

        .app-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 0.9rem 1.4rem; border-radius: 12px; margin-bottom: 1.4rem;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f8fafc;
        }
        .app-header h1 { font-size: 1.25rem; margin: 0; color: #f8fafc; }
        .app-header .sub { font-size: 0.82rem; color: #94a3b8; margin-top: 2px; }

        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 0.72rem; font-weight: 600; color: white; letter-spacing: .2px;
        }

        .card {
            border: 1px solid #e2e8f0; border-left: 4px solid #e2e8f0; border-radius: 12px;
            padding: 1rem 1.2rem; margin-bottom: 0.8rem; background: #ffffff; color: #0f172a;
        }
        .card:hover { border-color: #cbd5e1; }
        .card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; color: #0f172a; }
        .card-meta { font-size: 0.78rem; color: #64748b; }

        .card-sla-violado { border-left: 4px solid #dc2626; }
        .card-sla-risco { border-left: 4px solid #d97706; }
        .card-sla-pausado { border-left: 4px solid #7c3aed; }

        .ticket-selected {
            border: 1px solid #2563eb; box-shadow: 0 0 0 1px #2563eb inset;
        }

        .metric-row { display: flex; gap: 0.8rem; margin-bottom: 1rem; }

        .sla-pill {
            display: inline-block; background: #f1f5f9; border-radius: 8px;
            padding: 2px 8px; font-size: 0.75rem; color: #334155; margin-right: 6px;
        }

        .artigo-card {
            border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.2rem;
            margin-bottom: 0.8rem; background: #ffffff;
        }
        .artigo-titulo { font-weight: 700; font-size: 1.02rem; color: #0f172a; margin-bottom: 4px; }
        .artigo-resumo { font-size: 0.85rem; color: #475569; }
        .artigo-tag {
            display: inline-block; background: #f1f5f9; color: #334155;
            border-radius: 999px; padding: 2px 10px; font-size: 0.72rem;
            margin: 6px 6px 0 0;
        }
        .artigo-secao-titulo {
            font-weight: 600; font-size: 0.86rem; color: #0f172a;
            margin: 0.9rem 0 0.3rem 0; display: flex; align-items: center; gap: 6px;
        }
    </style>
    """, unsafe_allow_html=True)


CATEGORIA_COR = {
    "Acesso": "#2563eb",
    "Software": "#7c3aed",
    "Hardware": "#d97706",
    "Rede": "#0891b2",
    "Outros": "#64748b",
}

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
            st.markdown(f'<div class="artigo-secao-titulo">{icone} {titulo_secao}</div>', unsafe_allow_html=True)
            st.markdown(conteudo_secao)
        else:
            st.markdown(bloco)


def badge(texto, cor):
    return f'<span class="badge" style="background:{cor};">{texto}</span>'


def badge_status(status):
    return badge(status or "-", CORES_STATUS.get(status, "#64748b"))


def badge_urgencia(urgencia):
    return badge(urgencia or "-", CORES_URGENCIA.get(urgencia, "#64748b"))


def badge_sla(texto, status_sla_texto):
    return badge(texto, sla.CORES_SLA.get(status_sla_texto, "#64748b"))


def classe_card_sla(estado_sla):
    pior = sla.pior_status(estado_sla)
    if pior == "Violado":
        return " card-sla-violado"
    if pior == "Em risco":
        return " card-sla-risco"
    if pior == "Pausado":
        return " card-sla-pausado"
    return ""


def linha_sla_card(estado_sla):
    resp = estado_sla["resposta"]
    reso = estado_sla["resolucao"]
    texto_resp = f"Resposta: {resp['status']}"
    texto_reso = f"Resolução: {reso['status']}"
    return (
        f"{badge_sla(texto_resp, resp['status'])} "
        f"{badge_sla(texto_reso, reso['status'])}"
    )


def bloco_sla_detalhe(chamado, estado_sla):
    resp = estado_sla["resposta"]
    reso = estado_sla["resolucao"]

    linhas = [
        f'<span class="sla-pill">Prazo de resposta: {sla.formatar_data(chamado.get("prazo_resposta"))}</span>',
        badge_sla(resp["status"], resp["status"]),
    ]
    if resp["minutos_restantes"] is not None:
        linhas.append(f'<span class="sla-pill">{sla.formatar_tempo_restante(resp["minutos_restantes"])}</span>')

    st.markdown(" ".join(linhas), unsafe_allow_html=True)

    linhas2 = [
        f'<span class="sla-pill">Prazo de resolução: {sla.formatar_data(chamado.get("prazo_resolucao"))}</span>',
        badge_sla(reso["status"], reso["status"]),
    ]
    if reso["minutos_restantes"] is not None:
        linhas2.append(f'<span class="sla-pill">{sla.formatar_tempo_restante(reso["minutos_restantes"])}</span>')

    st.markdown(" ".join(linhas2), unsafe_allow_html=True)

    if chamado.get("tempo_pausado_min") or chamado.get("pausado_em"):
        st.caption("⏸ O relógio de SLA fica pausado enquanto o chamado está em 'Em Espera' (aguardando o solicitante).")


def cabecalho(titulo, subtitulo, icone="🎫"):
    st.markdown(f"""
    <div class="app-header">
        <div>
            <h1>{icone} {titulo}</h1>
            <div class="sub">{subtitulo}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


ESTADO_INICIAL_SESSAO = {
    "usuario_logado": None,
    "usuario_pendente_2fa": None,
    "login_auditoria_registrada": False,
    "admin_nav": "Usuários",
    "tela_atual": "login",
    "email_recuperacao": None,
    "chamado_selecionado_analista": None,
    "chamado_selecionado_historico": None,
    "chamado_selecionado_cancelado": None,
    "usuario_admin_aberto": None,
    "chamado_aberto_usuario": None,
}


def inicializar_estado_sessao():
    """Garante o estado de cada sessão, inclusive quando o módulo já está em cache."""
    for chave, valor_inicial in ESTADO_INICIAL_SESSAO.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor_inicial


def tela_login():
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Sistema Inteligente de Chamados")
        st.caption("Central de Serviços de TI - faça login para continuar")
        st.caption("Os acessos e ações relevantes são auditados para segurança do serviço.")

        with st.container(border=True):
            with st.form("form_login"):
                email = st.text_input("Email")
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

            if entrar:
                usuario = autenticar(email, senha)
                if usuario is None:
                    registrar_auditoria(None, "LOGIN_FALHOU", "sessao", resultado="FALHA")
                    st.error("Email ou senha inválidos.")
                elif usuario["papel"] == "admin":
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

            if st.button("Esqueci minha senha", use_container_width=True):
                st.session_state.tela_atual = "esqueci_senha_pedir"
                st.rerun()


def tela_2fa():
    injetar_css()
    usuario = st.session_state.usuario_pendente_2fa
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("### Verificação em duas etapas")

        usa_app = bool(usuario.get("totp_secret"))
        with st.container(border=True):
            if usa_app:
                st.write("Abra seu aplicativo autenticador (Google Authenticator, Authy, etc) e digite o código de 6 dígitos.")
            else:
                st.write(f"Enviamos um código para **{usuario['email']}**. Confira sua caixa de entrada (e o spam).")

            with st.form("form_2fa"):
                codigo = st.text_input("Código de verificação")
                confirmar = st.form_submit_button("Confirmar", use_container_width=True, type="primary")

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

            if st.button("Cancelar e voltar", use_container_width=True):
                st.session_state.usuario_pendente_2fa = None
                st.rerun()


def tela_esqueci_senha_pedir():
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("### Recuperar senha")
        with st.container(border=True):
            with st.form("form_pedir_codigo"):
                email = st.text_input("Digite seu email cadastrado")
                enviar = st.form_submit_button("Enviar código de recuperação", use_container_width=True, type="primary")

            if enviar:
                usuario = buscar_usuario_por_email(email)
                if usuario is None:
                    registrar_auditoria(None, "RECUPERACAO_SENHA_SOLICITADA", "sessao", resultado="FALHA")
                    st.error("Não encontramos nenhuma conta com esse e-mail.")
                else:
                    codigo = gerar_codigo_numerico()
                    salvar_codigo_verificacao(usuario["id"], codigo, tipo="reset_senha")
                    registrar_auditoria(usuario["id"], "RECUPERACAO_SENHA_SOLICITADA", "sessao")
                    try:
                        enviar_email(
                            email,
                            "Recuperação de senha",
                            f"Seu código de recuperação é: {codigo}\nEle expira em 10 minutos.",
                        )
                        st.session_state.email_recuperacao = email
                        st.session_state.tela_atual = "esqueci_senha_confirmar"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Não foi possível enviar o e-mail: {e}")

            if st.button("Voltar ao login", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()


def tela_esqueci_senha_confirmar():
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("### Recuperar senha")
        st.caption(f"Código enviado para {st.session_state.email_recuperacao}")

        with st.container(border=True):
            with st.form("form_confirmar_codigo"):
                codigo = st.text_input("Código recebido por e-mail")
                nova_senha = st.text_input("Nova senha", type="password")
                confirmar = st.form_submit_button("Redefinir senha", use_container_width=True, type="primary")

            if confirmar:
                usuario = buscar_usuario_por_email(st.session_state.email_recuperacao)
                if usuario and verificar_codigo(usuario["id"], codigo, tipo="reset_senha"):
                    atualizar_senha(usuario["id"], gerar_hash_senha(nova_senha))
                    st.success("Senha redefinida com sucesso! Faça login com a nova senha.")
                    st.session_state.tela_atual = "login"
                    st.session_state.email_recuperacao = None
                else:
                    registrar_auditoria(
                        usuario["id"] if usuario else None, "RECUPERACAO_SENHA_FALHOU",
                        "sessao", resultado="FALHA",
                    )
                    st.error("Código inválido ou expirado.")

            if st.button("Voltar ao login", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()


def sair():
    usuario = st.session_state.get("usuario_logado")
    if usuario:
        registrar_auditoria(usuario["id"], "LOGOUT_REALIZADO", "sessao")
    st.session_state.usuario_logado = None
    st.session_state.login_auditoria_registrada = False
    for chave in (
        "chat_mensagens", "chat_turnos_usuario", "chat_resultado_final", "chat_etapa",
        "chamado_aberto_usuario", "chamado_selecionado_analista",
        "chamado_selecionado_historico", "chamado_selecionado_cancelado",
    ):
        st.session_state.pop(chave, None)
    st.rerun()


def painel_conversa_chamado(chamado, usuario_atual, papel_atual, key_prefix):
    mensagens = listar_mensagens_chamado(chamado["id"])

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
    anexos = listar_anexos_chamado(chamado["id"])
    if anexos:
        st.markdown("##### Anexos")
        for anexo in anexos:
            st.download_button(
                f"Baixar {anexo['nome_arquivo']}",
                data=anexo["conteudo"],
                file_name=anexo["nome_arquivo"],
                mime=anexo.get("tipo_arquivo") or "application/octet-stream",
                key=f"{key_prefix}_baixar_{anexo['id']}",
            )

    if chamado["status"] in STATUS_ENCERRADOS:
        return

    with st.form(f"{key_prefix}_form_anexo_{chamado['id']}", clear_on_submit=True):
        arquivo = st.file_uploader(
            "Adicionar anexo à conversa (máximo de 10 MB)",
            key=f"{key_prefix}_anexo_{chamado['id']}",
        )
        enviar = st.form_submit_button("Enviar anexo", use_container_width=True)

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
                    st.success("Anexo adicionado ao chamado.")
                    st.rerun()


def painel_pesquisa_satisfacao(chamado, usuario):
    if chamado["status"] != "Fechado":
        return
    pesquisa = buscar_pesquisa_satisfacao(chamado["id"])
    st.markdown("##### Pesquisa de satisfação")
    if pesquisa:
        st.success(f"Pesquisa respondida: {pesquisa['nota']}/5")
        if pesquisa.get("comentario"):
            st.caption(pesquisa["comentario"])
        return
    with st.form(f"pesquisa_{chamado['id']}"):
        nota = st.radio("Como foi o atendimento?", [1, 2, 3, 4, 5], horizontal=True, format_func=lambda n: f"{n} ★")
        comentario = st.text_area("Comentário (opcional)")
        responder = st.form_submit_button("Enviar avaliação")
    if responder:
        salvar_pesquisa_satisfacao(chamado["id"], nota, comentario.strip() or None, autor_id=usuario["id"])
        st.success("Obrigado pela sua avaliação!")
        st.rerun()


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

    def _artigo_corresponde(artigo):
        if categoria_filtro != "Todas" and artigo["categoria"] != categoria_filtro:
            return False
        if not termo_busca:
            return True
        alvo = " ".join([
            artigo["titulo"],
            artigo["resumo"],
            artigo["categoria"],
            " ".join(artigo["tags"]),
            artigo["corpo"],
        ]).lower()
        return all(palavra in alvo for palavra in termo_busca.split())

    artigos_filtrados = [a for a in artigos if _artigo_corresponde(a)]

    st.caption(f"{len(artigos_filtrados)} de {len(artigos)} orientação(ões)")

    if not artigos_filtrados:
        st.warning("Nenhuma orientação encontrada para essa busca. Tente outro termo ou abra um chamado na aba ao lado.")
        return

    for artigo in artigos_filtrados:
        cor = CATEGORIA_COR.get(artigo["categoria"], "#64748b")
        with st.expander(artigo["titulo"]):
            st.markdown(
                f'{badge(artigo["categoria"], cor)} '
                f'<span class="artigo-resumo">&nbsp; {artigo["resumo"]}</span>',
                unsafe_allow_html=True,
            )
            if artigo["tags"]:
                tags_html = "".join(f'<span class="artigo-tag">{t}</span>' for t in artigo["tags"][:8])
                st.markdown(tags_html, unsafe_allow_html=True)
            _renderizar_secoes_artigo(artigo["corpo"])


def tela_usuario(usuario):
    injetar_css()
    cabecalho("Central de Chamados", f"Bem-vindo(a), {usuario['nome']}", "🎫")

    aba_portal, aba_chat, aba_chamados = st.tabs(["Central de ajuda", "Abrir novo chamado", "Meus chamados"])

    with aba_portal:
        _aba_portal_conhecimento()

    with aba_chat:
        _aba_abrir_chamado(usuario)

    with aba_chamados:
        aba_ativos, aba_finalizados, aba_cancelados = st.tabs(
            ["Ativos", "Fechados", "Cancelados"]
        )
        with aba_ativos:
            _aba_meus_chamados(usuario, "ativos")
        with aba_finalizados:
            _aba_meus_chamados(usuario, "fechados")
        with aba_cancelados:
            _aba_meus_chamados(usuario, "cancelados")


def _aba_abrir_chamado(usuario):
    st.caption("Envie sua mensagem. A IA analisa o caso em uma única etapa, pergunta apenas o necessário e sugere uma solução segura quando possível.")

    if "chat_mensagens" not in st.session_state:
        st.session_state.chat_mensagens = [
            {"role": "assistant", "content": "Olá! Como posso ajudar? Você pode tirar uma dúvida ou descrever um problema."}
        ]
    if "chat_resultado_final" not in st.session_state:
        st.session_state.chat_resultado_final = None

    def reiniciar_conversa():
        st.session_state.chat_mensagens = [
            {"role": "assistant", "content": "Olá! Como posso ajudar? Você pode tirar uma dúvida ou descrever um problema."}
        ]
        st.session_state.chat_resultado_final = None

    with st.container(border=True):
        for msg in st.session_state.chat_mensagens:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        if st.session_state.chat_resultado_final is None:
            entrada = st.chat_input("Digite sua resposta...")
            if entrada:
                st.session_state.chat_mensagens.append({"role": "user", "content": entrada})

                with st.spinner("A IA está processando..."):
                    resultado = conversar_coleta(st.session_state.chat_mensagens)

                if resultado["acao"] in {"orientar", "perguntar"}:
                    st.session_state.chat_mensagens.append({"role": "assistant", "content": resultado["mensagem"]})
                    st.rerun()
                elif resultado["acao"] == "solucionar":
                    atendimento_ia_id = salvar_atendimento_ia(
                        usuario["id"], resultado["titulo"], resultado["descricao"], resultado["solucao"],
                    )
                    st.session_state.chat_mensagens.append({"role": "assistant", "content": resultado["mensagem"]})
                    st.session_state.chat_resultado_final = {
                        "status": "solucao_sugerida",
                        "atendimento_ia_id": atendimento_ia_id,
                        "titulo": resultado["titulo"],
                        "descricao": resultado["descricao"],
                        "solucao": resultado["solucao"],
                    }
                    st.rerun()
                else:
                    st.session_state.chat_mensagens.append({
                        "role": "assistant",
                        "content": "Preparei os dados do chamado. Revise-os abaixo e confirme a abertura quando estiver tudo correto."
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
                st.success("Encontrei uma possível solução com base nos dados informados.")
                st.markdown("##### Solução sugerida")
                st.markdown(resultado["solucao"])
                st.caption("Siga apenas os passos indicados. Se não resolver, você poderá abrir o chamado com os dados já coletados.")

                col_resolvido, col_abrir = st.columns(2)
                with col_resolvido:
                    resolvido = st.button("A solução resolveu o problema", type="primary", use_container_width=True)
                with col_abrir:
                    abrir_chamado = st.button("Não resolveu — abrir chamado", use_container_width=True)

                if resolvido:
                    registrar_resultado_atendimento_ia(resultado["atendimento_ia_id"], "Resolvido")
                    st.session_state.chat_mensagens.append({
                        "role": "assistant",
                        "content": "Ótimo! Fico feliz que o problema tenha sido resolvido."
                    })
                    st.session_state.chat_resultado_final = {"status": "resolvido_pelo_usuario"}
                    st.rerun()
                if abrir_chamado:
                    registrar_resultado_atendimento_ia(resultado["atendimento_ia_id"], "Nao resolvido")
                    st.session_state.chat_resultado_final = {
                        "status": "aguardando_confirmacao",
                        "atendimento_ia_id": resultado["atendimento_ia_id"],
                        "titulo": resultado["titulo"],
                        "descricao": resultado["descricao"],
                    }
                    st.rerun()

            elif resultado.get("status") == "aguardando_confirmacao":
                st.info("Confira ou ajuste os dados. O chamado só será aberto após sua confirmação.")
                with st.form("form_confirmar_abertura"):
                    titulo = st.text_input("Título", value=resultado["titulo"], max_chars=255)
                    descricao = st.text_area("Descrição", value=resultado["descricao"], height=180)
                    confirmar = st.form_submit_button("Confirmar e abrir chamado", type="primary")

                _, col_nova = st.columns(2)
                with col_nova:
                    nova_conversa = st.button("Iniciar nova conversa", use_container_width=True)

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
                            )
                            if resultado.get("atendimento_ia_id"):
                                registrar_resultado_atendimento_ia(
                                    resultado["atendimento_ia_id"], "Nao resolvido", chamado_id,
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

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Categoria", resultado.get("categoria", "N/A"))
                    st.metric("Urgência", resultado.get("urgencia", "N/A"))
                    st.metric("Equipe destino", resultado.get("equipe_destino", "N/A"))
                with col2:
                    st.metric("SLA de resposta", resultado.get("tempo_sla_resposta", "N/A"))
                    st.metric("SLA de resolução", resultado.get("tempo_sla_resolucao", "N/A"))
                    st.metric("Confiabilidade (IA)", resultado.get("confiabilidade", "N/A"))

                if st.button("Iniciar nova conversa", type="primary"):
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
    chamados = listar_chamados(limite=50, usuario_id=usuario["id"])

    if grupo == "ativos":
        chamados = [c for c in chamados if c["status"] not in STATUS_ENCERRADOS]
        titulo_grupo = "ativo(s)"
    elif grupo == "fechados":
        chamados = [c for c in chamados if c["status"] == "Fechado"]
        titulo_grupo = "fechado(s)"
    else:
        chamados = [c for c in chamados if c["status"] == "Cancelado"]
        titulo_grupo = "cancelado(s)"

    if not chamados:
        st.info(f"Você não possui chamados {titulo_grupo}.")
        return

    st.caption(f"{len(chamados)} chamado(s) {titulo_grupo} — clique em um para ver detalhes.")

    lista_col, detalhe_col = st.columns([1, 1.6])

    with lista_col:
        for c in chamados:
            selecionado = st.session_state.chamado_aberto_usuario == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            estado_sla = sla.status_sla(c)
            classe_extra += classe_card_sla(estado_sla)
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
                <div class="card-meta" style="margin-top:6px;">{linha_sla_card(estado_sla)}</div>
                <div class="card-meta" style="margin-top:6px;">Analista: {c.get('nome_analista') or 'Aguardando atribuição'}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Ver detalhes", key=f"ver_{c['id']}", use_container_width=True):
                st.session_state.chamado_aberto_usuario = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_aberto_usuario
        if chamado_id_sel is None:
            st.info("Selecione um chamado na lista ao lado.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel)
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
            st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            st.write(chamado["descricao"])

            st.markdown(f'<span class="sla-pill">👥 Equipe: {chamado.get("equipe_destino") or "—"}</span>', unsafe_allow_html=True)
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))
            st.caption(f"Analista responsável: {chamado.get('nome_analista') or 'Aguardando atribuição'}")
            if chamado["status"] == "Cancelado":
                st.caption(f"Motivo do cancelamento: {chamado.get('motivo_cancelamento') or 'Não informado'}")

        st.markdown("##### Conversa com o analista")
        painel_conversa_chamado(chamado, usuario, "usuario", key_prefix="usr")
        painel_anexos_chamado(chamado, usuario, key_prefix="usr")

        if chamado["status"] == "Novo" and chamado.get("analista_id") is None:
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
                        st.success("Chamado cancelado.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()

        elif chamado["status"] == "Resolvido":
            st.divider()
            st.info("O analista marcou este chamado como resolvido. Confirme o resultado ou solicite a reabertura.")
            confirmar, reabrir = st.columns(2)
            with confirmar:
                if st.button("Confirmar solução", type="primary", key=f"fechar_{chamado['id']}"):
                    try:
                        confirmar_resolucao_usuario(chamado["id"], usuario["id"])
                        st.success("Solução confirmada. Chamado fechado.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()
            with reabrir:
                if st.button("Solicitar reabertura", key=f"reabrir_{chamado['id']}"):
                    try:
                        reabrir_chamado_usuario(chamado["id"], usuario["id"])
                        st.success("Chamado reaberto e devolvido para atendimento.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()

        painel_pesquisa_satisfacao(chamado, usuario)


def tela_analista(usuario):
    injetar_css()
    cabecalho("Central de Serviços — Analista", f"{usuario['nome']} · Gestão de Incidentes")

    chamados = listar_chamados(limite=200)
    if not chamados:
        st.info("Nenhum chamado registrado ainda.")
        return

    aba_fila, aba_historico, aba_cancelados = st.tabs(
        ["Fila Ativa", "Histórico (Fechados)", "Cancelados"]
    )

    with aba_fila:
        _aba_fila_ativa_analista(usuario, chamados)

    with aba_historico:
        _aba_historico_analista(usuario, chamados)

    with aba_cancelados:
        _aba_cancelados_analista(usuario, chamados)


def _aba_fila_ativa_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] not in STATUS_ENCERRADOS]
    ordem_urgencia = {"Critica": 0, "Alta": 1, "Media": 2, "Baixa": 3}
    chamados.sort(key=lambda c: (ordem_urgencia.get(c.get("urgencia"), 4), c.get("criado_em")))

    total = len(chamados)
    novos = sum(1 for c in chamados if c["status"] == "Novo")
    em_andamento = sum(1 for c in chamados if c["status"] == "Em Andamento")
    meus = sum(1 for c in chamados if c.get("analista_id") == usuario["id"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chamados ativos", total)
    m2.metric("Novos", novos)
    m3.metric("Em andamento", em_andamento)
    m4.metric("Atribuídos a mim", meus)

    st.divider()

    filtro_col1, filtro_col2, filtro_col3 = st.columns([1.2, 1.2, 1])
    with filtro_col1:
        filtro_status = st.multiselect("Status", options=STATUS_OPCOES, default=[], key="filtro_status_ativa")
    with filtro_col2:
        filtro_urgencia = st.multiselect("Urgência", options=["Critica", "Alta", "Media", "Baixa"], default=[], key="filtro_urgencia_ativa")
    with filtro_col3:
        st.write("")
        st.write("")
        somente_meus = st.checkbox("Somente meus chamados", key="somente_meus_ativa")

    chamados_filtrados = chamados
    if filtro_status:
        chamados_filtrados = [c for c in chamados_filtrados if c["status"] in filtro_status]
    if filtro_urgencia:
        chamados_filtrados = [c for c in chamados_filtrados if c["urgencia"] in filtro_urgencia]
    if somente_meus:
        chamados_filtrados = [c for c in chamados_filtrados if c.get("analista_id") == usuario["id"]]

    fila_col, detalhe_col = st.columns([1, 1.6])

    with fila_col:
        st.markdown("##### Fila de chamados")
        if not chamados_filtrados:
            st.caption("Nenhum chamado com os filtros selecionados.")
        for c in chamados_filtrados:
            selecionado = st.session_state.chamado_selecionado_analista == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            estado_sla = sla.status_sla(c)
            classe_extra += classe_card_sla(estado_sla)
            responsavel = c.get("nome_analista") or "Sem atribuição"
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
                <div class="card-meta" style="margin-top:6px;">{linha_sla_card(estado_sla)}</div>
                <div class="card-meta" style="margin-top:6px;">👤 {c.get('nome_usuario') or '—'} · 🧑‍💻 {responsavel}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Selecionar", key=f"sel_{c['id']}", use_container_width=True):
                st.session_state.chamado_selecionado_analista = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_selecionado_analista
        if chamado_id_sel is None:
            st.info("Selecione um chamado na fila para atender.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel)
        if not chamado:
            st.warning("Chamado não encontrado.")
            st.session_state.chamado_selecionado_analista = None
            return

        with st.container(border=True):
            topo_esq, topo_dir = st.columns([3, 1])
            with topo_esq:
                st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
                st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            with topo_dir:
                analista_atribuido = chamado.get("analista_id")
                ja_atribuido_a_mim = analista_atribuido == usuario["id"]
                if analista_atribuido is None:
                    if st.button("Atender chamado", type="primary", use_container_width=True):
                        try:
                            atribuir_chamado(chamado["id"], usuario["id"])
                        except ValueError as erro:
                            st.error(str(erro))
                        st.rerun()
                    if st.button("Cancelar chamado", key=f"cancelar_analista_{chamado['id']}", use_container_width=True):
                        st.session_state[f"mostrar_cancelamento_analista_{chamado['id']}"] = True
                        st.rerun()
                else:
                    if ja_atribuido_a_mim:
                        st.success("Você está atendendo")
                    else:
                        st.warning(f"Atribuído a {chamado.get('nome_analista') or 'outro analista'}")

            st.write(chamado["descricao"])

            st.markdown(
                f'<span class="sla-pill"> {chamado.get("categoria") or "—"}</span>'
                f'<span class="sla-pill"> Equipe: {chamado.get("equipe_destino") or "—"}</span>'
                f'<span class="sla-pill"> Confiabilidade IA: {chamado.get("confiabilidade") or "—"}</span>',
                unsafe_allow_html=True,
            )
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))
            st.caption(f"Solicitante: {chamado.get('nome_usuario') or '-'} · Aberto em {chamado.get('criado_em').strftime('%d/%m/%Y %H:%M:%S')}")

            if ja_atribuido_a_mim and chamado["status"] == "Em Andamento":
                st.divider()
                st.caption("Uma mensagem enviada ao solicitante coloca o chamado automaticamente em espera até a resposta dele.")
                if st.button("Marcar como resolvido", type="primary", use_container_width=True):
                    try:
                        atualizar_status_chamado(chamado["id"], "Resolvido", autor_id=usuario["id"])
                        st.success("Aguardando a confirmação do solicitante.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()
            elif ja_atribuido_a_mim and chamado["status"] == "Em Espera":
                st.info("Aguardando a resposta do solicitante. Quando ele responder, o chamado volta automaticamente para Em Andamento.")
            elif ja_atribuido_a_mim and chamado["status"] == "Resolvido":
                st.info("Aguardando a confirmação do solicitante para fechar ou reabrir o chamado.")

        chave_cancelamento_analista = f"mostrar_cancelamento_analista_{chamado['id']}"
        if chamado.get("analista_id") is None and st.session_state.get(chave_cancelamento_analista):
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
                    st.success("Chamado cancelado.")
                except ValueError as erro:
                    st.error(str(erro))
                st.rerun()

        if chamado.get("analista_id") != usuario["id"]:
            st.info("Atribua este chamado a você para enviar mensagens, anexos ou executar ações de atendimento.")
            return

        st.markdown("##### Conversa com o solicitante")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="ana")
        painel_anexos_chamado(chamado, usuario, key_prefix="ana")


def _aba_historico_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] == "Fechado"]

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

    m1, m2, m3 = st.columns(3)
    m1.metric("Total fechados", total_fechados)
    m2.metric("SLA cumprido", dentro_prazo)
    m3.metric("Taxa de cumprimento", taxa_cumprimento)

    st.caption(
        "A taxa de cumprimento considera somente chamados fechados. "
        "Chamados cancelados ficam em uma lista separada e não compõem este indicador."
    )

    st.divider()

    filtro_col1, filtro_col2 = st.columns([1.2, 1])
    with filtro_col1:
        filtro_urgencia_hist = st.multiselect("Urgência", options=["Critica", "Alta", "Media", "Baixa"], default=[], key="filtro_urgencia_hist")
    with filtro_col2:
        somente_meus_hist = st.checkbox("Somente atendidos por mim", key="somente_meus_hist")

    chamados_filtrados = chamados
    if filtro_urgencia_hist:
        chamados_filtrados = [c for c in chamados_filtrados if c["urgencia"] in filtro_urgencia_hist]
    if somente_meus_hist:
        chamados_filtrados = [c for c in chamados_filtrados if c.get("analista_id") == usuario["id"]]

    lista_col, detalhe_col = st.columns([1, 1.6])

    with lista_col:
        st.markdown("##### Registros encerrados")
        if not chamados_filtrados:
            st.caption("Nenhum chamado fechado com os filtros selecionados.")
        for c in chamados_filtrados:
            estado_sla = sla.status_sla(c)
            selecionado = st.session_state.get("chamado_selecionado_historico") == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            classe_extra += classe_card_sla(estado_sla)
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
                <div class="card-meta" style="margin-top:6px;">{linha_sla_card(estado_sla)}</div>
                <div class="card-meta" style="margin-top:6px;">👤 {c.get('nome_usuario') or '—'} · 🧑‍💻 {c.get('nome_analista') or '—'}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Ver registro", key=f"hist_{c['id']}", use_container_width=True):
                st.session_state.chamado_selecionado_historico = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.get("chamado_selecionado_historico")
        if chamado_id_sel is None:
            st.info("Selecione um chamado fechado para ver o registro completo.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel)
        if not chamado or chamado["status"] != "Fechado":
            st.warning("Chamado não encontrado no histórico.")
            st.session_state.chamado_selecionado_historico = None
            return

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
            st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            st.write(chamado["descricao"])

            st.markdown(
                f'<span class="sla-pill"> {chamado.get("categoria") or "—"}</span>'
                f'<span class="sla-pill"> Equipe: {chamado.get("equipe_destino") or "—"}</span>'
                f'<span class="sla-pill"> Confiabilidade IA: {chamado.get("confiabilidade") or "—"}</span>',
                unsafe_allow_html=True,
            )
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))

            st.caption(
                f"Solicitante: {chamado.get('nome_usuario') or '—'} · "
                f"Atendido por: {chamado.get('nome_analista') or '—'}"
            )
            st.caption(
                f"Aberto em {sla.formatar_data(chamado.get('criado_em'))} · "
                f"Resolvido em {sla.formatar_data(chamado.get('resolvido_em'))}"
            )

        st.markdown("#####  Histórico da conversa")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="hist")
        painel_anexos_chamado(chamado, usuario, key_prefix="hist")


def _aba_cancelados_analista(usuario, chamados_todos):
    chamados = [c for c in chamados_todos if c["status"] == "Cancelado"]
    if not chamados:
        st.info("Nenhum chamado cancelado ainda.")
        return

    st.metric("Total cancelados", len(chamados))
    st.caption("Cancelamentos são mantidos para auditoria e não impactam a taxa de cumprimento de SLA.")

    lista_col, detalhe_col = st.columns([1, 1.6])
    with lista_col:
        st.markdown("##### Chamados cancelados")
        for c in chamados:
            selecionado = st.session_state.chamado_selecionado_cancelado == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
                <div class="card-meta" style="margin-top:6px;">👤 {c.get('nome_usuario') or '—'}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Ver registro", key=f"cancel_{c['id']}", use_container_width=True):
                st.session_state.chamado_selecionado_cancelado = c["id"]
                st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_selecionado_cancelado
        if chamado_id_sel is None:
            st.info("Selecione um chamado cancelado para consultar o registro.")
            return

        chamado = buscar_chamado_por_id(chamado_id_sel)
        if not chamado or chamado["status"] != "Cancelado":
            st.info("Selecione um chamado desta lista.")
            return

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado['titulo']}")
            st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            st.write(chamado["descricao"])
            st.caption(
                f"Solicitante: {chamado.get('nome_usuario') or '—'} · "
                "SLA: não aplicável (cancelado pelo usuário)."
            )
            st.caption(f"Motivo do cancelamento: {chamado.get('motivo_cancelamento') or 'Não informado'}")

        st.markdown("##### Histórico da conversa")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="cancel_hist")
        painel_anexos_chamado(chamado, usuario, key_prefix="cancel_hist")


def _exibir_grafico_barras(dados, titulo, eixo_x, eixo_y, cor="#2563eb"):
    """Exibe um gráfico Matplotlib consistente e trata conjuntos de dados vazios."""
    if dados.empty or dados[eixo_y].sum() == 0:
        st.info("Ainda não há dados suficientes para este gráfico.")
        return

    figura, eixo = plt.subplots(figsize=(7, 3.4))
    barras = eixo.bar(dados[eixo_x].astype(str), dados[eixo_y], color=cor)
    eixo.set_title(titulo, loc="left", fontweight="bold")
    eixo.set_xlabel("")
    eixo.set_ylabel(eixo_y)
    eixo.spines[["top", "right"]].set_visible(False)
    eixo.tick_params(axis="x", rotation=20)
    for barra in barras:
        altura = barra.get_height()
        eixo.annotate(f"{altura:.0f}", (barra.get_x() + barra.get_width() / 2, altura),
                      ha="center", va="bottom", fontsize=9)
    figura.tight_layout()
    st.pyplot(figura, use_container_width=True)
    plt.close(figura)


def relatorio_usuarios(usuarios):
    st.markdown("### Relatório de usuários")
    st.caption("Distribuição das contas cadastradas por função de acesso.")
    dados = pd.DataFrame(usuarios)
    funcoes = ["usuario", "analista", "admin"]
    distribuicao = (
        dados["papel"].value_counts().reindex(funcoes, fill_value=0)
        .rename_axis("Função").reset_index(name="Quantidade")
    ) if not dados.empty else pd.DataFrame({"Função": funcoes, "Quantidade": [0, 0, 0]})

    metricas = st.columns(4)
    metricas[0].metric("Total de contas", int(distribuicao["Quantidade"].sum()))
    for coluna, funcao in zip(metricas[1:], funcoes):
        quantidade = int(distribuicao.loc[distribuicao["Função"] == funcao, "Quantidade"].iloc[0])
        coluna.metric(funcao.capitalize() + "s", quantidade)

    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        _exibir_grafico_barras(distribuicao, "Contas por função", "Função", "Quantidade", "#0f766e")
    with tabela:
        st.dataframe(distribuicao, use_container_width=True, hide_index=True)


def relatorio_sla_desempenho(chamados):
    st.markdown("### Relatório de desempenho e cumprimento de SLA")
    st.caption("Cancelados não entram no cálculo. O cumprimento considera chamados com a respectiva etapa concluída.")
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados para calcular os indicadores de SLA.")
        return

    dados = dados[dados["status"] != "Cancelado"].copy()
    dados["SLA resposta"] = [sla.status_sla(c)["resposta"]["status"] for c in dados.to_dict("records")]
    dados["SLA resolução"] = [sla.status_sla(c)["resolucao"]["status"] for c in dados.to_dict("records")]
    respostas_concluidas = dados[dados["primeira_resposta_em"].notna()]
    resolucoes_concluidas = dados[dados["resolvido_em"].notna()]
    resposta_cumprida = int((respostas_concluidas["SLA resposta"] == "Cumprido").sum())
    resolucao_cumprida = int((resolucoes_concluidas["SLA resolução"] == "Cumprido").sum())
    taxa_resposta = resposta_cumprida / len(respostas_concluidas) * 100 if len(respostas_concluidas) else 0
    taxa_resolucao = resolucao_cumprida / len(resolucoes_concluidas) * 100 if len(resolucoes_concluidas) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados monitorados", len(dados))
    c2.metric("Resposta no prazo", f"{taxa_resposta:.1f}%", f"{resposta_cumprida}/{len(respostas_concluidas)} concluídos")
    c3.metric("Resolução no prazo", f"{taxa_resolucao:.1f}%", f"{resolucao_cumprida}/{len(resolucoes_concluidas)} concluídos")
    c4.metric("SLA em violação", int((dados["SLA resolução"] == "Violado").sum()))

    ordem = ["Cumprido", "Dentro do prazo", "Em risco", "Violado", "Pausado"]
    resumo = pd.DataFrame({
        "Status": ordem,
        "Resposta": dados["SLA resposta"].value_counts().reindex(ordem, fill_value=0).values,
        "Resolução": dados["SLA resolução"].value_counts().reindex(ordem, fill_value=0).values,
    })
    figura, eixo = plt.subplots(figsize=(8, 3.6))
    posicoes = range(len(resumo))
    eixo.bar([p - 0.2 for p in posicoes], resumo["Resposta"], width=0.4, label="Resposta", color="#2563eb")
    eixo.bar([p + 0.2 for p in posicoes], resumo["Resolução"], width=0.4, label="Resolução", color="#16a34a")
    eixo.set_xticks(list(posicoes), resumo["Status"], rotation=15)
    eixo.set_ylabel("Chamados")
    eixo.set_title("Situação dos prazos de SLA", loc="left", fontweight="bold")
    eixo.legend(frameon=False)
    eixo.spines[["top", "right"]].set_visible(False)
    figura.tight_layout()
    st.pyplot(figura, use_container_width=True)
    plt.close(figura)


def relatorio_ia(chamados):
    st.markdown("### Confiança da classificação da IA")
    st.caption(
        "Indica o quanto a IA considera confiável a categoria, a urgência e a equipe "
        "atribuídas a cada chamado. Não representa uma taxa de acertos validada."
    )
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados classificados pela IA para analisar.")
        return

    niveis = ["Alta", "Média", "Baixa"]
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

    resultados = pd.DataFrame({
        "Confiança da classificação": niveis,
        "Quantidade": distribuicao.values,
    })
    _exibir_grafico_barras(
        resultados,
        "Distribuição da confiança da classificação",
        "Confiança da classificação",
        "Quantidade",
        "#7c3aed",
    )


def relatorio_produtividade_equipe(chamados):
    st.markdown("### Relatório de produtividade da equipe")
    st.caption("Produção por analista, baseada nos chamados atribuídos. O tempo de resolução desconta períodos em espera registrados.")
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
    dados["tempo_resolucao_horas"] = ((dados["resolvido_em"] - dados["criado_em"]).dt.total_seconds() / 3600 - dados["tempo_pausado_min"].fillna(0) / 60).clip(lower=0)
    produtividade = dados.groupby("Analista", as_index=False).agg(
        Atribuídos=("id", "count"),
        Fechados=("status", lambda status: int((status == "Fechado").sum())),
        Resolvidos=("resolvido_em", lambda data: int(data.notna().sum())),
        **{"Tempo médio de resolução (h)": ("tempo_resolucao_horas", "mean")},
    ).sort_values(["Fechados", "Atribuídos"], ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Analistas com demanda", len(produtividade))
    c2.metric("Chamados atribuídos", len(dados))
    c3.metric("Chamados fechados", int((dados["status"] == "Fechado").sum()))
    _exibir_grafico_barras(produtividade, "Chamados fechados por analista", "Analista", "Fechados", "#d97706")
    tabela = produtividade.copy()
    tabela["Tempo médio de resolução (h)"] = tabela["Tempo médio de resolução (h)"].map(lambda valor: f"{valor:.1f}" if pd.notna(valor) else "—")
    st.dataframe(tabela, use_container_width=True, hide_index=True)


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
        _exibir_grafico_barras(motivos, "Cancelamentos por motivo", "Motivo", "Quantidade", "#dc2626")
    with tabela:
        st.dataframe(motivos, use_container_width=True, hide_index=True)


def abrir_perfil_usuario_admin(usuario_id):
    st.session_state.usuario_admin_aberto = usuario_id
    st.session_state.admin_nav = "Perfil do usuário"


def fechar_perfil_usuario_admin():
    st.session_state.usuario_admin_aberto = None
    st.session_state.admin_nav = "Usuários"


def excluir_perfil_usuario_admin(usuario_id, admin_id):
    excluir_usuario(usuario_id, autor_id=admin_id)
    st.session_state.usuario_admin_aberto = None
    st.session_state.admin_nav = "Usuários"
    st.session_state.mensagem_admin = "Usuário excluído."


def painel_perfil_usuario_admin(admin):
    usuario_id = st.session_state.get("usuario_admin_aberto")
    conta = buscar_usuario_por_id(usuario_id) if usuario_id else None
    if not conta:
        st.info("Abra um usuário pela lista para consultar ou editar o perfil.")
        return

    st.markdown(f"#### Perfil de {conta['nome']} {conta.get('sobrenome') or ''}".strip())
    m1, m2, m3 = st.columns(3)
    m1.metric("Perfil", conta["papel"].capitalize())
    m2.metric("Departamento", conta.get("departamento") or "Não informado")
    m3.metric("Último login", conta["ultimo_login_em"].strftime("%d/%m/%Y %H:%M") if conta.get("ultimo_login_em") else "Nunca acessou")

    with st.container(border=True):
        st.caption("Dados de identificação e vínculo organizacional. Campos adicionais são opcionais.")
        with st.form(f"form_editar_usuario_{conta['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                novo_nome = st.text_input("Nome", value=conta["nome"])
                novo_sobrenome = st.text_input("Sobrenome", value=conta.get("sobrenome") or "")
                novo_email = st.text_input("E-mail", value=conta["email"])
                novo_telefone = st.text_input("Telefone", value=conta.get("telefone") or "")
            with col2:
                novo_papel = st.selectbox(
                    "Perfil de acesso", ["usuario", "analista", "admin"],
                    index=["usuario", "analista", "admin"].index(conta["papel"]),
                )
                novo_departamento = st.text_input("Departamento", value=conta.get("departamento") or "")
                novo_cargo = st.text_input("Cargo", value=conta.get("cargo") or "")
                nova_senha = st.text_input("Nova senha (opcional)", type="password")
            salvar = st.form_submit_button("Salvar alterações", type="primary")

        if salvar:
            outro_usuario = buscar_usuario_por_email(novo_email)
            if not novo_nome or not novo_sobrenome or not novo_email:
                st.warning("Nome, sobrenome e e-mail são obrigatórios.")
            elif outro_usuario and outro_usuario["id"] != conta["id"]:
                st.error("Já existe uma conta com esse e-mail.")
            else:
                atualizar_usuario(
                    conta["id"], novo_nome, novo_email, novo_papel,
                    senha_hash=gerar_hash_senha(nova_senha) if nova_senha else None,
                    sobrenome=novo_sobrenome, telefone=novo_telefone,
                    departamento=novo_departamento, cargo=novo_cargo,
                    autor_id=admin["id"],
                )
                st.success("Perfil atualizado.")
                st.rerun()

    acoes, fechar = st.columns(2)
    with acoes:
        if conta["id"] != admin["id"]:
            confirmar_exclusao = st.checkbox("Confirmo a exclusão permanente desta conta.")
            st.button(
                "Excluir usuário", disabled=not confirmar_exclusao,
                on_click=excluir_perfil_usuario_admin,
                args=(conta["id"], admin["id"]),
            )
    with fechar:
        st.button("Voltar para usuários", on_click=fechar_perfil_usuario_admin)


def tela_admin(usuario):
    injetar_css()
    cabecalho("Painel Administrativo", "Acesso restrito — gerenciamento de usuários do sistema")

    usuarios = listar_usuarios()

    total = len(usuarios)
    n_usuarios = sum(1 for u in usuarios if u["papel"] == "usuario")
    n_analistas = sum(1 for u in usuarios if u["papel"] == "analista")
    n_admins = sum(1 for u in usuarios if u["papel"] == "admin")

    opcoes_navegacao = ["Usuários", "Dashboards"]
    if st.session_state.get("usuario_admin_aberto"):
        opcoes_navegacao.append("Perfil do usuário")
    navegacao = st.radio("Navegação administrativa", opcoes_navegacao, horizontal=True, key="admin_nav")

    if navegacao == "Dashboards":
        chamados = listar_chamados(limite=5000)
        relatorio_usuarios(usuarios)
        st.divider()
        relatorio_sla_desempenho(chamados)
        st.divider()
        relatorio_ia(chamados)
        st.divider()
        relatorio_produtividade_equipe(chamados)
        st.divider()
        relatorio_cancelamentos(chamados)

    if navegacao == "Usuários":
        if st.session_state.get("mensagem_admin"):
            st.success(st.session_state.pop("mensagem_admin"))
        with st.expander("Cadastrar usuário", expanded=False):
            with st.form("form_novo_usuario", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nome = st.text_input("Nome")
                    sobrenome = st.text_input("Sobrenome")
                    senha = st.text_input("Senha", type="password")
                    telefone = st.text_input("Telefone (opcional)")
                with col2:
                    email = st.text_input("E-mail")
                    papel = st.selectbox("Perfil", options=["usuario", "analista", "admin"])
                    departamento = st.text_input("Departamento (opcional)")
                    cargo = st.text_input("Cargo (opcional)")
                cadastrar = st.form_submit_button("Cadastrar", type="primary")

            if cadastrar:
                if not nome or not sobrenome or not email or not senha:
                    st.warning("Nome, sobrenome, e-mail e senha são obrigatórios.")
                elif buscar_usuario_por_email(email):
                    st.error("Já existe um usuário cadastrado com esse e-mail.")
                else:
                    criar_usuario(
                        nome, email, gerar_hash_senha(senha), papel,
                        sobrenome=sobrenome, telefone=telefone or None,
                        departamento=departamento or None, cargo=cargo or None,
                        autor_id=usuario["id"],
                    )
                    st.success(f"Usuário {email} cadastrado como '{papel}'.")
                    st.rerun()

        if usuarios:
            filtro_usuario = st.text_input("Buscar por nome, e-mail ou perfil", key="filtro_usuarios").strip().lower()
            usuarios_filtrados = [
                u for u in usuarios
                if not filtro_usuario or filtro_usuario in f"{u['nome']} {u['email']} {u['papel']}".lower()
            ]
            st.caption(f"{len(usuarios_filtrados)} conta(s) encontrada(s).")
            cabecalho_tabela = st.columns([2, 2.4, 1, 1.4, 1])
            for coluna, texto in zip(cabecalho_tabela, ["Nome", "E-mail", "Perfil", "Último login", "Ação"]):
                coluna.markdown(f"**{texto}**")
            for conta in usuarios_filtrados:
                col_nome, col_email, col_papel, col_login, col_acao = st.columns([2, 2.4, 1, 1.4, 1])
                col_nome.write(f"{conta['nome']} {conta.get('sobrenome') or ''}".strip())
                col_email.write(conta["email"])
                col_papel.write(conta["papel"].capitalize())
                ultimo_login = conta.get("ultimo_login")
                col_login.write(ultimo_login.strftime("%d/%m/%Y %H:%M") if ultimo_login else "Nunca acessou")
                col_acao.button(
                    "Abrir perfil", key=f"abrir_usuario_{conta['id']}",
                    on_click=abrir_perfil_usuario_admin, args=(conta["id"],),
                )

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


PAGINAS_POR_PAPEL = {
    "usuario": ("pages/1_Portal_Usuario.py", "Portal do usuário", "🏠"),
    "analista": ("pages/2_Atendimento.py", "Atendimento", "🛠️"),
    "admin": ("pages/3_Administracao.py", "Administração", "🛡️"),
}


def exibir_navegacao(usuario):
    """Monta links de página compatíveis com o perfil autenticado."""
    with st.sidebar:
        st.write(f"Logado como **{usuario['nome']}**")
        st.caption(f"Perfil: {usuario['papel'].capitalize()}")
        st.divider()
        st.page_link("app.py", label="Início", icon="🏠")

        pagina_permitida = PAGINAS_POR_PAPEL.get(usuario["papel"])
        if pagina_permitida:
            pagina, rotulo, icone = pagina_permitida
            st.page_link(pagina, label=rotulo, icon=icone)

        if usuario["papel"] == "admin":
            secao_configurar_autenticador(usuario)
        if st.button("Sair", use_container_width=True):
            sair()


def executar_aplicacao(pagina_solicitada=None):
    """Centraliza autenticação, autorização e a tela de cada página Streamlit."""
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
    if not st.session_state.login_auditoria_registrada:
        registrar_login(usuario["id"])
        st.session_state.login_auditoria_registrada = True

    if pagina_solicitada is None:
        pagina_permitida = PAGINAS_POR_PAPEL.get(usuario["papel"])
        if pagina_permitida:
            st.switch_page(pagina_permitida[0])
        st.error("Perfil desconhecido. Contate o administrador.")
        return

    exibir_navegacao(usuario)
    if pagina_solicitada and pagina_solicitada != usuario["papel"]:
        st.error("Você não tem permissão para acessar esta página.")
        st.page_link("app.py", label="Voltar ao início", icon="🏠")
        return

    if usuario["papel"] == "usuario":
        tela_usuario(usuario)
    elif usuario["papel"] == "analista":
        tela_analista(usuario)
    elif usuario["papel"] == "admin":
        tela_admin(usuario)
    else:
        st.error("Perfil desconhecido. Contate o administrador.")
