import re
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import mysql.connector
from datetime import datetime, time, timedelta
from html import escape
from pathlib import Path

from ia_engine import (
    classificar_chamado, conversar_coleta, identificar_intencao, responder_duvida, avaliar_classificador,
)
from rag import listar_artigos
import sla
from database import (
    salvar_chamado, criar_tabela_departamentos, criar_tabelas_rbac, criar_tabela_usuarios,
    migrar_tabela_usuarios, migrar_usuarios_rbac,
    migrar_departamentos_usuarios, listar_departamentos, criar_departamento, atualizar_departamento,
    listar_perfis, listar_perfis_para_atribuicao, listar_permissoes, permissoes_do_perfil,
    criar_perfil, atualizar_perfil, excluir_perfil,
    usuario_tem_permissao, usuario_eh_administrador,
    criar_tabela_chamados, migrar_tabela_chamados, criar_tabela_historico_chamados, criar_tabela_mensagens,
    criar_tabela_base_casos_ia, migrar_tabela_base_casos_ia,
    criar_tabela_codigos, migrar_tabela_codigos, listar_chamados, buscar_chamado_por_id,
    atualizar_status_chamado, atribuir_chamado, listar_mensagens_chamado,
    registrar_resolucao_chamado,
    transferir_chamado, escalar_chamado, listar_analistas_para_transferencia,
    listar_historico_chamado,
    enviar_mensagem_chamado, listar_usuarios, criar_usuario,
    buscar_usuario_por_email, redefinir_senha_com_codigo, salvar_totp_secret,
    salvar_codigo_verificacao, verificar_codigo, buscar_usuario_por_id,
    atualizar_usuario, excluir_usuario,
    buscar_titular_por_identificador, buscar_usuario_por_cpf, normalizar_cpf,
    exportar_dados_titular, anonimizar_titular,
    criar_tabela_anexos, salvar_anexo_chamado, listar_anexos_chamado, baixar_anexo_chamado,
    criar_tabela_pesquisas_satisfacao, buscar_pesquisa_satisfacao, listar_pesquisas_satisfacao,
    salvar_pesquisa_satisfacao,
    criar_tabela_atendimentos_ia, migrar_tabela_atendimentos_ia, salvar_atendimento_ia,
    registrar_resultado_atendimento_ia, registrar_feedback_atendimento_ia, listar_atendimentos_ia,
    criar_tabela_casos_avaliacao_ia, criar_tabela_execucoes_avaliacao_ia, relatorio_qualidade_ia,
    cadastrar_caso_avaliacao_ia, listar_casos_avaliacao_ia, registrar_execucao_avaliacao_ia,
    listar_casos_base_ia,
    criar_tabela_auditoria, registrar_auditoria, registrar_login,
    criar_tabelas_privacidade, usuario_aceitou_politica, registrar_aceite_privacidade,
    VERSAO_POLITICA_PRIVACIDADE,
    cancelar_chamado_sem_atribuicao,
    confirmar_resolucao_usuario,
    reabrir_chamado_usuario,
    criar_tabela_configuracao_sla, obter_configuracao_sla, atualizar_configuracao_sla,
    fechar_chamados_resolvidos_automaticamente,
    listar_auditoria,
    para_horario_local,
)
from auth import (
    autenticar, gerar_hash_senha, gerar_codigo_numerico, gerar_totp_secret,
    gerar_qrcode_totp, verificar_totp,
)
from email_utils import enviar_email
from migrations import schema_pronto


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
    "Novo": "#1f5f78",
    "Aberto": "#1f5f78",
    "Em Andamento": "#8a5a00",
    "Em Espera": "#5b3f88",
    "Resolvido": "#176b4d",
    "Fechado": "#3e5954",
    "Cancelado": "#50535a",
}

CORES_URGENCIA = {
    "Critica": "#dc2626",
    "Alta": "#c2410c",
    "Media": "#a16207",
    "Baixa": "#15803d",
}

ICONE_URGENCIA = {"Critica": "🚨", "Alta": "🔴", "Media": "🟠", "Baixa": "🟢"}
ICONE_SLA = {
    "Dentro do prazo": "⏱️", "Em risco": "⚠️", "Violado": "🚨",
    "Cumprido": "✅", "Pausado": "⏸️", "Não aplicável": "—",
}


