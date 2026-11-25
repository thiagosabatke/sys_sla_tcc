"""Contagens de chamados por situação, compartilhadas pelos dashboards."""

import pandas as pd
import streamlit as st
from ui.report_scope import ESCOPO_BACKLOG, ESCOPO_TODOS, ESCOPO_CANCELADOS, rotulo_escopo

SITUACOES_CHAMADOS = ("Ativos", "Cancelados", "Fechados")


def grupo_situacao(chamado):
    return {"Cancelado": "Cancelados", "Fechado": "Fechados"}.get(chamado.get("status"), "Ativos")


def resumir_por_situacao(chamados, dimensao, obter_valor, grupos=(), ordenar_por_total=True):
    """Conta cada chamado uma vez e mantém as três séries, inclusive quando zeradas."""
    contagens = {valor: {dimensao: valor, **dict.fromkeys(SITUACOES_CHAMADOS, 0)} for valor in grupos}
    for chamado in chamados:
        valor = obter_valor(chamado)
        linha = contagens.setdefault(valor, {dimensao: valor, **dict.fromkeys(SITUACOES_CHAMADOS, 0)})
        linha[grupo_situacao(chamado)] += 1
    linhas = list(contagens.values())
    if ordenar_por_total:
        linhas.sort(key=lambda linha: (-sum(linha[s] for s in SITUACOES_CHAMADOS), str(linha[dimensao])))
    else:
        linhas.sort(key=lambda linha: linha[dimensao])
    return pd.DataFrame(linhas, columns=[dimensao, *SITUACOES_CHAMADOS])


def resumir_evolucao_por_situacao(chamados):
    validos = [c for c in chamados if c.get("criado_em") is not None and not pd.isna(c["criado_em"])]
    dados = resumir_por_situacao(validos, "Data", lambda c: pd.Timestamp(c["criado_em"]).normalize(),
                                ordenar_por_total=False)
    if dados.empty:
        return dados
    dados = dados.set_index("Data")
    return dados.reindex(pd.date_range(dados.index.min(), dados.index.max()), fill_value=0).rename_axis("Data").reset_index()


def exibir_grafico_situacao(dados, dimensao, titulo=None, horizontal=True, escopo=ESCOPO_TODOS):
    if titulo:
        st.markdown(f"##### {titulo}")
    rotulo_escopo(escopo)
    if dados.empty:
        st.info("Nenhum chamado neste recorte para exibir no gráfico.")
        return
    series = (["Ativos"] if escopo == ESCOPO_BACKLOG else ["Cancelados"]
              if escopo == ESCOPO_CANCELADOS else list(SITUACOES_CHAMADOS))
    st.bar_chart(dados, x=dimensao, y=series,
                 horizontal=horizontal, stack=True, sort=False,
                 x_label=dimensao if horizontal else "Data de abertura",
                 y_label="Chamados")
