"""Rotas existentes e escolha inicial por permissões efetivas."""

PAGINAS_POR_PERMISSAO = {
    "usuario": ("chamados.visualizar_proprios", "pages/1_Portal_Usuario.py", "Portal do usuário", "🏠"),
    "analista": ("chamados.visualizar_fila", "pages/2_Atendimento.py", "Atendimento", "🛠️"),
    "admin": ("administracao.acessar", "pages/3_Administracao.py", "Administração", "🛡️"),
}


def paginas_autorizadas(tem_permissao):
    return {chave: dados for chave, dados in PAGINAS_POR_PERMISSAO.items()
            if tem_permissao(dados[0])}


def destino_inicial(tem_permissao):
    """Não concede acesso operacional como consequência de acesso a relatórios."""
    paginas = paginas_autorizadas(tem_permissao)
    if "admin" in paginas and tem_permissao("relatorios.visualizar"):
        return "admin", "Dashboards"
    if "analista" in paginas:
        return "analista", "Fila ativa"
    if "usuario" in paginas:
        return "usuario", "Central de ajuda"
    return next(iter(paginas), None), None