def injetar_css():
    """Mantido como ponto de extensão, sem substituir o estilo nativo."""
    return

    st.markdown("""
    <style>
        :root {
            --brand: #5e9188;
            --brand-dark: #232226;
            --surface: #ffffff;
            --muted: #3e5954;
            --agenda-active: #5e9188;
            --agenda-active-text: #ffffff;
            --agenda-closed: #3e5954;
            --agenda-closed-text: #ffffff;
            --input-bg: #ffffff;
            --input-border: #5e9188;
            --input-focus: #5e9188;
            --input-text: #232226;
            --success: #176b4d;
            --warning: #8a5a00;
            --danger: #a82a22;
            --info: #1f5f78;
        }

        .stApp { background: #253342; }
        .block-container { max-width: 1440px; padding-top: 2.25rem; padding-bottom: 3rem; }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #232226 0%, #253342 100%);
            border-right: 1px solid #3e5954;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0.7rem;
        }
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p { color: #ffffff; }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {
            color: #ffffff;
            border-radius: 9px;
            padding: 0.48rem 0.65rem;
            transition: background 0.15s ease, color 0.15s ease;
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
            background: #3e5954;
            color: #ffffff;
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
            background: #5e9188;
            color: #232226;
            font-weight: 650;
        }
        [data-testid="stSidebar"] [data-baseweb="radio"] {
            padding: 0.28rem 0.4rem;
            border-radius: 8px;
        }
        [data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) {
            background: #5e9188;
        }
        [data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) label {
            color: #232226 !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] hr { border-color: #3e5954; }

        /* A barra lateral não acompanha o tema da área principal: ela mantém
           a aparência escura em toda a navegação, inclusive nos expansores. */
        [data-testid="stSidebar"] [data-testid="stExpander"],
        [data-testid="stSidebar"] [data-testid="stExpander"] details,
        [data-testid="stSidebar"] [data-testid="stExpander"] details > summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] details > summary > div {
            background: #253342 !important;
            border-color: #3e5954 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
        [data-testid="stSidebar"] [data-testid="stExpander"] p,
        [data-testid="stSidebar"] [data-testid="stExpander"] label,
        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stCaptionContainer"] {
            color: #ffffff !important;
        }

        .sidebar-brand {
            padding: 0.75rem 0.65rem 0.9rem;
            margin-bottom: 0.4rem;
            border-bottom: 1px solid #3e5954;
        }
        .sidebar-brand__eyebrow {
            color: #5e9188; font-size: 0.68rem; font-weight: 700;
            letter-spacing: 0.12em; text-transform: uppercase;
        }
        .sidebar-brand__name {
            color: #ffffff; font-size: 1.08rem; font-weight: 700; margin-top: 0.15rem;
        }
        .sidebar-section {
            color: #5e9188; font-size: 0.68rem; font-weight: 700;
            letter-spacing: 0.11em; text-transform: uppercase; margin: 1.1rem 0 0.35rem;
        }

        .app-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 1.1rem 1.4rem; border-radius: 16px; margin-bottom: 1.6rem;
            background: linear-gradient(135deg, #232226 0%, #3e5954 100%);
            box-shadow: 0 12px 28px rgba(35, 34, 38, 0.32);
            color: #ffffff;
        }
        .app-header h1 { font-size: 1.35rem; margin: 0; color: #ffffff; }
        .app-header .sub { font-size: 0.82rem; color: #5e9188; margin-top: 2px; }

        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 0.72rem; font-weight: 700; color: white; letter-spacing: .2px;
            box-shadow: 0 1px 2px rgba(35, 34, 38, 0.22);
        }

        .card {
            border: 1px solid #5e9188; border-left: 6px solid #5e9188; border-radius: 12px;
            padding: 1rem 1.2rem; margin-bottom: 0.8rem; background: #ffffff; color: #232226;
            box-shadow: 0 5px 14px rgba(35, 34, 38, 0.26);
        }
        .card:hover { border-color: #232226; transform: translateY(-2px); }
        .card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; color: #232226; }
        .card-meta { font-size: 0.78rem; color: #3e5954; }

        .card-sla-violado { border-left: 4px solid #dc2626; }
        .card-sla-risco { border-left: 4px solid #d97706; }
        .card-sla-pausado { border-left: 4px solid #7c3aed; }

        .ticket-selected {
            border: 1px solid #5e9188; box-shadow: 0 0 0 1px #5e9188 inset;
        }

        .metric-row { display: flex; gap: 0.8rem; margin-bottom: 1rem; }

        .sla-pill {
            display: inline-block; background: #5e9188; border-radius: 8px;
            padding: 2px 8px; font-size: 0.75rem; color: #232226; font-weight: 650; margin-right: 6px;
        }

        .artigo-card {
            border: 1px solid #5e9188; border-radius: 12px; padding: 1rem 1.2rem;
            margin-bottom: 0.8rem; background: #ffffff;
        }
        .artigo-titulo { font-weight: 700; font-size: 1.02rem; color: #232226; margin-bottom: 4px; }
        .artigo-resumo { font-size: 0.85rem; color: #3e5954; }
        .artigo-tag {
            display: inline-block; background: #5e9188; color: #232226; font-weight: 650;
            border-radius: 999px; padding: 2px 10px; font-size: 0.72rem;
            margin: 6px 6px 0 0;
        }
        .artigo-secao-titulo {
            font-weight: 600; font-size: 0.86rem; color: #232226;
            margin: 0.9rem 0 0.3rem 0; display: flex; align-items: center; gap: 6px;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stTimeInput"] input {
            background: var(--input-bg) !important;
            color: var(--input-text) !important;
            border: 1.5px solid var(--input-border) !important;
            border-radius: 8px !important;
        }
        [data-baseweb="select"] > div {
            background: var(--input-bg) !important;
            border: 1.5px solid var(--input-border) !important;
            border-radius: 8px !important;
        }
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stNumberInput"] input:focus,
        [data-testid="stDateInput"] input:focus,
        [data-testid="stTimeInput"] input:focus,
        [data-baseweb="select"] > div:focus-within {
            border-color: var(--input-focus) !important;
            box-shadow: 0 0 0 3px rgba(94, 145, 136, 0.35) !important;
        }
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder { color: #3e5954; opacity: 1; }
        button:focus-visible, input:focus-visible, textarea:focus-visible, [role="button"]:focus-visible {
            outline: 3px solid #5e9188 !important; outline-offset: 3px !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 0.4rem; }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            height: 2.55rem; border-radius: 8px 8px 0 0; padding: 0 1rem;
        }
        [data-testid="stTabs"] [aria-selected="true"] { font-weight: 700; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border-color: #5e9188;
        }
        [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"] {
            background: #3e5954;
            border-radius: 8px;
        }
        [data-testid="stBaseButton-primary"] {
            background: #3e5954 !important;
            border: 1px solid #3e5954 !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        [data-testid="stBaseButton-primary"]:hover {
            background: #253342 !important;
            border-color: #253342 !important;
            color: #ffffff !important;
        }
        [data-testid="stBaseButton-secondary"] {
            background: #ffffff !important;
            border: 1px solid #5e9188 !important;
            color: #232226 !important;
            font-weight: 600 !important;
        }
        [data-testid="stBaseButton-secondary"]:hover {
            background: #edf4f2 !important;
            border-color: #3e5954 !important;
        }
        [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {
            min-height: 2.5rem;
            border-radius: 8px !important;
            transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
        }
        [data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-secondary"]:active {
            transform: translateY(1px);
        }
        [data-testid="stBaseButton-primary"] *,
        [data-testid="stBaseButton-secondary"] * {
            color: inherit !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.35rem;
            border-radius: 12px;
        }
        [data-testid="stVerticalBlockBorderWrapper"] label,
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stVerticalBlockBorderWrapper"] h1,
        [data-testid="stVerticalBlockBorderWrapper"] h2,
        [data-testid="stVerticalBlockBorderWrapper"] h3,
        [data-testid="stVerticalBlockBorderWrapper"] h4,
        [data-testid="stVerticalBlockBorderWrapper"] h5,
        [data-testid="stVerticalBlockBorderWrapper"] h6 { color: #232226 !important; }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            border-bottom: 1px solid #5e9188;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            color: #ffffff;
            font-weight: 600;
        }
        [data-testid="stTabs"] [aria-selected="true"] {
            color: #ffffff !important;
            border-bottom: 3px solid #5e9188 !important;
        }
        [data-testid="stAlert"] {
            border-radius: 8px;
            border-left-width: 4px;
            font-size: 0.92rem;
        }
        [data-testid="stMetric"] [data-testid="stMetricLabel"],
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-weight: 650;
        }
        @media (max-width: 700px) {
            .block-container { padding: 1rem 0.75rem; }
            .app-header { padding: 0.75rem 0.9rem; }
            .app-header h1 { font-size: 1.08rem; }
            .card { padding: 0.8rem; }
        }
    </style>
    """, unsafe_allow_html=True)

    # Tema único da aplicação por enquanto: escuro.
    if True:
        st.markdown("""
        <style>
            :root { --agenda-active: #176b4d; --agenda-active-text: #ffffff; --agenda-closed: #3e5954; --agenda-closed-text: #ffffff; --input-bg: #232226; --input-border: #5e9188; --input-focus: #5e9188; --input-text: #ffffff; }
            .stApp { background: #232226; color: #ffffff; }
            /* O cabeçalho fixo do Streamlit abriga controles como "Deploy" e não
               herda o fundo da aplicação. */
            [data-testid="stHeader"], [data-testid="stToolbar"] {
                background: #232226 !important;
            }
            [data-testid="stMain"], [data-testid="stMain"] p, [data-testid="stMain"] label,
            [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3,
            [data-testid="stMain"] h4, [data-testid="stMain"] h5, [data-testid="stMain"] h6 { color: #ffffff; }
            [data-testid="stMain"] .stCaption, [data-testid="stMain"] [data-testid="stCaptionContainer"] { color: #d7e4e1 !important; }
            .app-header h1 { color: #ffffff !important; }
            .app-header .sub { color: #b9d3cd !important; }
            .card, .artigo-card, [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stMetric"] {
                background: #253342; border-color: #3e5954; color: #ffffff;
            }
            .card-title, .artigo-titulo, .artigo-secao-titulo { color: #ffffff; }
            .card-meta, .artigo-resumo { color: #d7e4e1; }
            .sla-pill, .artigo-tag { background: #3e5954; color: #ffffff; }
            [data-testid="stMetric"] { border-left: 4px solid #5e9188; padding: 0.75rem; border-radius: 10px; }
            [data-testid="stExpander"], [data-testid="stExpander"] details,
            [data-testid="stExpander"] details > summary,
            [data-testid="stExpander"] details > summary > div,
            [data-testid="stForm"] {
                background: #253342 !important;
                border-color: #3e5954 !important;
            }
            [data-testid="stExpander"] details > summary {
                color: #ffffff !important;
            }
            [data-testid="stForm"] {
                padding: 1rem;
                border-radius: 10px;
            }
            [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
            [data-testid="stSelectbox"] [data-baseweb="select"],
            [data-testid="stSelectbox"] [data-baseweb="select"] > div,
            [data-testid="stSelectbox"] [data-baseweb="select"] > div > div,
            [data-testid="stSelectbox"] [role="combobox"],
            [data-baseweb="input"] > div {
                background: #253342 !important;
                color: #ffffff !important;
                border-color: #5e9188 !important;
            }
            [data-testid="stSelectbox"] [data-baseweb="select"] input {
                background: #253342 !important;
                color: #ffffff !important;
                -webkit-text-fill-color: #ffffff !important;
            }
            [data-baseweb="select"] *, [data-baseweb="input"] * { color: #ffffff !important; }
            /* Evita que o botão de revelar senha e a seta dos selects mantenham
               o fundo claro padrão do BaseWeb. */
            [data-testid="stTextInput"] [data-baseweb="input"] button,
            [data-testid="stSelectbox"] [data-baseweb="select"] button {
                background: transparent !important;
                border-color: transparent !important;
                color: #ffffff !important;
            }
            [data-testid="stTextInput"] [data-baseweb="input"] svg,
            [data-testid="stSelectbox"] [data-baseweb="select"] svg {
                fill: #ffffff !important;
                color: #ffffff !important;
            }
            [data-testid="stVerticalBlockBorderWrapper"] label,
            [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
            [data-testid="stVerticalBlockBorderWrapper"] h1,
            [data-testid="stVerticalBlockBorderWrapper"] h2,
            [data-testid="stVerticalBlockBorderWrapper"] h3,
            [data-testid="stVerticalBlockBorderWrapper"] h4,
            [data-testid="stVerticalBlockBorderWrapper"] h5,
            [data-testid="stVerticalBlockBorderWrapper"] h6 { color: #ffffff !important; }
            [data-testid="stDataFrame"] {
                --gdg-bg-cell: #253342 !important;
                --gdg-bg-cell-medium: #2d3d4d !important;
                --gdg-bg-header: #3e5954 !important;
                --gdg-bg-header-has-focus: #486961 !important;
                --gdg-bg-header-hovered: #486961 !important;
                --gdg-bg-bubble: #2d3d4d !important;
                --gdg-bg-bubble-selected: #486961 !important;
                --gdg-text-dark: #ffffff !important;
                --gdg-text-medium: #d7e4e1 !important;
                --gdg-text-light: #b9d3cd !important;
                --gdg-text-header: #ffffff !important;
                --gdg-border-color: #3e5954 !important;
                --gdg-horizontal-border-color: #3e5954 !important;
                --gdg-link-color: #9fd0c6 !important;
                background: #253342 !important;
                border: 1px solid #3e5954;
                border-radius: 10px;
                overflow: hidden;
            }
            [data-testid="stDataFrame"] .dvn-scroller { background: #253342 !important; }
            [data-testid="stDataFrame"], [data-testid="stDataFrame"] * { color: #ffffff; }
            [data-testid="stTable"] table {
                background: #253342;
                color: #ffffff;
                border-color: #3e5954;
            }
            [data-testid="stTable"] th {
                background: #3e5954;
                color: #ffffff;
                border-color: #5e9188;
            }
            [data-testid="stTable"] td { border-color: #3e5954; }
            [data-testid="stTable"] tbody tr:nth-child(even) { background: #2d3d4d; }
            .app-table-wrap {
                overflow-x: auto;
                background: #253342;
                border: 1px solid #5e9188;
                border-radius: 10px;
            }
            .app-table { width: 100%; border-collapse: collapse; color: #ffffff; }
            .app-table th {
                background: #3e5954;
                color: #ffffff;
                font-weight: 700;
                text-align: left;
            }
            .app-table th, .app-table td {
                border: 1px solid #3e5954;
                padding: 0.7rem;
                vertical-align: top;
            }
            .app-table td { background: #253342; }
            .app-table tbody tr:nth-child(even) td { background: #2d3d4d; }
            [data-testid="stCheckbox"] {
                background: #283845;
                border-left: 3px solid #5e9188;
                border-radius: 6px;
                margin: 0.2rem 0;
                padding: 0.3rem 0.5rem;
            }
            [data-testid="stCheckbox"]:has(input:checked) {
                background: #24483f;
                border-left-color: #83c7b8;
            }
            [data-testid="stCheckbox"]:has(input:disabled) {
                background: #202b36;
                border-left: 3px solid #60707e;
                border-radius: 6px;
                opacity: 0.72;
            }
            [data-testid="stCheckbox"]:has(input:disabled) label { color: #a9b8c2 !important; }
            [role="tooltip"], [data-baseweb="tooltip"] {
                background: #18212b !important;
                border: 1px solid #5e9188 !important;
                color: #ffffff !important;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35) !important;
            }
            [role="tooltip"] *, [data-baseweb="tooltip"] * { color: #ffffff !important; }
            [data-testid="stExpander"] { background: #253342; border-color: #3e5954; }
            [data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: #ffffff !important; }
            [data-testid="stTabs"] [data-baseweb="tab"] { color: #d7e4e1; }
            [data-testid="stTabs"] [aria-selected="true"] { color: #ffffff !important; }
            [data-testid="stBaseButton-secondary"], button[kind="secondary"] {
                background: #253342 !important; border-color: #5e9188 !important; color: #ffffff !important;
            }
            [data-testid="stBaseButton-secondary"] *, button[kind="secondary"] * { color: #ffffff !important; }
            [data-testid="stBaseButton-secondary"]:hover, button[kind="secondary"]:hover {
                background: #3e5954 !important; border-color: #5e9188 !important; color: #ffffff !important;
            }
            [data-testid="stBaseButton-secondary"]:hover *, button[kind="secondary"]:hover * { color: #ffffff !important; }
            [data-testid="stBaseButton-primary"], button[kind="primary"] {
                background: #5e9188 !important; border-color: #5e9188 !important; color: #232226 !important;
            }
            [data-testid="stBaseButton-primary"] *, button[kind="primary"] * { color: #232226 !important; }
            [data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover {
                background: #3e5954 !important; border-color: #5e9188 !important; color: #ffffff !important;
            }
            [data-testid="stBaseButton-primary"]:hover *, button[kind="primary"]:hover * { color: #ffffff !important; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            :root { --agenda-active: #dceee8; --agenda-active-text: #232226; --agenda-closed: #e6eeec; --agenda-closed-text: #232226; --input-bg: #ffffff; --input-border: #5e9188; --input-focus: #3e5954; --input-text: #232226; }
            .stApp { background: #f4f7f6; color: #232226; }
            [data-testid="stMain"], [data-testid="stMain"] p, [data-testid="stMain"] label,
            [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3,
            [data-testid="stMain"] h4, [data-testid="stMain"] h5, [data-testid="stMain"] h6 { color: #232226; }
            [data-testid="stMain"] .stCaption, [data-testid="stMain"] [data-testid="stCaptionContainer"] { color: #3e5954 !important; }
            .app-header h1 { color: #ffffff !important; }
            .app-header .sub { color: #d7e4e1 !important; }
            .artigo-tag {
                background: #eef4f2;
                border: 1px solid #c7d8d4;
                color: #253342;
                box-shadow: none;
                font-weight: 600;
            }
            [data-testid="stMain"] a { color: #1f5f78; }
            [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"] {
                background: #ffffff; border-color: #c7d8d4;
            }
            [data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: #232226 !important; }
            [data-testid="stMetric"] {
                background: #ffffff; border: 1px solid #c7d8d4; border-left: 5px solid #5e9188;
                padding: 0.75rem; border-radius: 10px; box-shadow: 0 3px 10px rgba(35, 34, 38, 0.08);
            }
            [data-testid="stMetric"] [data-testid="stMetricLabel"],
            [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #232226 !important; }
            [data-testid="stDataFrame"] {
                --gdg-bg-cell: #ffffff !important;
                --gdg-bg-cell-medium: #f1f6f4 !important;
                --gdg-bg-header: #e0ece8 !important;
                --gdg-bg-header-has-focus: #cce1da !important;
                --gdg-bg-header-hovered: #cce1da !important;
                --gdg-bg-bubble: #e7f4ef !important;
                --gdg-bg-bubble-selected: #cce1da !important;
                --gdg-text-dark: #232226 !important;
                --gdg-text-medium: #3e5954 !important;
                --gdg-text-light: #63736f !important;
                --gdg-text-header: #232226 !important;
                --gdg-border-color: #c7d8d4 !important;
                --gdg-horizontal-border-color: #d9e5e1 !important;
                --gdg-link-color: #1f5f78 !important;
                background: #ffffff;
                border: 1px solid #c7d8d4;
                border-radius: 10px;
                overflow: hidden;
            }
            [data-testid="stDataFrame"] .dvn-scroller { background: #ffffff !important; }
            [data-testid="stTable"] table {
                background: #ffffff;
                color: #232226;
                border-color: #c7d8d4;
            }
            [data-testid="stTable"] th {
                background: #e0ece8;
                color: #232226;
                border-color: #b6cec6;
            }
            [data-testid="stTable"] td { border-color: #d9e5e1; }
            [data-testid="stTable"] tbody tr:nth-child(even) { background: #f1f6f4; }
            .app-table-wrap {
                overflow-x: auto;
                background: #ffffff;
                border: 1px solid #c7d8d4;
                border-radius: 10px;
            }
            .app-table { width: 100%; border-collapse: collapse; color: #232226; }
            .app-table th {
                background: #e0ece8;
                color: #232226;
                font-weight: 700;
                text-align: left;
            }
            .app-table th, .app-table td {
                border: 1px solid #d9e5e1;
                padding: 0.7rem;
                vertical-align: top;
            }
            .app-table td { background: #ffffff; }
            .app-table tbody tr:nth-child(even) td { background: #f1f6f4; }
            [data-testid="stCheckbox"] {
                background: #ffffff;
                border-left: 3px solid #5e9188;
                border-radius: 6px;
                margin: 0.2rem 0;
                padding: 0.3rem 0.5rem;
            }
            [data-testid="stCheckbox"]:has(input:checked) {
                background: #e7f4ef;
                border-left-color: #176b4d;
            }
            [data-testid="stCheckbox"]:has(input:disabled) {
                background: #edf1f0;
                border-left-color: #9aa9a5;
                opacity: 0.76;
            }
            [data-testid="stCheckbox"]:has(input:disabled) label { color: #63736f !important; }
            [role="tooltip"], [data-baseweb="tooltip"] {
                background: #ffffff !important;
                border: 1px solid #5e9188 !important;
                color: #232226 !important;
                box-shadow: 0 8px 20px rgba(35, 34, 38, 0.18) !important;
            }
            [role="tooltip"] *, [data-baseweb="tooltip"] * { color: #232226 !important; }
            [data-testid="stTabs"] [data-baseweb="tab"] { color: #3e5954; }
            [data-testid="stTabs"] [aria-selected="true"] { color: #232226 !important; }
            [data-testid="stBaseButton-primary"], button[kind="primary"] {
                background: #3e5954 !important; border-color: #3e5954 !important; color: #ffffff !important;
            }
            [data-testid="stBaseButton-primary"] *, button[kind="primary"] * { color: #ffffff !important; }
            [data-testid="stBaseButton-secondary"], button[kind="secondary"] {
                background: #ffffff !important; border-color: #5e9188 !important; color: #232226 !important;
            }
            [data-testid="stBaseButton-secondary"] *, button[kind="secondary"] * { color: #232226 !important; }
        </style>
        """, unsafe_allow_html=True)


