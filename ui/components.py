"""Componentes compartilhados; os dados são fornecidos pela tela chamadora."""

from contextlib import contextmanager
from html import escape
from math import ceil
import pandas as pd
import streamlit as st
import sla

ICONE_URGENCIA = {"Critica": "🚨", "Alta": "🔴", "Media": "🟠", "Baixa": "🟢"}
ICONE_STATUS = {"Novo": "📥", "Em Andamento": "🛠️", "Em Espera": "⏸️",
                "Resolvido": "✅", "Fechado": "🏁", "Cancelado": "⛔"}
CORES_STATUS = {"Novo": "blue", "Em Andamento": "orange", "Em Espera": "violet",
                "Resolvido": "green", "Fechado": "gray", "Cancelado": "red"}
ICONE_SLA = {"Dentro do prazo": "⏱️", "Em risco": "⚠️", "Violado": "🚨",
             "Cumprido": "✅", "Pausado": "⏸️", "Não aplicável": "—"}

ROTULOS = {"Critica": "Crítica", "Media": "Média"}


def rotulo(valor):
    return ROTULOS.get(valor, valor)


def exibir_status_chamado(status):
    st.badge(f"{ICONE_STATUS.get(status, '•')} {status or 'Não informado'}",
             color=CORES_STATUS.get(status, "gray"))


def valor_em_uma_linha(valor):
    """Tipografia local: uma linha, tamanho fluido e texto completo no tooltip."""
    texto = escape(" ".join(str(valor).split()), quote=True)
    st.html(
        f'<div title="{texto}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        'max-width:100%;min-width:0;font-size:clamp(1.125rem,1.8vw,1.5rem);'
        f'font-weight:700;line-height:1.4;">{texto}</div>'
    )


def cor_sla(situacao):
    """Cores semânticas nativas, com contraste adaptado ao tema ativo."""
    return {"Violado": "red", "Em risco": "orange", "Pausado": "violet",
            "Dentro do prazo": "green", "Cumprido": "green"}.get(situacao, "gray")


def indicadores_destaque_chamado(chamado, estado_sla):
    urgencia = chamado.get("urgencia") or "Não informada"
    pior = sla.pior_status(estado_sla)
    itens = [
        ("Criticidade", rotulo(urgencia), "red" if urgencia == "Critica" else "orange" if urgencia == "Alta" else "blue", ICONE_URGENCIA.get(urgencia, "•")),
        ("SLA geral", pior, cor_sla(pior), ICONE_SLA.get(pior, "•")),
        ("Categoria", chamado.get("categoria") or "Não informada", "blue", "🗂️"),
        ("Equipe responsável", chamado.get("equipe_destino") or "Não definida", "violet", "👥"),
    ]
    # As linhas de dois cartões passam a empilhar conforme a largura real do painel,
    # inclusive com a barra lateral aberta, sem comprimir os valores em quatro colunas.
    for inicio in range(0, len(itens), 2):
        with st.container(horizontal=True, gap="small"):
            for nome, valor, cor, icone in itens[inicio:inicio + 2]:
                with st.container(border=True, gap="small", width=260):
                    st.badge(f"{icone} {nome}", color=cor)
                    valor_em_uma_linha(valor)


@contextmanager
def painel_acesso():
    """Largura confortável sem colunas vazias comprimindo formulários no celular."""
    with st.container(horizontal=True, horizontal_alignment="center"):
        with st.container(width=560):
            st.caption("CENTRAL DE CHAMADOS · ACESSO SEGURO")
            yield


def notificar(mensagem, icone="✅"):
    st.session_state["ui_notificacao"] = (mensagem, icone)


def exibir_notificacao():
    aviso = st.session_state.pop("ui_notificacao", None)
    if aviso:
        st.toast(aviso[0], icon=aviso[1])


def recarregar_com_feedback(mensagem):
    notificar(mensagem)
    st.rerun()


def limpar_filtros(chaves):
    for chave in chaves:
        st.session_state.pop(chave, None)


def paginar_registros(registros, chave, tamanho=5):
    """Paginação visual sobre o recorte já autorizado, sem outra consulta ao banco."""
    paginas = max(1, ceil(len(registros) / tamanho))
    if chave in st.session_state:
        atual = st.session_state[chave]
        limitado = min(max(1, atual), paginas)
        if limitado != atual:
            st.session_state[chave] = limitado
    if paginas > 1:
        pagina = st.number_input("Página da lista", min_value=1, max_value=paginas,
                                 value=1, step=1, key=chave)
        st.caption(f"Página {pagina} de {paginas} · {len(registros)} registros no recorte")
    else:
        pagina = 1
    inicio = (pagina - 1) * tamanho
    return registros[inicio:inicio + tamanho]


