"""Busca, filtros e listas de atendimento, sem alterar as regras dos chamados."""

from math import ceil
import streamlit as st
import sla
from ui.components import limpar_filtros, rotulo, cor_sla, ICONE_SLA, ICONE_URGENCIA, exibir_status_chamado

CHAVES_FILTROS_FILA = ("busca_chamado_ativa", "filtro_status_ativa", "filtro_urgencia_ativa",
                      "filtro_categoria_ativa", "filtro_departamento_ativa", "filtro_analista_ativa",
                      "filtro_sla_ativa", "somente_meus_ativa", "pagina_fila_ativa")


def fechar_detalhe_historico():
    st.session_state.chamado_selecionado_historico = None


def reiniciar_consulta_historico():
    st.session_state.pagina_historico = 1
    fechar_detalhe_historico()


def _ir_para_pagina_historico(pagina):
    st.session_state.pagina_historico = pagina
    fechar_detalhe_historico()


def paginar_historico(registros, tamanho=5):
    """Renderiza o rodapé e retorna a página atual da consulta completa."""
    paginas = max(1, ceil(len(registros) / tamanho))
    pagina = min(max(1, st.session_state.get("pagina_historico", 1)), paginas)
    if st.session_state.get("pagina_historico") != pagina:
        st.session_state.pagina_historico = pagina
    inicio = (pagina - 1) * tamanho
    st.caption(f"Mostrando {inicio + 1 if registros else 0}–{min(inicio + tamanho, len(registros))} "
               f"de {len(registros)} chamados · Página {pagina} de {paginas}")
    anterior, seletor, proxima = st.columns([1, 1, 1], vertical_alignment="bottom")
    anterior.button("Anterior", key="historico_pagina_anterior", disabled=pagina == 1,
                    on_click=_ir_para_pagina_historico, args=(pagina - 1,), width="stretch")
    seletor.number_input("Página", min_value=1, max_value=paginas, step=1,
                         key="pagina_historico", disabled=paginas == 1,
                         on_change=fechar_detalhe_historico)
    proxima.button("Próxima", key="historico_pagina_proxima", disabled=pagina == paginas,
                   on_click=_ir_para_pagina_historico, args=(pagina + 1,), width="stretch")
    return registros[inicio:inicio + tamanho]


def cartao_historico_compacto(chamado, selecionado):
    """Resumo do registro fechado; descrição, SLA e conversa ficam no detalhe."""
    titulo = " ".join((chamado.get("titulo") or "Sem título").split())
    resumo = titulo if len(titulo) <= 85 else titulo[:82].rstrip() + "…"
    criado = chamado.get("criado_em")
    resolvido = chamado.get("resolvido_em")
    abertura = criado.strftime("%d/%m/%Y") if criado else "—"
    resolucao = resolvido.strftime("%d/%m/%Y") if resolvido else "—"
    with st.container(border=True, gap="small"):
        texto, acao = st.columns([5, 1.4], vertical_alignment="center")
        with texto:
            st.markdown(f"**#{chamado['id']} · {resumo}**")
            st.caption(f"Aberto por: {chamado.get('nome_usuario') or 'Não informado'} · "
                       f"Responsável: {chamado.get('nome_analista') or 'Sem atribuição'}")
            st.caption(f"{chamado.get('categoria') or 'Não informada'} · "
                       f"Urgência: {rotulo(chamado.get('urgencia')) or 'Não informada'} · "
                       f"Abertura: {abertura} · Resolução: {resolucao}")
        return acao.button("Selecionado" if selecionado else "Ver detalhes",
                           key=f"hist_{chamado['id']}", disabled=selecionado,
                           type="primary" if selecionado else "secondary", width="stretch",
                           help=f"Consultar o registro completo de #{chamado['id']} · {titulo}")