def exibir_tabela_tematica(dados):
    """Renderiza a tabela usando o componente padrão do Streamlit."""
    tabela = dados if isinstance(dados, pd.DataFrame) else pd.DataFrame(dados)
    if tabela.empty:
        st.info("Nenhum registro encontrado.")
        return
    st.dataframe(tabela, use_container_width=True, hide_index=True)


CATEGORIA_COR = {
    "Acesso": "#1f5f78",
    "Software": "#5b3f88",
    "Hardware": "#8a5a00",
    "Rede": "#176b4d",
    "Outros": "#3e5954",
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
    icone = ICONE_URGENCIA.get(urgencia, "•")
    return badge(f"{icone} {urgencia or '-'}", CORES_URGENCIA.get(urgencia, "#64748b"))


def badge_sla(texto, status_sla_texto):
    icone = ICONE_SLA.get(status_sla_texto, "•")
    return badge(f"{icone} {texto}", sla.CORES_SLA.get(status_sla_texto, "#64748b"))


def bloco_fila(texto, cor, icone=""):
    """Etiqueta de cor sólida usada somente nos cartões da fila de atendimento."""
    return (
        '<span style="display:inline-block; padding:0.28rem 0.55rem; margin:0 0.3rem 0.35rem 0; '
        f'border-radius:0.4rem; background:{cor}; color:#ffffff; font-size:0.78rem; font-weight:600;">'
        f'{escape(icone)} {escape(str(texto))}</span>'
    )


CORES_FILA_STATUS = {
    "Novo": "#2563eb",
    "Aberto": "#2563eb",
    "Em Andamento": "#f97316",
    "Em Espera": "#9333ea",
    "Resolvido": "#16a34a",
    "Fechado": "#15803d",
    "Cancelado": "#64748b",
}
CORES_FILA_URGENCIA = {
    "Critica": "#dc2626", "Alta": "#f97316", "Media": "#d97706", "Baixa": "#16a34a",
}
CORES_FILA_SLA = {
    "Dentro do prazo": "#16a34a", "Em risco": "#f97316", "Violado": "#dc2626",
    "Pausado": "#9333ea", "Cumprido": "#16a34a", "Não aplicável": "#64748b",
}


def etiquetas_fila(chamado, estado_sla):
    """Agrupa status e urgência em blocos visuais objetivos."""
    status = chamado.get("status") or "Não informado"
    urgencia = chamado.get("urgencia") or "Não informada"
    icone_status = "✅" if status in {"Resolvido", "Fechado"} else ""
    return "".join((
        bloco_fila(status, CORES_FILA_STATUS.get(status, "#64748b"), icone_status),
        bloco_fila(urgencia, CORES_FILA_URGENCIA.get(urgencia, "#64748b"), ICONE_URGENCIA.get(urgencia, "")),
    ))


def etiquetas_sla_fila(estado_sla):
    """Mostra resposta e resolução como blocos independentes, sem marcador de texto."""
    def etiqueta(etapa, situacao):
        icone = "🚨" if situacao == "Violado" else "⚠️" if situacao == "Em risco" else "⏸️" if situacao == "Pausado" else "✅" if situacao == "Cumprido" else ""
        return bloco_fila(f"{etapa}: {situacao}", CORES_FILA_SLA.get(situacao, "#64748b"), icone)

    return etiqueta("Resposta", estado_sla["resposta"]["status"]) + etiqueta("Resolução", estado_sla["resolucao"]["status"])


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
        st.info("⏸ Em espera: aguardamos uma informação ou ação do solicitante. O relógio de SLA está pausado nesse período.")


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


def cabecalho(titulo, subtitulo, icone="🎫"):
    st.title(f"{icone} {titulo}")
    st.caption(subtitulo)


ESTADO_INICIAL_SESSAO = {
    "usuario_logado": None,
    "usuario_pendente_2fa": None,
    "login_auditoria_registrada": False,
    "admin_nav": "Usuários",
    "usuario_nav": "Central de ajuda",
    "analista_nav": "Fila ativa",
    "tela_atual": "login",
    "email_recuperacao": None,
    "aceite_privacidade_validado": False,
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
        st.caption("Entre com suas credenciais para continuar.")

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

            if st.button("Voltar ao login", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()


def sair():
    usuario = st.session_state.get("usuario_logado")
    if usuario:
        registrar_auditoria(usuario["id"], "LOGOUT_REALIZADO", "sessao")
    st.session_state.usuario_logado = None
    st.session_state.login_auditoria_registrada = False
    st.session_state.aceite_privacidade_validado = False
    for chave in (
        "chat_mensagens", "chat_turnos_usuario", "chat_resultado_final", "chat_etapa",
        "chamado_aberto_usuario", "chamado_selecionado_analista",
        "chamado_selecionado_historico", "chamado_selecionado_cancelado",
    ):
        st.session_state.pop(chave, None)
    st.rerun()


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
    pesquisa = buscar_pesquisa_satisfacao(chamado["id"], usuario["id"])
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
    col_dispositivo, col_servico, col_sintoma = st.columns(3)
    with col_dispositivo:
        dispositivo = st.text_input("Dispositivo", placeholder="Notebook, celular, impressora").strip().lower()
    with col_servico:
        servico = st.text_input("Serviço", placeholder="E-mail, VPN, Wi-Fi").strip().lower()
    with col_sintoma:
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

    opcoes_navegacao = [
        "Central de ajuda",
        "Abrir novo chamado",
        "Meus chamados ativos",
        "Meus chamados fechados",
        "Meus chamados cancelados",
    ]
    if st.session_state.get("usuario_nav") not in opcoes_navegacao:
        st.session_state.usuario_nav = opcoes_navegacao[0]
    with st.sidebar:
        st.markdown('<div class="sidebar-section">Portal do usuário</div>', unsafe_allow_html=True)
        navegacao = st.radio(
            "Seções do portal", opcoes_navegacao, key="usuario_nav", label_visibility="collapsed",
        )

    if navegacao == "Central de ajuda":
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
                st.success("Encontrei uma possível solução com base nos dados informados.")
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
                    resolvido = st.button("A solução resolveu o problema", type="primary", use_container_width=True)
                with col_abrir:
                    abrir_chamado = st.button("Não resolveu — abrir chamado", use_container_width=True)

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
            st.markdown(f"{badge_status(chamado['status'])} {badge_urgencia(chamado['urgencia'])}", unsafe_allow_html=True)
            st.write(chamado["descricao"])

            st.markdown(f'<span class="sla-pill">👥 Equipe: {chamado.get("equipe_destino") or "—"}</span>', unsafe_allow_html=True)
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))
            st.caption(f"Analista responsável: {chamado.get('nome_analista') or 'Aguardando atribuição'}")
            st.info(f"**Status atual:** {chamado['status']}. {_quem_precisa_agir(chamado)}")
            if chamado["status"] == "Cancelado":
                st.warning(f"Cancelado: {chamado.get('motivo_cancelamento') or 'Não informado'}. O registro permanece disponível apenas para consulta e auditoria.")

        linha_do_tempo_chamado(chamado, usuario["id"])

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
                        st.success("Chamado cancelado. Ele não será encaminhado para atendimento e ficará disponível apenas para consulta e auditoria.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()

        elif chamado["status"] == "Resolvido":
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
                    st.success("Solução confirmada. Chamado fechado.")
                except ValueError as erro:
                    st.error(str(erro))
                st.rerun()
            with st.form(f"form_reabrir_{chamado['id']}"):
                motivo_reabertura = st.text_area("Motivo da reabertura", max_chars=500)
                reabrir = st.form_submit_button("Solicitar reabertura")
            if reabrir:
                try:
                    reabrir_chamado_usuario(chamado["id"], usuario["id"], motivo_reabertura)
                    st.success("Chamado reaberto e devolvido para atendimento.")
                except ValueError as erro:
                    st.error(str(erro))
                st.rerun()

        painel_pesquisa_satisfacao(chamado, usuario)


def tela_analista(usuario):
    injetar_css()
    cabecalho("Central de Serviços — Analista", f"{usuario['nome']} · Gestão de Incidentes")

    chamados = listar_chamados(limite=200, executor_id=usuario["id"])

    opcoes_navegacao = ["Fila ativa", "Histórico (fechados)", "Cancelados"]
    if st.session_state.get("analista_nav") not in opcoes_navegacao:
        st.session_state.analista_nav = opcoes_navegacao[0]
    with st.sidebar:
        st.markdown('<div class="sidebar-section">Atendimento</div>', unsafe_allow_html=True)
        navegacao = st.radio(
            "Seções de atendimento", opcoes_navegacao, key="analista_nav", label_visibility="collapsed",
        )

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

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chamados ativos", total)
    m2.metric("Novos", novos)
    m3.metric("Em andamento", em_andamento)
    m4.metric("Atribuídos a mim", meus)

    st.divider()

    with st.container(border=True):
        st.markdown("##### Filtros da fila")
        busca_col, status_col, urgencia_col = st.columns([2, 1, 1])
        with busca_col:
            busca_textual = st.text_input(
                "Buscar chamado",
                placeholder="Título, descrição ou solicitante",
                key="busca_chamado_ativa",
            ).strip().lower()
        with status_col:
            filtro_status = st.multiselect("Status", options=STATUS_OPCOES, default=[], key="filtro_status_ativa")
        with urgencia_col:
            filtro_urgencia = st.multiselect(
                "Urgência", options=["Critica", "Alta", "Media", "Baixa"], default=[], key="filtro_urgencia_ativa",
            )

        categoria_col, departamento_col, analista_col, sla_col, responsavel_col = st.columns(5)
        with categoria_col:
            categorias_fila = ["Todas"] + sorted({c.get("categoria") or "Outros" for c in chamados})
            filtro_categoria = st.selectbox("Categoria", categorias_fila, key="filtro_categoria_ativa")
        with departamento_col:
            departamentos_fila = ["Todos"] + sorted({c.get("departamento_usuario") or "Não informado" for c in chamados})
            filtro_departamento = st.selectbox("Departamento", departamentos_fila, key="filtro_departamento_ativa")
        with analista_col:
            analistas_fila = ["Todos"] + sorted({c.get("nome_analista") or "Sem atribuição" for c in chamados})
            filtro_analista = st.selectbox("Analista", analistas_fila, key="filtro_analista_ativa")
        with sla_col:
            filtro_sla = st.multiselect(
                "Situação de SLA", ["Violado", "Em risco", "Dentro do prazo", "Pausado"], key="filtro_sla_ativa",
            )
        with responsavel_col:
            st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
            somente_meus = st.checkbox("Atribuídos a mim", key="somente_meus_ativa")

    chamados_filtrados = chamados
    if filtro_status:
        chamados_filtrados = [c for c in chamados_filtrados if c["status"] in filtro_status]
    if filtro_urgencia:
        chamados_filtrados = [c for c in chamados_filtrados if c["urgencia"] in filtro_urgencia]
    if somente_meus:
        chamados_filtrados = [c for c in chamados_filtrados if c.get("analista_id") == usuario["id"]]
    if filtro_sla:
        chamados_filtrados = [c for c in chamados_filtrados if sla.pior_status(sla.status_sla(c)) in filtro_sla]
    if filtro_categoria != "Todas":
        chamados_filtrados = [c for c in chamados_filtrados if c.get("categoria") == filtro_categoria]
    if filtro_departamento != "Todos":
        chamados_filtrados = [c for c in chamados_filtrados if (c.get("departamento_usuario") or "Não informado") == filtro_departamento]
    if filtro_analista != "Todos":
        chamados_filtrados = [c for c in chamados_filtrados if (c.get("nome_analista") or "Sem atribuição") == filtro_analista]
    if busca_textual:
        chamados_filtrados = [c for c in chamados_filtrados if busca_textual in " ".join(str(c.get(campo) or "") for campo in ("titulo", "descricao", "nome_usuario")).lower()]

    st.caption(f"{len(chamados_filtrados)} de {len(chamados)} chamado(s) exibido(s).")

    fila_col, detalhe_col = st.columns([1, 1.6])

    with fila_col:
        st.markdown("##### Fila de chamados")
        if not chamados_filtrados:
            st.caption("Nenhum chamado com os filtros selecionados.")
        for c in chamados_filtrados:
            selecionado = st.session_state.chamado_selecionado_analista == c["id"]
            estado_sla = sla.status_sla(c)
            responsavel = c.get("nome_analista") or "Sem atribuição"
            with st.container(border=True):
                st.markdown(f"**#{c['id']} · {c['titulo']}**")
                st.markdown(etiquetas_fila(c, estado_sla), unsafe_allow_html=True)
                st.markdown(etiquetas_sla_fila(estado_sla), unsafe_allow_html=True)
                st.caption(
                    f"Solicitante: {c.get('nome_usuario') or '—'} · "
                    f"Responsável: {responsavel}"
                )
                if selecionado:
                    st.button(
                        "Chamado selecionado", key=f"sel_{c['id']}", type="primary",
                        use_container_width=True, disabled=True,
                    )
                elif st.button("Ver detalhes", key=f"sel_{c['id']}", use_container_width=True):
                    st.session_state.chamado_selecionado_analista = c["id"]
                    st.rerun()

    with detalhe_col:
        chamado_id_sel = st.session_state.chamado_selecionado_analista
        if chamado_id_sel is None:
            st.info("Selecione um chamado na fila para atender.")
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
                st.caption(f"Status: {chamado['status']} · Urgência: {chamado['urgencia']}")
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

            categoria_col, equipe_col, ia_col = st.columns(3)
            categoria_col.caption(f"Categoria: {chamado.get('categoria') or '—'}")
            equipe_col.caption(f"Equipe: {chamado.get('equipe_destino') or '—'}")
            ia_col.caption(f"Confiança da IA: {chamado.get('confiabilidade') or '—'}")
            bloco_sla_detalhe(chamado, sla.status_sla(chamado))
            st.caption(f"Solicitante: {chamado.get('nome_usuario') or '-'} · Aberto em {chamado.get('criado_em').strftime('%d/%m/%Y %H:%M:%S')}")

            if ja_atribuido_a_mim and chamado["status"] == "Em Andamento" and not chamado.get("primeira_resposta_em"):
                st.warning("A primeira resposta ainda não foi registrada. Ela é obrigatória antes de resolver o chamado e inicia o indicador de atendimento.")
                with st.form(f"form_primeira_resposta_{chamado['id']}"):
                    primeira_resposta = st.text_area("Primeira resposta ao solicitante", placeholder="Confirme que está analisando e informe o próximo passo.", max_chars=4000)
                    enviar_primeira_resposta = st.form_submit_button("Enviar primeira resposta", type="primary")
                if enviar_primeira_resposta:
                    if not primeira_resposta.strip():
                        st.error("Escreva uma mensagem antes de enviar.")
                    else:
                        enviar_mensagem_chamado(chamado["id"], usuario["id"], usuario["nome"], "analista", primeira_resposta.strip())
                        st.success("Primeira resposta registrada e enviada ao solicitante.")
                        st.rerun()

            if (
                ja_atribuido_a_mim
                and chamado["status"] in ("Em Andamento", "Em Espera")
                and chamado.get("primeira_resposta_em")
            ):
                st.divider()
                st.caption("A primeira resposta foi registrada. Você pode continuar a conversa ou registrar a resolução para que o solicitante confirme o resultado. A aprovação para a base interna da IA é uma decisão separada e opcional.")
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
                    marcar_resolvido = st.form_submit_button("Registrar resolução", type="primary", use_container_width=True)
                if marcar_resolvido:
                    try:
                        registrar_resolucao_chamado(
                            chamado["id"], usuario["id"], diagnostico, solucao, compartilhar,
                            categoria_final, urgencia_final, equipe_final,
                        )
                        st.success("Resolução registrada. O solicitante poderá confirmar ou solicitar reabertura.")
                    except ValueError as erro:
                        st.error(str(erro))
                    st.rerun()
            elif ja_atribuido_a_mim and chamado["status"] == "Em Espera":
                st.info("Aguardando a resposta do solicitante. Você ainda pode enviar mensagens ou registrar a resolução, se o atendimento já estiver concluído.")
            elif ja_atribuido_a_mim and chamado["status"] == "Resolvido":
                st.info("Aguardando a confirmação do solicitante para fechar ou reabrir o chamado.")

            if ja_atribuido_a_mim and chamado["status"] not in STATUS_ENCERRADOS:
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
                                st.success("Chamado transferido."); st.rerun()
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
                            st.success("Chamado escalado."); st.rerun()
                        except (ValueError, PermissionError) as erro:
                            st.error(str(erro))

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
        with st.expander("Histórico operacional"):
            for evento in listar_historico_chamado(chamado["id"], usuario["id"]):
                st.caption(f"{evento['criado_em'].strftime('%d/%m/%Y %H:%M')} · {evento['tipo']} · {evento.get('autor_nome') or 'Sistema'}")


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

        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
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

        chamado = buscar_chamado_por_id(chamado_id_sel, usuario["id"])
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
        with st.expander("Decisões e alterações de status"):
            for evento in listar_historico_chamado(chamado["id"], usuario["id"]):
                st.caption(f"{sla.formatar_data(evento['criado_em'])} · {evento['tipo'].replace('_', ' ').title()} · {evento.get('autor_nome') or 'Sistema'}")


def _estilizar_grafico(figura, eixo):
    """Preserva o estilo padrão do Matplotlib exibido pelo Streamlit."""
    return


def _exibir_grafico_barras(dados, titulo, eixo_x, eixo_y, cor="#5e9188"):
    """Exibe um gráfico Matplotlib consistente e trata conjuntos de dados vazios."""
    if dados.empty or dados[eixo_y].sum() == 0:
        st.info("Ainda não há dados suficientes para este gráfico.")
        return

    figura, eixo = plt.subplots(figsize=(7, 3.4))
    _estilizar_grafico(figura, eixo)
    barras = eixo.bar(dados[eixo_x].astype(str), dados[eixo_y], color=cor)
    eixo.set_title(titulo, loc="left", fontweight="bold")
    eixo.set_xlabel("")
    eixo.set_ylabel(eixo_y)
    eixo.spines[["top", "right"]].set_visible(False)
    eixo.tick_params(axis="x", rotation=20)
    for barra in barras:
        altura = barra.get_height()
        eixo.annotate(f"{altura:.0f}", (barra.get_x() + barra.get_width() / 2, altura),
                      ha="center", va="bottom", fontsize=9,
                      color="#262730")
    figura.tight_layout()
    st.pyplot(figura, use_container_width=True)
    plt.close(figura)


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
        _exibir_grafico_barras(distribuicao, "Contas por perfil", "Perfil", "Quantidade", "#3e5954")
    with tabela:
        exibir_tabela_tematica(distribuicao)


def relatorio_sla_desempenho(chamados):
    st.markdown("### Relatório de desempenho e cumprimento de SLA")
    st.caption("Cancelados não entram no cálculo. O cumprimento considera chamados com a respectiva etapa concluída.")
    dados = pd.DataFrame(chamados)
    if dados.empty:
        st.info("Ainda não há chamados para calcular os indicadores de SLA.")
        return

    estados = dados["status"].value_counts()
    operacionais = st.columns(5)
    for coluna, status in zip(operacionais, ["Em Andamento", "Em Espera", "Resolvido", "Fechado", "Cancelado"]):
        coluna.metric(status, int(estados.get(status, 0)))

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
    _estilizar_grafico(figura, eixo)
    posicoes = range(len(resumo))
    eixo.bar([p - 0.2 for p in posicoes], resumo["Resposta"], width=0.4, label="Resposta", color="#5e9188")
    eixo.bar([p + 0.2 for p in posicoes], resumo["Resolução"], width=0.4, label="Resolução", color="#3e5954")
    eixo.set_xticks(list(posicoes), resumo["Status"], rotation=15)
    eixo.set_ylabel("Chamados")
    eixo.set_title("Situação dos prazos de SLA", loc="left", fontweight="bold")
    legenda = eixo.legend(frameon=False)
    for texto in legenda.get_texts():
        texto.set_color("#262730")
    eixo.spines[["top", "right"]].set_visible(False)
    figura.tight_layout()
    st.pyplot(figura, use_container_width=True)
    plt.close(figura)


def relatorio_ia(chamados, admin):
    st.markdown("### Qualidade da classificação da IA")
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
        "#5e9188",
    )


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
    _exibir_grafico_barras(produtividade, "Chamados fechados por analista", "Analista", "Fechados", "#8a5a00")
    tabela = produtividade.copy()
    tabela["Tempo médio de resolução (h)"] = tabela["Tempo médio de resolução (h)"].map(lambda valor: f"{valor:.1f}" if pd.notna(valor) else "—")
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
        _exibir_grafico_barras(motivos, "Cancelamentos por motivo", "Motivo", "Quantidade", "#a82a22")
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
    st.markdown("### Direitos do titular")
    st.caption("Consulte o titular por e-mail ou CPF. A busca por CPF é exata e o número completo não é exibido.")
    identificador = st.text_input("E-mail ou CPF do titular", key="privacidade_identificador")
    if not st.button("Localizar titular", type="primary", key="privacidade_localizar"):
        return

    try:
        titular, erro = buscar_titular_por_identificador(identificador, executor_id=admin["id"])
    except ValueError as erro:
        st.error(str(erro))
        return
    if erro:
        st.warning(erro)
        return

    st.session_state.titular_privacidade_id = titular["id"]
    st.rerun()


def tela_aceite_privacidade(usuario):
    injetar_css()
    col_esq, col_meio, col_dir = st.columns([1, 1.5, 1])
    with col_meio:
        st.markdown("### Privacidade e uso do sistema")
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
            confirmar = st.form_submit_button("Aceitar e continuar", type="primary", use_container_width=True)
        if confirmar:
            if not aceito:
                st.warning("Para continuar, confirme a leitura e o aceite do Aviso de Privacidade.")
            else:
                registrar_aceite_privacidade(usuario["id"], "uso_do_sistema")
                st.session_state.aceite_privacidade_validado = True
                st.rerun()


def acoes_privacidade_admin(admin):
    titular_id = st.session_state.get("titular_privacidade_id")
    if not titular_id:
        return
    titular = buscar_usuario_por_id(titular_id, executor_id=admin["id"])
    if not titular:
        st.session_state.pop("titular_privacidade_id", None)
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
                use_container_width=True,
            )
            st.caption(f"Arquivo disponível até {exportacao['expira_em'].strftime('%d/%m/%Y %H:%M')} UTC.")
    st.caption("O arquivo contém os dados acessíveis do titular e anexos. Senha, segredo TOTP e códigos não são exportados.")

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
    st.markdown("### Departamentos")
    st.caption("Organize a estrutura da empresa. Departamentos inativos são preservados no histórico e não aparecem em novos cadastros.")

    with st.expander("Cadastrar departamento", expanded=False):
        with st.form("form_novo_departamento", clear_on_submit=True):
            nome = st.text_input("Nome do departamento")
            descricao = st.text_input("Descrição (opcional)")
            cadastrar = st.form_submit_button("Cadastrar departamento", type="primary")
        if cadastrar:
            try:
                criar_departamento(nome, descricao, autor_id=admin["id"])
                st.success("Departamento cadastrado.")
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))

    departamentos = listar_departamentos()
    if not departamentos:
        st.info("Nenhum departamento cadastrado.")
        return

    tabela = pd.DataFrame(departamentos)[["nome", "descricao", "ativo", "total_usuarios"]].copy()
    tabela.columns = ["Nome", "Descrição", "Ativo", "Usuários vinculados"]
    tabela["Ativo"] = tabela["Ativo"].map(
        lambda valor: "Sim" if valor in (True, 1, "1", "true", "True", "Sim", "sim") else "Não"
    )
    exibir_tabela_tematica(tabela)

    por_id = {departamento["id"]: departamento for departamento in departamentos}
    departamento_id = st.selectbox(
        "Editar departamento",
        options=list(por_id),
        format_func=lambda item: por_id[item]["nome"],
    )
    departamento = por_id[departamento_id]
    with st.form(f"form_editar_departamento_{departamento_id}"):
        nome = st.text_input("Nome", value=departamento["nome"])
        descricao = st.text_input("Descrição", value=departamento.get("descricao") or "")
        ativo = st.checkbox("Departamento ativo", value=bool(departamento["ativo"]))
        salvar = st.form_submit_button("Salvar departamento", type="primary")
    if salvar:
        try:
            atualizar_departamento(departamento_id, nome, descricao, ativo, autor_id=admin["id"])
            st.success("Departamento atualizado.")
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))


