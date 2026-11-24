"""Visão executiva sobre chamados já autorizados e filtrados pela tela."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
import pandas as pd
import streamlit as st
import sla
from ui.components import indicadores, exibir_tabela_tematica, limpar_filtros, rotulo
from ui.charts import resumir_por_situacao, resumir_evolucao_por_situacao, exibir_grafico_situacao

ENCERRADOS = {"Fechado", "Cancelado"}
PERIODOS_ABERTURA = {"Último mês": 30, "Última semana": 7, "Último dia": 1}
CHAVES_FILTROS_DASHBOARD = (
    "dashboard_periodo_abertura", "dashboard_intervalo_datas", "dashboard_data_especifica", "dashboard_categoria",
    "dashboard_urgencia", "dashboard_situacao",
)


def intervalo_abertura(periodo, agora, datas=None):
    """Janelas móveis, intervalo de dias completos ou histórico até agora, em hora local."""
    if periodo == "Até agora":
        return None, agora
    if periodo == "Intervalo de datas":
        if not isinstance(datas, (tuple, list)) or len(datas) != 2:
            raise ValueError("Selecione a data inicial e a data final para atualizar os indicadores.")
        if datas[0] > datas[1]:
            raise ValueError("A data final deve ser igual ou posterior à data inicial.")
        return (datetime.combine(datas[0], time.min),
                datetime.combine(datas[1], time.max))
    return agora - timedelta(days=PERIODOS_ABERTURA[periodo]), agora


def filtrar_chamados_dashboard(chamados, inicio, fim, categoria="Todas",
                              urgencia="Todas", situacao="Todas"):
    # listar_chamados já entrega os datetimes na hora civil de São Paulo.
    return [c for c in chamados
            if c.get("criado_em") and (inicio is None or inicio <= c["criado_em"]) and c["criado_em"] <= fim
            and (categoria == "Todas" or (c.get("categoria") or "Outros") == categoria)
            and (urgencia == "Todas" or (c.get("urgencia") or "Não informada") == urgencia)
            and (situacao == "Todas" or c.get("status") == situacao)]


def filtros_dashboard(chamados):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
    datas_padrao = (agora.date() - timedelta(days=29), agora.date())
    if st.session_state.get("dashboard_periodo_abertura") == "Data específica":
        st.session_state.dashboard_periodo_abertura = "Intervalo de datas"
        data_anterior = st.session_state.get("dashboard_data_especifica")
        if data_anterior is not None and "dashboard_intervalo_datas" not in st.session_state:
            datas_padrao = (data_anterior, data_anterior)
    with st.container(border=True):
        periodo_col, data_col = st.columns(2)
        periodo = periodo_col.selectbox(
            "Período de abertura", [*PERIODOS_ABERTURA, "Intervalo de datas", "Até agora"],
            key="dashboard_periodo_abertura",
            help="Último mês: 30 dias; última semana: 7 dias; último dia: 24 horas. "
                 "Até agora: todo o histórico até o momento atual. Os demais filtros continuam aplicados.",
        )
        datas = None
        if periodo == "Intervalo de datas":
            datas = data_col.date_input(
                "Data inicial e final", value=datas_padrao,
                max_value=agora.date(), format="DD/MM/YYYY", key="dashboard_intervalo_datas",
                help="Inclui os dois dias completos. Para consultar um único dia, escolha a mesma data duas vezes.",
            )
        categoria_col, urgencia_col, situacao_col = st.columns(3)
        # As opções usam a amostra completa para preservar o filtro ao trocar o período.
        categorias = ["Todas"] + sorted({c.get("categoria") or "Outros" for c in chamados})
        if st.session_state.get("dashboard_categoria", "Todas") not in categorias:
            st.session_state.dashboard_categoria = "Todas"
        categoria = categoria_col.selectbox("Categoria", categorias, key="dashboard_categoria")
        urgencia = urgencia_col.selectbox(
            "Urgência", ["Todas", "Critica", "Alta", "Media", "Baixa", "Não informada"],
            format_func=rotulo, key="dashboard_urgencia",
        )
        situacao = situacao_col.selectbox(
            "Situação", ["Todas", "Novo", "Em Andamento", "Em Espera", "Resolvido", "Fechado", "Cancelado"],
            key="dashboard_situacao",
        )
        st.button("Limpar filtros", key="limpar_filtros_dashboard", on_click=limpar_filtros,
                  args=(CHAVES_FILTROS_DASHBOARD,))

    try:
        inicio, fim = intervalo_abertura(periodo, agora, datas)
    except ValueError as erro:
        st.info(str(erro))
        return None
    filtrados = filtrar_chamados_dashboard(chamados, inicio, fim, categoria, urgencia, situacao)
    if periodo == "Até agora":
        janela = f"Todo o histórico até {fim:%d/%m/%Y %H:%M}"
    elif periodo == "Intervalo de datas":
        janela = f"{datas[0]:%d/%m/%Y} a {datas[1]:%d/%m/%Y} · Dias completos"
    else:
        janela = f"{inicio:%d/%m/%Y %H:%M} a {fim:%d/%m/%Y %H:%M}"
    st.caption(f"{janela} (São Paulo) · Categoria: {categoria} · Urgência: {rotulo(urgencia)} · "
               f"Situação: {situacao} · {len(filtrados)} chamado(s)")
    return filtrados


def duracao_resolucao_horas(chamado):
    if pd.isna(chamado.get("criado_em")) or pd.isna(chamado.get("resolvido_em")):
        return None
    configuracao = chamado.get("sla_configuracao")
    if not isinstance(configuracao, (dict, str)):
        configuracao = {"usar_horario_comercial": False}
    minutos = sla.minutos_uteis_entre(chamado["criado_em"], chamado["resolvido_em"],
                                    configuracao)
    return max(0, minutos - float(chamado.get("tempo_pausado_min") or 0)) / 60


def departamento_relatorio(chamado):
    """Mantém o departamento registrado e o rótulo das demonstrações existentes."""
    departamento = str(chamado.get("departamento_usuario") or chamado.get("departamento") or "").strip()
    if departamento:
        return departamento
    metadados = chamado.get("metadados_ia")
    if isinstance(metadados, str):
        try:
            metadados = json.loads(metadados)
        except json.JSONDecodeError:
            metadados = None
    if isinstance(metadados, dict):
        departamento_demo = str(metadados.get("departamento_demo") or "").strip()
        if departamento_demo:
            return departamento_demo
    return "Não informado"


def resumir_operacao(chamados):
    """Agrega avaliações de sla.py, sem reconstruir prazos nem transições."""
    avaliados = [(chamado, sla.status_sla(chamado)) for chamado in chamados]
    ativos = [(c, e) for c, e in avaliados if c.get("status") not in ENCERRADOS]
    violados = sum(sla.pior_status(e) == "Violado" for _, e in ativos)
    risco = sum(sla.pior_status(e) == "Em risco" for _, e in ativos)
    # Só uma amostra com os dois marcos e prazos permite medir o SLA completo.
    concluidos = [(c, e) for c, e in avaliados if c.get("status") != "Cancelado"
                  and c.get("primeira_resposta_em") and c.get("resolvido_em")
                  and c.get("prazo_resposta") and c.get("prazo_resolucao")]
    cumpridos = sum(all(e[k]["status"] == "Cumprido" for k in ("resposta", "resolucao"))
                    for _, e in concluidos)
    excecoes = [(c, e) for c, e in ativos if sla.pior_status(e) in {"Violado", "Em risco"}
                or c.get("urgencia") in {"Critica", "Alta"}]
    urgencias = {"Critica": 0, "Alta": 1, "Media": 2, "Baixa": 3}
    niveis = {"Violado": 0, "Em risco": 1}
    excecoes.sort(key=lambda item: (niveis.get(sla.pior_status(item[1]), 2),
                                    urgencias.get(item[0].get("urgencia"), 4), item[0]["id"]))
    return {"avaliados": avaliados, "ativos": ativos, "violados": violados,
            "risco": risco, "amostra": len(concluidos), "cumpridos": cumpridos,
            "taxa": cumpridos / len(concluidos) * 100 if concluidos else None,
            "excecoes": excecoes}


def resumir_carga_departamentos(chamados):
    """Cada chamado do recorte entra uma vez, conforme seu estado atual."""
    return resumir_por_situacao(chamados, "Departamento", departamento_relatorio).to_dict("records")


def renderizar_dashboard(chamados):
    st.subheader("Visão executiva")
    st.caption("Recorte por data de abertura e escopo selecionados acima. "
               "Os estados e SLAs refletem a situação atual desses chamados, em America/Sao_Paulo.")
    resumo = resumir_operacao(chamados)
    taxa = f"{resumo['taxa']:.1f}%" if resumo["taxa"] is not None else "Sem amostra"
    indicadores([
        ("Chamados ativos", len(resumo["ativos"]), "Do recorte: todos exceto fechados e cancelados. Dimensiona a fila pendente."),
        ("SLA violado", resumo["violados"], "Ativos com resposta ou resolução violada; cada chamado conta uma vez. Priorize a atuação."),
        ("Em risco", resumo["risco"], "Ativos em risco segundo as metas e o limiar configurados, sem violação. Antecipe o atendimento."),
        ("Cumprimento do SLA", taxa, f"Resposta e resolução cumpridas em {resumo['cumpridos']}/{resumo['amostra']} chamados com ambos os marcos e prazos. Cancelados excluídos."),
    ])
    if not chamados:
        st.info("Nenhum chamado neste recorte. Ajuste o período, a categoria, a urgência ou a situação.")
        return resumo

    st.markdown("#### Demanda e gargalos")
    with st.container(border=True):
        exibir_grafico_situacao(resumir_evolucao_por_situacao(chamados), "Data", "Evolução da demanda", horizontal=False)
        st.caption("Chamados por dia de abertura no recorte, separados pela situação atual: ativos, cancelados e fechados. "
                   "Inclui dias sem abertura entre os registros. Apoia o planejamento de cobertura.")

    with st.container(border=True):
        carga = resumir_por_situacao(chamados, "Departamento", departamento_relatorio)
        exibir_grafico_situacao(carga, "Departamento", "Carga por departamento")
        st.caption("Total de chamados abertos no período e nos filtros selecionados, por departamento do solicitante. "
                   "Cada barra soma ativos, cancelados e fechados. Ativos incluem novos, em andamento, em espera e resolvidos. "
                   "Compare o volume de solicitações de cada setor e a parcela que ainda está na fila.")

    with st.container(border=True):
        valores = resumir_por_situacao(chamados, "Urgência", lambda c: rotulo(c.get("urgencia")) or "Não informada")
        exibir_grafico_situacao(valores, "Urgência", "Distribuição de urgências")
        st.caption("Todos os chamados do recorte por urgência, separados em ativos, cancelados e fechados. Compare o volume de cada nível.")

    with st.container(border=True):
        st.markdown("##### Primeira resposta e resolução")
        linhas = [{"Etapa": nome, "Situação": e[chave]["status"]}
                  for c, e in resumo["avaliados"] if c.get("status") != "Cancelado"
                  for chave, nome in (("resposta", "Primeira resposta"), ("resolucao", "Resolução"))]
        if linhas:
            tabela = pd.crosstab(pd.DataFrame(linhas)["Etapa"], pd.DataFrame(linhas)["Situação"])
            exibir_tabela_tematica(tabela.reset_index())
        st.caption("Contagem por etapa conforme as metas configuradas no mesmo recorte, sem cancelados. "
                   "Estados em andamento não equivalem a metas cumpridas; compare as duas etapas para localizar atrasos.")

    st.markdown("#### Chamados que precisam de atenção")
    st.caption("Ativos com violação, risco ou urgência alta/crítica no recorte. "
               "Ordenados por situação do SLA, urgência e número; prazos vigentes incluem os ajustes de pausa.")
    linhas = []
    for c, e in resumo["excecoes"]:
        linhas.append({"Chamado": f"#{c['id']}", "Título": c.get("titulo"),
                       "Estado": c.get("status"), "Urgência": c.get("urgencia"),
                       "Responsável": c.get("nome_analista") or "Sem atribuição",
                       "Resposta": e["resposta"]["status"], "Prazo de resposta": sla.formatar_data(e["resposta"]["prazo_efetivo"]),
                       "Resolução": e["resolucao"]["status"], "Prazo de resolução": sla.formatar_data(e["resolucao"]["prazo_efetivo"])})
    if linhas:
        exibir_tabela_tematica(pd.DataFrame(linhas))
    else:
        st.success("Nenhuma exceção de SLA ou urgência alta/crítica entre os ativos deste recorte.")
    return resumo
