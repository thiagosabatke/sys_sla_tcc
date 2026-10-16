
import streamlit as st

st.set_page_config(page_title="Sistema Inteligente de Chamados", layout="wide", initial_sidebar_state="expanded")

from pages._telas import executar_aplicacao


executar_aplicacao()
