"""Feedback da resposta da IA, sempre renderizado na thread do Streamlit."""

import logging
import streamlit as st

from core.ia_monitoramento import FalhaIA, executar_com_progresso


def aguardar_resposta_ia(operacao):
    status = st.status("Preparando sua solicitação…", expanded=True)
    with status:
        detalhe = st.empty()

    def atualizar(etapa, segundos, recebendo, sem_atualizacao):
        status.update(label=etapa, state="running")
        texto = f"Tempo de espera: {segundos}s (limite de 3 minutos). "
        if recebendo:
            texto += f"A IA enviou parte da resposta há {sem_atualizacao}s."
        elif segundos >= 30:
            texto += "Ainda aguardando esta etapa. A primeira resposta pode demorar enquanto a IA carrega."
        else:
            texto += "Aguarde enquanto sua solicitação é analisada."
        if sem_atualizacao >= 30:
            texto += " Esta etapa está demorando mais que o habitual."
        detalhe.caption(texto)

    try:
        resultado = executar_com_progresso(operacao, atualizar)
    except Exception as erro:
        # Registra somente o tipo, sem mensagens, prompts ou respostas privadas.
        logging.getLogger(__name__).warning("Falha ao aguardar IA: %s", type(erro).__name__)
        mensagem = str(erro) if isinstance(erro, FalhaIA) else "Não foi possível concluir a resposta da IA. Tente novamente em instantes."
        status.update(label="Não foi possível concluir a resposta", state="error", expanded=True)
        raise FalhaIA(mensagem) from erro
    status.update(label="Resposta recebida", state="complete", expanded=False)
    return resultado
