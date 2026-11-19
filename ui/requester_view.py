"""Orientação do solicitante; não cria chamados nem consulta permissões."""

import streamlit as st


def selecionar_secao_portal(secao):
    st.session_state.usuario_nav = secao


def acompanhar_chamado(chamado_id):
    st.session_state.usuario_nav = "Meus chamados ativos"
    st.session_state.chamado_aberto_usuario = chamado_id


def boas_vindas(pode_usar_ia):
    with st.container(border=True):
        st.subheader("Como podemos ajudar?")
        if pode_usar_ia:
            st.write("Descreva o que aconteceu com suas palavras. O assistente pode orientar você e, se necessário, preparar um chamado para sua revisão.")
            st.caption("O chamado só é registrado depois que você revisar os dados e confirmar a abertura.")
            st.button("Descrever um problema ou tirar uma dúvida", type="primary",
                      on_click=selecionar_secao_portal, args=("Abrir novo chamado",),
                      width="stretch")
        else:
            st.write("Encontre orientações na central de ajuda ou acompanhe suas solicitações pelo menu do portal.")
    st.markdown("#### Orientações da central de ajuda")


def contexto_conversa(resultado):
    st.subheader("Converse com o assistente")
    estado = (resultado or {}).get("status")
    if estado == "registrado":
        st.caption("Chamado registrado. Acompanhe o atendimento em Meus chamados ativos.")
    elif estado == "aguardando_confirmacao":
        st.caption("Revisão dos dados: falta sua confirmação para registrar o chamado.")
    elif estado == "solucao_sugerida":
        st.caption("Orientação em andamento. Informe se o procedimento resolveu o problema.")
    elif estado == "resolvido_pelo_usuario":
        st.caption("Conversa concluída sem abrir chamado.")
    else:
        st.caption("O assistente está orientando ou coletando informações. Nenhum chamado foi aberto nesta conversa.")
