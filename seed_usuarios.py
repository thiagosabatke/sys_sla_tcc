import logging
import os

from database import (
    criar_tabelas_rbac, criar_tabela_usuarios, migrar_tabela_usuarios, migrar_usuarios_rbac,
    criar_usuario, buscar_usuario_por_email, criar_tabela_auditoria,
)
from auth import gerar_hash_senha
from observability import configurar_logging

logger = logging.getLogger(__name__)
 
if __name__ == "__main__":
    configurar_logging()
    nome = os.getenv("SEED_ADMIN_NOME")
    email = os.getenv("SEED_ADMIN_EMAIL")
    senha = os.getenv("SEED_ADMIN_SENHA")
    if not all((nome, email, senha)):
        raise SystemExit("Defina SEED_ADMIN_NOME, SEED_ADMIN_EMAIL e SEED_ADMIN_SENHA para criar uma conta inicial.")
    criar_tabelas_rbac()
    criar_tabela_usuarios()
    migrar_tabela_usuarios()
    migrar_usuarios_rbac()
    criar_tabela_auditoria()
    if buscar_usuario_por_email(email):
        logger.info("Conta inicial já existe; ignorada.")
    else:
        criar_usuario(nome, email, gerar_hash_senha(senha), "admin")
        logger.info("Conta inicial de administrador criada.")