def painel_sla_admin(admin):
    st.markdown("### Configurações de SLA e horário comercial")
    st.caption("Estas configurações passam a valer para novos chamados. Chamados já abertos preservam a configuração vigente quando foram criados.")
    configuracao = obter_configuracao_sla()
    nomes_dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dias_atuais = [nomes_dias[dia] for dia in configuracao["dias_uteis"]]
    st.markdown("#### Agenda semanal vigente")
    st.caption("Todos os horários são exibidos em UTC no ambiente produtivo.")
    agenda = []
    for indice, dia in enumerate(nomes_dias):
        if indice in configuracao["dias_uteis"]:
            agenda.append(
                f"<div class='agenda-linha'><strong>{dia}</strong><div class='agenda-faixa agenda-ativa'>"
                f"🟢 Atendimento: {configuracao['hora_inicio']} — {configuracao['hora_fim']}</div></div>"
            )
        else:
            agenda.append(f"<div class='agenda-linha'><strong>{dia}</strong><div class='agenda-faixa agenda-fechada'>Fechado</div></div>")
    st.markdown(
        """<style>
        .agenda-linha {display:grid; grid-template-columns:110px 1fr; gap:10px; align-items:center; margin:8px 0;}
        .agenda-faixa {border-radius:8px; padding:10px 12px; font-size:0.9rem; font-weight:600; border:1px solid rgba(100,116,139,.28);}
        .agenda-ativa {background:var(--agenda-active); border-left:7px solid var(--success); color:var(--agenda-active-text);}
        .agenda-fechada {background:var(--agenda-closed); border-left:7px solid var(--muted); color:var(--agenda-closed-text);}
        </style>""" + "".join(agenda), unsafe_allow_html=True,
    )
    with st.form("form_configuracao_sla"):
        dias = st.multiselect("Dias de atendimento", nomes_dias, default=dias_atuais)
        col_inicio, col_fim, col_fechamento, col_risco = st.columns(4)
        with col_inicio:
            inicio = st.time_input("Início", value=time.fromisoformat(configuracao["hora_inicio"]))
        with col_fim:
            fim = st.time_input("Fim", value=time.fromisoformat(configuracao["hora_fim"]))
        with col_fechamento:
            fechamento = st.number_input("Fechamento automático (horas comerciais)", min_value=1, max_value=720, value=configuracao["horas_fechamento_automatico"])
        with col_risco:
            risco = st.number_input("Alerta de risco após (%)", min_value=1, max_value=99, value=int(configuracao["limiar_risco"] * 100))
        st.markdown("#### Prazos por urgência (minutos comerciais)")
        matriz = {}
        for urgencia in ["Critica", "Alta", "Media", "Baixa"]:
            resposta_col, resolucao_col = st.columns(2)
            with resposta_col:
                resposta = st.number_input(f"{urgencia} — primeira resposta", min_value=1, value=int(configuracao["matriz"][urgencia]["resposta"]), key=f"sla_resp_{urgencia}")
            with resolucao_col:
                resolucao = st.number_input(f"{urgencia} — resolução", min_value=1, value=int(configuracao["matriz"][urgencia]["resolucao"]), key=f"sla_res_{urgencia}")
            matriz[urgencia] = {"resposta": resposta, "resolucao": resolucao}
        salvar = st.form_submit_button("Salvar configurações", type="primary")
    if salvar:
        try:
            atualizar_configuracao_sla({"dias_uteis": [nomes_dias.index(dia) for dia in dias], "hora_inicio": inicio.strftime("%H:%M"), "hora_fim": fim.strftime("%H:%M"), "horas_fechamento_automatico": fechamento, "limiar_risco": risco / 100, "matriz": matriz}, admin["id"])
            st.success("Configurações de SLA atualizadas para novos chamados.")
            st.rerun()
        except (ValueError, PermissionError) as erro:
            st.error(str(erro))


