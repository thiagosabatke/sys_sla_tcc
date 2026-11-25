"""Escopos explícitos para a leitura gerencial dos relatórios."""

import streamlit as st
from ui.components import exibir_tabela_tematica

ESCOPO_BACKLOG = "Backlog do período"
ESCOPO_TODOS = "Tudo no período"
ESCOPO_CANCELADOS = "Cancelados do período"
ESTADOS_BACKLOG = ("Novo", "Em Andamento", "Em Espera", "Resolvido")


def filtrar_escopo(chamados, escopo):
    if escopo == ESCOPO_BACKLOG:
        return [c for c in chamados if c.get("status") in ESTADOS_BACKLOG]
    if escopo == ESCOPO_CANCELADOS:
        return [c for c in chamados if c.get("status") == "Cancelado"]
    return list(chamados)


def rotulo_escopo(escopo, detalhe=None):
    st.caption(f"**Escopo: {escopo}**" + (f" · {detalhe}" if detalhe else ""))


def tabela_relatorio(dados, titulo, escopo, detalhe=None):
    st.markdown(f"##### {titulo}")
    rotulo_escopo(escopo, detalhe)
    exibir_tabela_tematica(dados)
