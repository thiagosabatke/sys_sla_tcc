"""Contrato das chaves compartilhadas entre as entradas multipágina."""

ESTADO_INICIAL_SESSAO = {
    "usuario_logado": None,
    "usuario_pendente_2fa": None,
    "login_auditoria_registrada": False,
    "admin_nav": "Dashboards",
    "usuario_nav": "Central de ajuda",
    "analista_nav": "Fila ativa",
    "tela_atual": "login",
    "email_recuperacao": None,
    "aceite_privacidade_validado": False,
    "chamado_selecionado_analista": None,
    "chamado_selecionado_historico": None,
    "chamado_selecionado_cancelado": None,
    "usuario_admin_aberto": None,
    "chamado_aberto_usuario": None,
}


def inicializar_sessao(estado):
    for chave, valor in ESTADO_INICIAL_SESSAO.items():
        estado.setdefault(chave, valor)


def limpar_sessao(estado):
    """Descarta também anexos, exportações e segredos temporários ao sair."""
    estado.clear()
    inicializar_sessao(estado)