def painel_auditoria_admin(admin):
    st.markdown("### Auditoria operacional")
    st.caption("Consulta protegida de operações relevantes. Exportações omitem dados pessoais e conteúdos de chamados.")
    colunas = st.columns(3)
    with colunas[0]:
        usuario_id = st.number_input("ID do usuário", min_value=0, value=0)
        acao = st.text_input("Ação exata")
    with colunas[1]:
        entidade = st.text_input("Entidade")
        resultado = st.selectbox("Resultado", ["", "SUCESSO", "FALHA"])
    with colunas[2]:
        limite = st.selectbox("Eventos por página", [50, 100, 200], index=1)
        pagina = st.number_input("Página", min_value=1, value=1, step=1)
    periodo = st.date_input("Período", value=(), key="auditoria_periodo")
    inicio = fim = None
    if isinstance(periodo, tuple) and len(periodo) == 2:
        inicio = datetime.combine(periodo[0], time.min)
        fim = datetime.combine(periodo[1] + timedelta(days=1), time.min)
    eventos = listar_auditoria(limite=limite, usuario_id=usuario_id or None,
                               acao=acao or None, entidade=entidade or None,
                               resultado=resultado or None, inicio=inicio, fim=fim, pagina=pagina - 1,
                               executor_id=admin["id"])
    if not eventos:
        st.info("Nenhum evento de auditoria encontrado.")
        return
    dados = pd.DataFrame(eventos)
    col_data, col_acao = st.columns(2)
    with col_data:
        busca_evento = st.text_input("Buscar ação ou entidade").strip().lower()
    with col_acao:
        acoes = ["Todas"] + sorted(dados["acao"].dropna().unique().tolist())
        acao = st.selectbox("Ação", acoes)
    if busca_evento:
        dados = dados[dados.apply(lambda linha: busca_evento in f"{linha.get('acao', '')} {linha.get('entidade', '')}".lower(), axis=1)]
    if acao != "Todas":
        dados = dados[dados["acao"] == acao]
    exibicao = dados[["criado_em", "acao", "entidade", "entidade_id", "resultado"]].copy()
    exibicao.columns = ["Data", "Ação", "Entidade", "ID", "Resultado"]
    exibir_tabela_tematica(exibicao)
    st.download_button("Exportar auditoria filtrada (CSV)", exibicao.to_csv(index=False).encode("utf-8-sig"), "auditoria.csv", "text/csv", use_container_width=True)


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
    reabertos = 0
    for chamado_id in dados["id"].tolist():
        reabertos += sum(evento["tipo"] == "REABERTURA" for evento in listar_historico_chamado(chamado_id, admin["id"]))
    c3.metric("Reaberturas", reabertos)
    c4.metric("Resolvidos/fechados", len(resolvidos))
    pesquisas = listar_pesquisas_satisfacao(admin["id"])
    if pesquisas:
        st.caption(f"Satisfação média: {sum(item['nota'] for item in pesquisas) / len(pesquisas):.1f}/5 em {len(pesquisas)} avaliação(ões).")
    carga = ativos.groupby(ativos["equipe_destino"].fillna("Sem equipe")).size().reset_index(name="Backlog")
    carga.columns = ["Equipe", "Backlog"]
    tendencia = dados.copy()
    tendencia["criado_em"] = pd.to_datetime(tendencia["criado_em"])
    tendencia = tendencia.groupby(tendencia["criado_em"].dt.date).size().reset_index(name="Chamados abertos")
    tendencia.columns = ["Data", "Chamados abertos"]
    carga_coluna, tendencia_coluna = st.columns(2)
    with carga_coluna:
        _exibir_grafico_barras(carga, "Carga atual por equipe", "Equipe", "Backlog", "#5e9188")
    with tendencia_coluna:
        _exibir_grafico_barras(tendencia, "Tendência de abertura no período", "Data", "Chamados abertos", "#3e5954")
    exportacao = dados[["id", "status", "categoria", "urgencia", "equipe_destino", "criado_em", "resolvido_em"]].copy()
    st.download_button("Exportar indicadores operacionais (CSV)", exportacao.to_csv(index=False).encode("utf-8-sig"), "indicadores_operacionais.csv", "text/csv")