def filtros_fila(chamados):
    with st.container(border=True):
        busca_col, meus_col = st.columns([3, 1], vertical_alignment="bottom")
        with busca_col:
            busca = st.text_input("Buscar chamado", placeholder="Número, título, descrição ou solicitante",
                                  key="busca_chamado_ativa").strip().lower().lstrip("#")
        with meus_col:
            meus = st.toggle("Atribuídos a mim", key="somente_meus_ativa",
                             help="Exibe somente chamados em que você é o analista responsável.")
        if meus:
            # O atalho principal prevalece sobre uma seleção anterior de outro analista.
            if st.session_state.get("filtro_analista_ativa", "Todos") != "Todos":
                st.session_state.filtro_analista_ativa = "Todos"
            st.info("Minha fila: somente os chamados atribuídos a você. Os demais filtros continuam aplicados.")
        status = st.pills("Estado do chamado", ["Novo", "Em Andamento", "Em Espera", "Resolvido"],
                          selection_mode="multi", key="filtro_status_ativa")
        with st.expander("Filtros avançados", expanded=False):
            urgencia = st.multiselect("Urgência", ["Critica", "Alta", "Media", "Baixa"], format_func=rotulo, key="filtro_urgencia_ativa")
            categoria = st.selectbox("Categoria", ["Todas"] + sorted({c.get("categoria") or "Outros" for c in chamados}), key="filtro_categoria_ativa")
            departamento = st.selectbox("Departamento", ["Todos"] + sorted({c.get("departamento_usuario") or "Não informado" for c in chamados}), key="filtro_departamento_ativa")
            analista = st.selectbox("Analista", ["Todos"] + sorted({c.get("nome_analista") or "Sem atribuição" for c in chamados}), key="filtro_analista_ativa", disabled=meus,
                                   help="Desative Atribuídos a mim para escolher outro analista.")
            situacao = st.multiselect("Situação de SLA", ["Violado", "Em risco", "Dentro do prazo", "Pausado"], key="filtro_sla_ativa")
        st.button("Limpar filtros", key="limpar_filtros_fila", on_click=limpar_filtros, args=(CHAVES_FILTROS_FILA,))
    return {"busca": busca, "status": status, "urgencia": urgencia, "categoria": categoria,
            "departamento": departamento, "analista": analista, "sla": situacao, "meus": meus}


def filtrar_fila(chamados, filtros, usuario_id):
    def corresponde(c):
        return (
            (not filtros["status"] or c["status"] in filtros["status"])
            and (not filtros["urgencia"] or c.get("urgencia") in filtros["urgencia"])
            and (not filtros["meus"] or c.get("analista_id") == usuario_id)
            and (not filtros["sla"] or sla.pior_status(sla.status_sla(c)) in filtros["sla"])
            and (filtros["categoria"] == "Todas" or (c.get("categoria") or "Outros") == filtros["categoria"])
            and (filtros["departamento"] == "Todos" or (c.get("departamento_usuario") or "Não informado") == filtros["departamento"])
            and (filtros["meus"] or filtros["analista"] == "Todos" or (c.get("nome_analista") or "Sem atribuição") == filtros["analista"])
            and (not filtros["busca"] or filtros["busca"] in " ".join(str(c.get(campo) or "") for campo in ("id", "titulo", "descricao", "nome_usuario")).lower())
        )
    return [c for c in chamados if corresponde(c)]


def resumo_filtros(filtros):
    ativos = list(filtros["status"] or []) + list(filtros["urgencia"] or []) + list(filtros["sla"] or [])
    for campo, todos in (("categoria", "Todas"), ("departamento", "Todos"), ("analista", "Todos")):
        if filtros[campo] != todos:
            ativos.append(filtros[campo])
    if filtros["meus"]:
        ativos.append("Atribuídos a mim")
    return " · ".join(ativos)


def cartao_fila_compacto(chamado, estado_sla, contexto, selecionado, chave_botao):
    """Resumo denso para a coluna da fila; os demais dados ficam no detalhe."""
    with st.container(border=True, gap=None):
        titulo = chamado["titulo"]
        resumo = titulo if len(titulo) <= 64 else titulo[:61].rstrip() + "…"
        st.markdown(f"**#{chamado['id']} · {resumo}**")
        urgencia = chamado.get("urgencia")
        pior = sla.pior_status(estado_sla)
        with st.container(horizontal=True, gap="small"):
            exibir_status_chamado(chamado.get("status"))
            st.badge(f"{ICONE_URGENCIA.get(urgencia, '•')} {rotulo(urgencia) or 'Não informada'}",
                     color="red" if urgencia == "Critica" else "orange" if urgencia == "Alta" else "gray")
            st.badge(f"{ICONE_SLA.get(pior, '•')} SLA: {pior}", color=cor_sla(pior))
        prazos = []
        for etapa, nome in (("resposta", "Resposta"), ("resolucao", "Resolução")):
            metrica = estado_sla[etapa]
            prazos.append(f"**{nome}:** {ICONE_SLA.get(metrica['status'], '•')} {sla.formatar_data(metrica['prazo_efetivo'])}")
        st.markdown(" · ".join(prazos))
        st.caption(contexto)
        return st.button("Chamado selecionado" if selecionado else "Ver detalhes",
                         key=chave_botao, type="primary" if selecionado else "secondary",
                         width="stretch", disabled=selecionado, help=f"#{chamado['id']} · {titulo}")