def tabela_usuarios(usuarios, pode_editar, ao_abrir, converter_data=lambda valor: valor):
    if not usuarios:
        st.info("Nenhuma conta corresponde à busca. Tente outro nome, e-mail ou perfil.")
        return
    dados = pd.DataFrame([{
        "Nome": f"{u['nome']} {u.get('sobrenome') or ''}".strip(), "E-mail": u["email"],
        "Perfil": u.get("perfil_nome") or "Sem perfil", "Departamento": u.get("departamento") or "Não informado",
        "Último acesso": converter_data(u.get("ultimo_login_em") or u.get("ultimo_login")),
    } for u in usuarios])
    dados["Último acesso"] = pd.to_datetime(dados["Último acesso"], errors="coerce")
    evento = st.dataframe(dados, hide_index=True, width="stretch", key="tabela_usuarios_admin",
                         on_select="rerun" if pode_editar else "ignore", selection_mode="single-row",
                         column_config={"Último acesso": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
    if pode_editar:
        st.caption("Selecione uma pessoa na tabela para abrir seu perfil.")
        linhas = evento.selection.rows
        if linhas:
            conta = usuarios[linhas[0]]
            st.button(f"Abrir perfil de {conta['nome']}", type="primary",
                      key=f"abrir_usuario_{conta['id']}", on_click=ao_abrir, args=(conta["id"],))


def cabecalho(titulo, subtitulo, icone="🎫"):
    exibir_notificacao()
    st.title(f"{icone} {titulo}")
    st.caption(subtitulo)


def exibir_tabela_tematica(dados):
    if len(dados) == 0:
        st.info("Nenhum registro encontrado.")
        return
    st.dataframe(dados, width="stretch", hide_index=True)


def indicadores(itens):
    """Cada item contém rótulo, valor e definição; no máximo quatro por linha."""
    for inicio in range(0, len(itens), 4):
        grupo = itens[inicio:inicio + 4]
        for coluna, (rotulo, valor, definicao) in zip(st.columns(len(grupo)), grupo):
            with coluna, st.container(border=True):
                st.metric(rotulo, valor, help=definicao)
                st.caption(definicao)


def exibir_cartao_chamado(chamado, estado_sla, contexto, selecionado, chave_botao):
    with st.container(border=True):
        st.markdown(f"**#{chamado['id']} · {chamado['titulo']}**")
        status, urgencia = chamado.get("status"), chamado.get("urgencia")
        with st.container(horizontal=True, gap="small"):
            exibir_status_chamado(status)
            st.badge(f"{ICONE_URGENCIA.get(urgencia, '•')} {rotulo(urgencia) or 'Não informada'}",
                     color="red" if urgencia == "Critica" else "orange" if urgencia == "Alta" else "gray")
        for etapa, nome in (("resposta", "Resposta"), ("resolucao", "Resolução")):
            metrica = estado_sla[etapa]
            situacao = metrica["status"]
            prazo = sla.formatar_data(metrica["prazo_efetivo"])
            st.caption(f"{ICONE_SLA.get(situacao, '•')} {nome}: {situacao} · {prazo}")
        st.caption(contexto)
        return st.button(
            "Chamado selecionado" if selecionado else "Ver detalhes",
            key=chave_botao, type="primary" if selecionado else "secondary",
            width="stretch", disabled=selecionado,
        )


def painel_metricas_chamado(chamado, estado_sla=None):
    estado_sla = estado_sla or sla.status_sla(chamado)
    urgencia = chamado.get("urgencia") or "Não informada"
    pior = sla.pior_status(estado_sla)
    # Texto nativo também pode ser usado por chamadas legadas de st.markdown.
    return (f"**{ICONE_URGENCIA.get(urgencia, '•')} Urgência: {urgencia}**  \n"
            f"{ICONE_SLA.get(pior, '•')} SLA: {pior} · "
            f"Equipe: {chamado.get('equipe_destino') or 'Não definida'}")


def bloco_sla_detalhe(chamado, estado_sla):
    with st.container(horizontal=True, gap="small"):
        for etapa, nome in (("resposta", "Primeira resposta"), ("resolucao", "Resolução")):
            metrica = estado_sla[etapa]
            situacao = metrica["status"]
            with st.container(border=True, width=260):
                st.markdown(f"**{nome}**")
                st.badge(f"{ICONE_SLA.get(situacao, '•')} {situacao}", color=cor_sla(situacao))
                st.metric("Prazo vigente", sla.formatar_data(metrica["prazo_efetivo"]),
                          help="Prazo vigente calculado conforme o calendário de atendimento e as pausas deste chamado.")
                if metrica["minutos_restantes"] is not None:
                    st.markdown(f"**{sla.formatar_tempo_restante(metrica['minutos_restantes']).capitalize()}**")
                st.caption("Tempo de atendimento conforme a configuração deste chamado.")
    if chamado.get("pausado_em"):
        st.info("⏸ Em espera: aguardando retorno do solicitante. O SLA está pausado durante a espera.")


def exibir_grafico_barras(dados, titulo, eixo_x, eixo_y, cor=None):
    """Gráfico nativo: paleta, fundo e textos acompanham Light e Dark."""
    st.markdown(f"##### {titulo}")
    if dados.empty or eixo_x not in dados or eixo_y not in dados:
        st.info("Ainda não há dados suficientes para este gráfico.")
        return
    st.bar_chart(dados, x=eixo_x, y=eixo_y, horizontal=True, sort=False,
                 x_label=eixo_y, y_label=eixo_x)
