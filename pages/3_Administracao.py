import streamlit as st

st.set_page_config(page_title="Administração", layout="wide")

from pages._telas import executar_aplicacao


executar_aplicacao("admin")
