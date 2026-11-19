"""Visão executiva sobre chamados já autorizados e filtrados pela tela."""

from collections import Counter
import json
import pandas as pd
import streamlit as st
import sla
from ui.components import indicadores, exibir_tabela_tematica

ENCERRADOS = {"Fechado", "Cancelado"}


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
        st.info("Nenhum chamado neste recorte. Ajuste o período ou os filtros avançados.")
        return resumo

    st.markdown("#### Demanda e gargalos")
    datas = [pd.Timestamp(c["criado_em"]).date() for c in chamados if c.get("criado_em")]
    with st.container(border=True):
        st.markdown("##### Evolução da demanda")
        if datas:
            contagem = pd.Series(Counter(datas), name="Chamados abertos").sort_index()
            contagem.index = pd.to_datetime(contagem.index)
            contagem = contagem.reindex(pd.date_range(contagem.index.min(), contagem.index.max()), fill_value=0)
            st.line_chart(contagem, x_label="Data de abertura", y_label="Chamados")
        st.caption("Aberturas por dia no recorte, incluindo cancelados e dias sem abertura entre os registros. Apoia o planejamento de cobertura.")

    for titulo, valores, legenda in [
        ("Carga por departamento", Counter(departamento_relatorio(c) for c, _ in resumo["ativos"]),
         "Ativos por departamento do solicitante no recorte. Identifique onde concentrar o suporte."),
        ("Distribuição de urgências", Counter(c.get("urgencia") or "Não informada" for c in chamados),
         "Todos os chamados do recorte por urgência registrada. Compare o volume de cada nível."),
    ]:
        with st.container(border=True):
            st.markdown(f"##### {titulo}")
            if valores:
                st.bar_chart(pd.Series(dict(valores.most_common()), name="Chamados"), horizontal=True, sort=False)
            else:
                st.caption("Nenhum chamado ativo neste recorte.")
            st.caption(legenda)

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
