import streamlit as st
from datetime import datetime

from ia_engine import classificar_chamado, conversar_coleta
from database import (
    salvar_chamado, criar_tabela, atualizar_tabela, criar_tabela_mensagens,
    listar_chamados, buscar_chamado_por_id, atualizar_status_chamado,
    atribuir_chamado, listar_mensagens_chamado, enviar_mensagem_chamado,
    listar_usuarios, criar_usuario, buscar_usuario_por_email, atualizar_senha,
    salvar_totp_secret, salvar_codigo_verificacao, verificar_codigo,
    buscar_usuario_por_id, atualizar_usuario, excluir_usuario,
)
from auth import (
    autenticar, gerar_hash_senha, gerar_codigo_numerico, gerar_totp_secret,
    gerar_qrcode_totp, verificar_totp,
)
from email_utils import enviar_email

st.set_page_config(
    page_title="Sistema Inteligente de Chamados",
    page_icon="🎫",
    layout="wide",
)

criar_tabela()
atualizar_tabela()
criar_tabela_mensagens()


STATUS_OPCOES = ["Novo", "Em Andamento", "Em Espera", "Resolvido", "Fechado"]

CORES_STATUS = {
    "Novo": "#2563eb",          
    "Aberto": "#2563eb",        
    "Em Andamento": "#d97706",  
    "Em Espera": "#7c3aed",   
    "Resolvido": "#16a34a",    
    "Fechado": "#475569",      
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
            border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.2rem;
            margin-bottom: 0.8rem; background: #ffffff;
        }
        .card:hover { border-color: #cbd5e1; }
        .card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; }
        .card-meta { font-size: 0.78rem; color: #64748b; }

        .ticket-selected {
            border: 1px solid #2563eb; box-shadow: 0 0 0 1px #2563eb inset;
        }

        .metric-row { display: flex; gap: 0.8rem; margin-bottom: 1rem; }

        .sla-pill {
            display: inline-block; background: #f1f5f9; border-radius: 8px;
            padding: 2px 8px; font-size: 0.75rem; color: #334155; margin-right: 6px;
        }
    </style>
    """, unsafe_allow_html=True)


def badge(texto, cor):
    return f'<span class="badge" style="background:{cor};">{texto}</span>'


def badge_status(status):
    return badge(status or "—", CORES_STATUS.get(status, "#64748b"))


def badge_urgencia(urgencia):
    return badge(urgencia or "—", CORES_URGENCIA.get(urgencia, "#64748b"))


def cabecalho(titulo, subtitulo, icone="🎫"):
    st.markdown(f"""
    <div class="app-header">
        <div>
            <h1>{icone} {titulo}</h1>
            <div class="sub">{subtitulo}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


for chave, valor_inicial in {
    "usuario_logado": None,
    "usuario_pendente_2fa": None,
    "tela_atual": "login",
    "email_recuperacao": None,
    "chamado_selecionado_analista": None,
    "chamado_aberto_usuario": None,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor_inicial


def tela_login():
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 🔒 Sistema Inteligente de Chamados")
        st.caption("Central de Serviços de TI — faça login para continuar")

        with st.container(border=True):
            with st.form("form_login"):
                email = st.text_input("Email")
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

            if entrar:
                usuario = autenticar(email, senha)
                if usuario is None:
                    st.error("Email ou senha inválidos.")
                elif usuario["papel"] == "admin":
                    st.session_state.usuario_pendente_2fa = usuario
                    if not usuario.get("totp_secret"):
                        codigo = gerar_codigo_numerico()
                        salvar_codigo_verificacao(usuario["id"], codigo, tipo="login_2fa")
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
                    st.rerun()

            if st.button("Esqueci minha senha", use_container_width=True):
                st.session_state.tela_atual = "esqueci_senha_pedir"
                st.rerun()


def tela_2fa():
    injetar_css()
    usuario = st.session_state.usuario_pendente_2fa
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("### 🔑 Verificação em duas etapas")

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
                    st.rerun()
                else:
                    st.error("Código inválido ou expirado.")

            if st.button("Cancelar e voltar", use_container_width=True):
                st.session_state.usuario_pendente_2fa = None
                st.rerun()


def tela_esqueci_senha_pedir():
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])
    with col_meio:
        st.markdown("### 🔓 Recuperar senha")
        with st.container(border=True):
            with st.form("form_pedir_codigo"):
                email = st.text_input("Digite seu email cadastrado")
                enviar = st.form_submit_button("Enviar código de recuperação", use_container_width=True, type="primary")

            if enviar:
                usuario = buscar_usuario_por_email(email)
                if usuario is None:
                    st.error("Não encontramos nenhuma conta com esse e-mail.")
                else:
                    codigo = gerar_codigo_numerico()
                    salvar_codigo_verificacao(usuario["id"], codigo, tipo="reset_senha")
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
        st.markdown("### 🔓 Recuperar senha")
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
                    st.error("Código inválido ou expirado.")

            if st.button("Voltar ao login", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()


def sair():
    st.session_state.usuario_logado = None
    st.rerun()


def painel_conversa_chamado(chamado, usuario_atual, papel_atual, key_prefix):
    """Mostra o histórico de mensagens de um chamado e permite responder.
    Usado tanto pelo usuário quanto pelo analista dentro do chamado."""
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

    if chamado["status"] == "Fechado":
        st.caption("🔒 Chamado fechado — não é possível enviar novas mensagens.")
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


def tela_usuario(usuario):
    injetar_css()
    cabecalho("Central de Chamados", f"Bem-vindo(a), {usuario['nome']}", "🎫")

    aba_chat, aba_chamados = st.tabs(["💬 Abrir novo chamado", "📋 Meus chamados"])

    with aba_chat:
        _aba_abrir_chamado(usuario)

    with aba_chamados:
        _aba_meus_chamados(usuario)


def _aba_abrir_chamado(usuario):
    st.caption("Converse com a IA descrevendo o problema — ela vai fazer algumas perguntas e, ao final, abrir o chamado automaticamente.")

    if "chat_mensagens" not in st.session_state:
        st.session_state.chat_mensagens = [
            {"role": "assistant", "content": "Olá! Descreva o problema que você está enfrentando."}
        ]
    if "chat_turnos_usuario" not in st.session_state:
        st.session_state.chat_turnos_usuario = 0
    if "chat_resultado_final" not in st.session_state:
        st.session_state.chat_resultado_final = None

    MAX_TURNOS = 4

    with st.container(border=True):
        for msg in st.session_state.chat_mensagens:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        if st.session_state.chat_resultado_final is None:
            entrada = st.chat_input("Digite sua resposta...")
            if entrada:
                st.session_state.chat_mensagens.append({"role": "user", "content": entrada})
                st.session_state.chat_turnos_usuario += 1

                with st.spinner("A IA está processando..."):
                    forcar = st.session_state.chat_turnos_usuario >= MAX_TURNOS
                    resultado = conversar_coleta(st.session_state.chat_mensagens, forcar_finalizar=forcar)

                if resultado["acao"] == "perguntar":
                    st.session_state.chat_mensagens.append({"role": "assistant", "content": resultado["mensagem"]})
                    st.rerun()
                else:
                    st.session_state.chat_mensagens.append({
                        "role": "assistant",
                        "content": f"Entendi! Vou abrir o chamado: **{resultado['titulo']}**"
                    })
                    with st.spinner("Classificando e registrando o chamado..."):
                        classificacao = classificar_chamado(resultado["titulo"], resultado["descricao"])
                        chamado_id = salvar_chamado(
                            titulo=resultado["titulo"],
                            descricao=resultado["descricao"],
                            categoria=classificacao.get("categoria"),
                            urgencia=classificacao.get("urgencia"),
                            sla_resposta=classificacao.get("tempo_sla_resposta"),
                            sla_resolucao=classificacao.get("tempo_sla_resolucao"),
                            equipe_destino=classificacao.get("equipe_destino"),
                            titulo_resumido=classificacao.get("titulo_resumido"),
                            descricao_padronizada=classificacao.get("descricao_padronizada"),
                            confiabilidade=classificacao.get("confiabilidade"),
                            usuario_id=usuario["id"],
                        )
                    st.session_state.chat_resultado_final = {"id": chamado_id, **classificacao}
                    st.rerun()

        else:
            resultado = st.session_state.chat_resultado_final
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

            if st.button("Abrir novo chamado", type="primary"):
                st.session_state.chat_mensagens = [
                    {"role": "assistant", "content": "Olá! Descreva o problema que você está enfrentando."}
                ]
                st.session_state.chat_turnos_usuario = 0
                st.session_state.chat_resultado_final = None
                st.rerun()


def _aba_meus_chamados(usuario):
    chamados = listar_chamados(limite=50, usuario_id=usuario["id"])

    if not chamados:
        st.info("Você ainda não abriu nenhum chamado.")
        return

    st.caption(f"{len(chamados)} chamado(s) — clique em um para ver detalhes e conversar com o analista.")

    lista_col, detalhe_col = st.columns([1, 1.6])

    with lista_col:
        for c in chamados:
            selecionado = st.session_state.chamado_aberto_usuario == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c.get('titulo_resumido') or c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
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

        with st.container(border=True):
            st.markdown(f"#### #{chamado['id']} — {chamado.get('titulo_resumido') or chamado['titulo']}")
            st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            st.write(chamado.get("descricao_padronizada") or chamado["descricao"])

            st.markdown(
                f'<span class="sla-pill">⏱ Resposta: {chamado.get("sla_resposta") or "—"}</span>'
                f'<span class="sla-pill">✅ Resolução: {chamado.get("sla_resolucao") or "—"}</span>'
                f'<span class="sla-pill">👥 Equipe: {chamado.get("equipe_destino") or "—"}</span>',
                unsafe_allow_html=True,
            )
            st.caption(f"Analista responsável: {chamado.get('nome_analista') or 'Aguardando atribuição'}")

        st.markdown("##### 💬 Conversa com o analista")
        painel_conversa_chamado(chamado, usuario, "usuario", key_prefix="usr")


def tela_analista(usuario):
    injetar_css()
    cabecalho("Central de Serviços — Analista", f"{usuario['nome']} · Gestão de Incidentes (ITIL 4)", "🧑‍💻")

    chamados = listar_chamados(limite=100)
    if not chamados:
        st.info("Nenhum chamado registrado ainda.")
        return

    total = len(chamados)
    novos = sum(1 for c in chamados if c["status"] == "Novo")
    em_andamento = sum(1 for c in chamados if c["status"] == "Em Andamento")
    meus = sum(1 for c in chamados if c.get("analista_id") == usuario["id"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de chamados", total)
    m2.metric("Novos", novos)
    m3.metric("Em andamento", em_andamento)
    m4.metric("Atribuídos a mim", meus)

    st.divider()

    filtro_col1, filtro_col2, filtro_col3 = st.columns([1.2, 1.2, 1])
    with filtro_col1:
        filtro_status = st.multiselect("Status", options=STATUS_OPCOES, default=[])
    with filtro_col2:
        filtro_urgencia = st.multiselect("Urgência", options=["Critica", "Alta", "Media", "Baixa"], default=[])
    with filtro_col3:
        st.write("")
        st.write("")
        somente_meus = st.checkbox("Somente meus chamados")

    chamados_filtrados = chamados
    if filtro_status:
        chamados_filtrados = [c for c in chamados_filtrados if c["status"] in filtro_status]
    if filtro_urgencia:
        chamados_filtrados = [c for c in chamados_filtrados if c["urgencia"] in filtro_urgencia]
    if somente_meus:
        chamados_filtrados = [c for c in chamados_filtrados if c.get("analista_id") == usuario["id"]]

    fila_col, detalhe_col = st.columns([1, 1.6])

    with fila_col:
        st.markdown("##### 📥 Fila de chamados")
        if not chamados_filtrados:
            st.caption("Nenhum chamado com os filtros selecionados.")
        for c in chamados_filtrados:
            selecionado = st.session_state.chamado_selecionado_analista == c["id"]
            classe_extra = " ticket-selected" if selecionado else ""
            responsavel = c.get("nome_analista") or "🔓 Sem atribuição"
            st.markdown(f"""
            <div class="card{classe_extra}">
                <div class="card-title">#{c['id']} — {c.get('titulo_resumido') or c['titulo']}</div>
                <div class="card-meta">{badge_status(c['status'])} {badge_urgencia(c['urgencia'])}</div>
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
                st.markdown(f"#### #{chamado['id']} — {chamado.get('titulo_resumido') or chamado['titulo']}")
                st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            with topo_dir:
                ja_atribuido_a_mim = chamado.get("analista_id") == usuario["id"]
                if not ja_atribuido_a_mim:
                    if st.button("🖐️ Atender chamado", type="primary", use_container_width=True):
                        atribuir_chamado(chamado["id"], usuario["id"])
                        st.rerun()
                else:
                    st.success("Você está atendendo")

            st.write(chamado.get("descricao_padronizada") or chamado["descricao"])

            st.markdown(
                f'<span class="sla-pill">📂 {chamado.get("categoria") or "—"}</span>'
                f'<span class="sla-pill">⏱ Resposta: {chamado.get("sla_resposta") or "—"}</span>'
                f'<span class="sla-pill">✅ Resolução: {chamado.get("sla_resolucao") or "—"}</span>'
                f'<span class="sla-pill">👥 Equipe: {chamado.get("equipe_destino") or "—"}</span>'
                f'<span class="sla-pill">🤖 Confiabilidade IA: {chamado.get("confiabilidade") or "—"}</span>',
                unsafe_allow_html=True,
            )
            st.caption(f"Solicitante: {chamado.get('nome_usuario') or '—'} · Aberto em {chamado.get('criado_em')}")

            st.divider()
            status_col, botao_col = st.columns([2, 1])
            with status_col:
                indice_atual = STATUS_OPCOES.index(chamado["status"]) if chamado["status"] in STATUS_OPCOES else 0
                novo_status = st.selectbox("Atualizar status (ciclo de vida ITIL)", options=STATUS_OPCOES, index=indice_atual, key=f"status_{chamado['id']}")
            with botao_col:
                st.write("")
                if st.button("Salvar status", use_container_width=True):
                    atualizar_status_chamado(chamado["id"], novo_status)
                    st.success(f"Status atualizado para '{novo_status}'.")
                    st.rerun()

        st.markdown("##### 💬 Conversa com o solicitante")
        painel_conversa_chamado(chamado, usuario, "analista", key_prefix="ana")


def tela_admin(usuario):
    injetar_css()
    cabecalho("Painel Administrativo", "Acesso restrito — gerenciamento de usuários do sistema", "🛠️")

    usuarios = listar_usuarios()

    total = len(usuarios)
    n_usuarios = sum(1 for u in usuarios if u["papel"] == "usuario")
    n_analistas = sum(1 for u in usuarios if u["papel"] == "analista")
    n_admins = sum(1 for u in usuarios if u["papel"] == "admin")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de contas", total)
    m2.metric("Usuários", n_usuarios)
    m3.metric("Analistas", n_analistas)
    m4.metric("Admins", n_admins)

    st.divider()

    aba_listar, aba_cadastrar, aba_editar, aba_excluir = st.tabs(
        ["👥 Usuários cadastrados", "➕ Cadastrar", "✏️ Editar", "🗑️ Excluir"]
    )

    with aba_listar:
        if usuarios:
            st.dataframe(usuarios, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum usuário cadastrado.")

    with aba_cadastrar:
        with st.container(border=True):
            with st.form("form_novo_usuario", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nome = st.text_input("Nome")
                    senha = st.text_input("Senha", type="password")
                with col2:
                    email = st.text_input("Email")
                    papel = st.selectbox("Perfil", options=["usuario", "analista", "admin"])
                cadastrar = st.form_submit_button("Cadastrar", type="primary")

            if cadastrar:
                if not nome or not email or not senha:
                    st.warning("Preencha todos os campos.")
                elif buscar_usuario_por_email(email):
                    st.error("Já existe um usuário cadastrado com esse e-mail.")
                else:
                    hash_senha = gerar_hash_senha(senha)
                    criar_usuario(nome, email, hash_senha, papel)
                    st.success(f"Usuário {email} cadastrado como '{papel}'.")
                    st.rerun()

    with aba_editar:
        if not usuarios:
            st.info("Nenhum usuário para editar.")
        else:
            mapa_usuarios = {u["id"]: u for u in usuarios}
            id_para_editar = st.selectbox(
                "Selecione o usuário",
                options=list(mapa_usuarios.keys()),
                format_func=lambda uid: f"#{uid} — {mapa_usuarios[uid]['nome']} ({mapa_usuarios[uid]['email']})",
                key="select_editar_usuario",
            )
            usuario_selecionado = buscar_usuario_por_id(id_para_editar)

            with st.container(border=True):
                with st.form("form_editar_usuario"):
                    col1, col2 = st.columns(2)
                    with col1:
                        novo_nome = st.text_input("Nome", value=usuario_selecionado["nome"])
                        novo_papel = st.selectbox(
                            "Perfil",
                            options=["usuario", "analista", "admin"],
                            index=["usuario", "analista", "admin"].index(usuario_selecionado["papel"]),
                        )
                    with col2:
                        novo_email = st.text_input("Email", value=usuario_selecionado["email"])
                        nova_senha = st.text_input(
                            "Nova senha (deixe em branco para manter a atual)", type="password"
                        )
                    salvar = st.form_submit_button("Salvar alterações", type="primary")

                if salvar:
                    if not novo_nome or not novo_email:
                        st.warning("Nome e email não podem ficar em branco.")
                    else:
                        outro_usuario_com_email = buscar_usuario_por_email(novo_email)
                        if outro_usuario_com_email and outro_usuario_com_email["id"] != id_para_editar:
                            st.error("Já existe outro usuário cadastrado com esse e-mail.")
                        else:
                            hash_nova_senha = gerar_hash_senha(nova_senha) if nova_senha else None
                            atualizar_usuario(id_para_editar, novo_nome, novo_email, novo_papel, hash_nova_senha)
                            st.success(f"Usuário #{id_para_editar} atualizado com sucesso.")
                            st.rerun()

    with aba_excluir:
        if not usuarios:
            st.info("Nenhum usuário para excluir.")
        else:
            mapa_usuarios = {u["id"]: u for u in usuarios}
            id_para_excluir = st.selectbox(
                "Selecione o usuário",
                options=list(mapa_usuarios.keys()),
                format_func=lambda uid: f"#{uid} — {mapa_usuarios[uid]['nome']} ({mapa_usuarios[uid]['email']})",
                key="select_excluir_usuario",
            )

            if id_para_excluir == usuario["id"]:
                st.warning("Você não pode excluir a própria conta enquanto estiver logado nela.")
            else:
                usuario_alvo = mapa_usuarios[id_para_excluir]
                with st.container(border=True):
                    confirmar_exclusao = st.checkbox(
                        f"Confirmo que quero excluir permanentemente o usuário "
                        f"'{usuario_alvo['nome']}' ({usuario_alvo['email']})."
                    )
                    if st.button("Excluir usuário", type="primary", disabled=not confirmar_exclusao):
                        excluir_usuario(id_para_excluir)
                        st.success(f"Usuário #{id_para_excluir} excluído com sucesso.")
                        st.rerun()


def secao_configurar_autenticador(usuario):
    with st.sidebar.expander("🔐 Autenticação em duas etapas"):
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
                        salvar_totp_secret(usuario["id"], st.session_state.totp_secret_temp)
                        st.session_state.totp_secret_temp = None
                        st.success("Autenticador ativado!")
                        st.session_state.usuario_logado["totp_secret"] = "ativo"
                        st.rerun()
                    else:
                        st.error("Código incorreto. Tente novamente.")


if st.session_state.usuario_pendente_2fa is not None:
    tela_2fa()
elif st.session_state.usuario_logado is None:
    if st.session_state.tela_atual == "esqueci_senha_pedir":
        tela_esqueci_senha_pedir()
    elif st.session_state.tela_atual == "esqueci_senha_confirmar":
        tela_esqueci_senha_confirmar()
    else:
        tela_login()
else:
    usuario = st.session_state.usuario_logado

    st.sidebar.write(f"Logado como **{usuario['nome']}**")
    st.sidebar.write(f"Perfil: `{usuario['papel']}`")
    if usuario["papel"] == "admin":
        secao_configurar_autenticador(usuario)
    if st.sidebar.button("Sair"):
        sair()

    if usuario["papel"] == "usuario":
        tela_usuario(usuario)
    elif usuario["papel"] == "analista":
        tela_analista(usuario)
    elif usuario["papel"] == "admin":
        tela_admin(usuario)
    else:
        st.error("Perfil desconhecido. Contate o administrador.")