def relatorio_chamados_abertos_por_departamento(chamados):
    """Exibe o backlog por departamento do solicitante, incluindo departamentos sem demanda."""
    st.markdown("### Chamados abertos por departamento")
    st.caption(
        "Considera os chamados que ainda não foram fechados ou cancelados, conforme o "
        "departamento do solicitante."
    )

    dados = pd.DataFrame(chamados)
    departamentos = listar_departamentos()
    nomes_departamentos = [departamento["nome"] for departamento in departamentos]

    if dados.empty:
        abertos_por_departamento = pd.DataFrame({
            "Departamento": nomes_departamentos,
            "Chamados abertos": [0] * len(nomes_departamentos),
        })
    else:
        abertos = dados[~dados["status"].isin(STATUS_ENCERRADOS)].copy()
        abertos["Departamento"] = (
            abertos["departamento_usuario"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "Não informado")
        )
        contagem = abertos.groupby("Departamento").size()
        ordem = list(dict.fromkeys(nomes_departamentos + contagem.index.tolist()))
        abertos_por_departamento = pd.DataFrame({
            "Departamento": ordem,
            "Chamados abertos": [int(contagem.get(nome, 0)) for nome in ordem],
        })

    total_abertos = int(abertos_por_departamento["Chamados abertos"].sum())
    sem_departamento = int(
        abertos_por_departamento.loc[
            abertos_por_departamento["Departamento"] == "Não informado", "Chamados abertos"
        ].sum()
    )
    maior_demanda = abertos_por_departamento.sort_values(
        "Chamados abertos", ascending=False
    ).head(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Chamados abertos", total_abertos)
    c2.metric(
        "Departamento com maior demanda",
        maior_demanda.iloc[0]["Departamento"] if total_abertos else "—",
        f"{int(maior_demanda.iloc[0]['Chamados abertos'])} chamado(s)" if total_abertos else None,
    )
    c3.metric("Sem departamento informado", sem_departamento)

    if abertos_por_departamento.empty:
        st.info("Cadastre departamentos para acompanhar a distribuição dos chamados.")
        return

    abertos_por_departamento = abertos_por_departamento.sort_values(
        ["Chamados abertos", "Departamento"], ascending=[False, True]
    ).reset_index(drop=True)
    grafico, tabela = st.columns([1.4, 1])
    with grafico:
        _exibir_grafico_barras(
            abertos_por_departamento,
            "Backlog por departamento",
            "Departamento",
            "Chamados abertos",
            "#1f5f78",
        )
    with tabela:
        exibir_tabela_tematica(abertos_por_departamento)


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

    dados["Departamento"] = (
        dados["departamento_usuario"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Não informado")
    )
    dados["Categoria"] = (
        dados["categoria"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Não classificada")
    )
    demanda_departamento = (
        dados.groupby("Departamento", as_index=False)
        .size()
        .rename(columns={"size": "Chamados criados"})
        .sort_values(["Chamados criados", "Departamento"], ascending=[False, True])
        .reset_index(drop=True)
    )
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
        _exibir_grafico_barras(
            categorias,
            f"Categorias recorrentes — {departamento_selecionado}",
            "Categoria",
            "Chamados criados",
            "#8a5a00",
        )
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
            st.markdown(f"##### {categoria}")
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

    with st.expander("Cadastrar perfil", expanded=False):
        nome = st.text_input("Nome do perfil", placeholder="Ex.: Suporte N1", key="novo_perfil_nome")
        descricao = st.text_input("Descrição (opcional)", key="novo_perfil_descricao")
        st.caption("Marque a primeira permissão de cada grupo para liberar suas ações adicionais.")
        permissao_ids = renderizar_permissoes("novo_perfil")
        cadastrar = st.button("Cadastrar perfil", type="primary", key="novo_perfil_cadastrar")
        if cadastrar:
            try:
                criar_perfil(nome, descricao, permissao_ids, admin["id"])
                for permissao in permissoes:
                    st.session_state.pop(f"novo_perfil_{permissao['id']}", None)
                st.session_state.pop("novo_perfil_nome", None)
                st.session_state.pop("novo_perfil_descricao", None)
                st.success("Perfil cadastrado.")
                st.rerun()
            except (ValueError, PermissionError, mysql.connector.Error) as erro:
                st.error(str(erro))

    tabela = pd.DataFrame(perfis)[["nome", "descricao", "ativo", "total_usuarios", "total_permissoes"]].copy()
    tabela.columns = ["Perfil", "Descrição", "Ativo", "Usuários vinculados", "Permissões"]
    tabela["Ativo"] = tabela["Ativo"].map(
        lambda valor: "Sim" if valor in (True, 1, "1", "true", "True", "Sim", "sim") else "Não"
    )
    exibir_tabela_tematica(tabela)

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
            st.success("Perfil atualizado.")
            st.rerun()
        except (ValueError, PermissionError, mysql.connector.Error) as erro:
            st.error(str(erro))
    if excluir:
        try:
            excluir_perfil(perfil_id, admin["id"])
            st.success("Perfil excluído.")
            st.rerun()
        except (ValueError, PermissionError, mysql.connector.Error) as erro:
            st.error(str(erro))


def painel_perfil_usuario_admin(admin):
    usuario_id = st.session_state.get("usuario_admin_aberto")
    conta = buscar_usuario_por_id(usuario_id, executor_id=admin["id"]) if usuario_id else None
    if not conta:
        st.info("Abra um usuário pela lista para consultar ou editar o perfil.")
        return
    if conta.get("perfil_chave") == "administrador" and not usuario_eh_administrador(admin["id"]):
        st.error("Somente um administrador pode alterar uma conta administrativa.")
        return

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
                    st.success("Perfil atualizado.")
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

    acoes, fechar = st.columns(2)
    with acoes:
        if conta["id"] != admin["id"]:
            confirmar_exclusao = st.checkbox("Confirmo a anonimização permanente desta conta e de seus dados associados.")
            st.button(
                "Anonimizar usuário", disabled=not confirmar_exclusao,
                on_click=excluir_perfil_usuario_admin,
                args=(conta["id"], admin["id"]),
            )
    with fechar:
        st.button("Voltar para usuários", on_click=fechar_perfil_usuario_admin)

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


def tela_admin(usuario):
    injetar_css()
    cabecalho("Administração", "Gerencie pessoas, operação, indicadores e conformidade", "🛡️")
    if not usuario_tem_permissao(usuario["id"], "administracao.acessar"):
        st.error("Você não tem permissão para acessar a área administrativa.")
        return

    pode_visualizar_usuarios = usuario_tem_permissao(usuario["id"], "usuarios.visualizar")
    pode_gerenciar_usuarios = usuario_tem_permissao(usuario["id"], "usuarios.gerenciar")
    pode_visualizar_relatorios = usuario_tem_permissao(usuario["id"], "relatorios.visualizar")
    usuarios = (
        listar_usuarios(executor_id=usuario["id"], para_relatorio=not pode_visualizar_usuarios)
        if pode_visualizar_usuarios or pode_visualizar_relatorios else []
    )

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
        st.markdown('<div class="sidebar-section">Administração</div>', unsafe_allow_html=True)
        navegacao = st.radio(
            "Seções administrativas",
            opcoes_navegacao,
            key="admin_nav",
            label_visibility="collapsed",
        )

    if navegacao == "Dashboards":
        chamados = listar_chamados(limite=5000, executor_id=usuario["id"], para_relatorio=True)
        hoje = datetime.now().date()
        st.subheader("Painel de indicadores")
        st.caption("Acompanhe a operação por período. Os filtros se aplicam a todos os painéis abaixo.")
        filtro_periodo, resumo_periodo = st.columns([1, 2])
        with filtro_periodo:
            periodo = st.date_input(
                "Período dos indicadores",
                value=(hoje.replace(day=1), hoje),
                max_value=hoje,
            )
        if isinstance(periodo, tuple) and len(periodo) == 2:
            inicio, fim = periodo
            chamados = [c for c in chamados if c.get("criado_em") and inicio <= c["criado_em"].date() <= fim]
        with resumo_periodo:
            st.metric("Chamados no período", len(chamados))

        visao_geral, operacao_sla, pessoas, inteligencia = st.tabs([
            "Visão geral", "Operação e SLA", "Pessoas", "IA e conhecimento",
        ])
        with visao_geral:
            relatorio_operacional(chamados, usuario)
            st.divider()
            relatorio_chamados_abertos_por_departamento(chamados)
            st.divider()
            relatorio_demanda_por_departamento_categoria(chamados)
        with operacao_sla:
            relatorio_sla_desempenho(chamados)
            st.divider()
            relatorio_produtividade_equipe(chamados)
            st.divider()
            relatorio_cancelamentos(chamados)
        with pessoas:
            relatorio_usuarios(usuarios)
        with inteligencia:
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
        if st.session_state.get("mensagem_admin"):
            st.success(st.session_state.pop("mensagem_admin"))
        if pode_gerenciar_usuarios:
            with st.expander("Cadastrar usuário", expanded=False):
                with st.form("form_novo_usuario", clear_on_submit=True):
                    departamentos_ativos = listar_departamentos(apenas_ativos=True)
                    departamentos_por_id = {departamento["id"]: departamento for departamento in departamentos_ativos}
                    perfis_ativos = listar_perfis_para_atribuicao(usuario["id"])
                    perfis_por_id = {perfil["id"]: perfil for perfil in perfis_ativos}
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
                            st.success(f"Usuário {email} cadastrado no perfil '{perfis_por_id[perfil_id]['nome']}'.")
                            st.rerun()
                        except ValueError as erro:
                            st.error(str(erro))

        if usuarios:
            filtro_usuario = st.text_input("Buscar por nome, e-mail ou perfil", key="filtro_usuarios").strip().lower()
            usuarios_filtrados = [
                u for u in usuarios
                if not filtro_usuario or filtro_usuario in f"{u['nome']} {u['email']} {u.get('perfil_nome') or ''}".lower()
            ]
            st.caption(f"{len(usuarios_filtrados)} conta(s) encontrada(s).")
            cabecalho_tabela = st.columns([2, 2.4, 1, 1.4, 1])
            for coluna, texto in zip(cabecalho_tabela, ["Nome", "E-mail", "Perfil", "Último login", "Ação"]):
                coluna.markdown(f"**{texto}**")
            for conta in usuarios_filtrados:
                col_nome, col_email, col_papel, col_login, col_acao = st.columns([2, 2.4, 1, 1.4, 1])
                col_nome.write(f"{conta['nome']} {conta.get('sobrenome') or ''}".strip())
                col_email.write(conta["email"])
                col_papel.write(conta.get("perfil_nome") or "Sem perfil")
                ultimo_login = conta.get("ultimo_login")
                col_login.write(para_horario_local(ultimo_login).strftime("%d/%m/%Y %H:%M") if ultimo_login else "Nunca acessou")
                if pode_gerenciar_usuarios:
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


PAGINAS_POR_PERMISSAO = {
    "usuario": ("chamados.visualizar_proprios", "pages/1_Portal_Usuario.py", "Portal do usuário", "🏠"),
    "analista": ("chamados.visualizar_fila", "pages/2_Atendimento.py", "Atendimento", "🛠️"),
    "admin": ("administracao.acessar", "pages/3_Administracao.py", "Administração", "🛡️"),
}


def paginas_permitidas_usuario(usuario):
    """Retorna as páginas cuja permissão está ativa no perfil atual do usuário."""
    return {
        chave: dados
        for chave, dados in PAGINAS_POR_PERMISSAO.items()
        if usuario_tem_permissao(usuario["id"], dados[0])
    }


def exibir_navegacao(usuario):
    """Monta links de página conforme as permissões efetivas do perfil."""
    paginas_permitidas = paginas_permitidas_usuario(usuario)
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
            <div class="sidebar-brand__eyebrow">Service desk</div>
            <div class="sidebar-brand__name">Central de Chamados</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f"**{usuario['nome']}**")
        st.divider()
        st.markdown('<div class="sidebar-section">Navegação</div>', unsafe_allow_html=True)

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
        if st.button("Sair", use_container_width=True):
            sair()


def _executar_aplicacao_legacy(pagina_solicitada=None):
    if not schema_pronto():
        st.error("O banco não está atualizado. Um administrador deve executar `python migrations.py upgrade` em uma janela de manutenção.")
        return
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
        paginas_permitidas = paginas_permitidas_usuario(usuario)
        for chave in ("admin", "analista", "usuario"):
            if chave in paginas_permitidas:
                st.switch_page(paginas_permitidas[chave][1])
        st.error("Seu perfil não possui acesso a nenhuma área do sistema. Contate o administrador.")
        return

    exibir_navegacao(usuario)
    paginas_permitidas = paginas_permitidas_usuario(usuario)
    if pagina_solicitada not in paginas_permitidas:
        st.error("Você não tem permissão para acessar esta página.")
        st.page_link("app.py", label="Voltar ao login", icon="🔐")
        return

    if pagina_solicitada == "usuario":
        tela_usuario(usuario)
    elif pagina_solicitada == "analista":
        tela_analista(usuario)
    elif pagina_solicitada == "admin":
        tela_admin(usuario)

    exibir_acoes_sessao(usuario)


# Mantém o ponto de entrada público usado por app.py e pelas páginas multipágina.
executar_aplicacao = _executar_aplicacao_legacy
