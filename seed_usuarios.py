import logging

from database import criar_tabela_usuarios, criar_usuario, buscar_usuario_por_email, criar_tabela_auditoria
from auth import gerar_hash_senha
from observability import configurar_logging

logger = logging.getLogger(__name__)
 
USUARIOS_TESTE = [
    {"nome": "Thiago Admin", "email": "tsabatke7@gmail.com", "senha": "Thiago123", "papel": "admin"},
]
 
if __name__ == "__main__":
    configurar_logging()
    criar_tabela_usuarios()
    criar_tabela_auditoria()
    for u in USUARIOS_TESTE:
        if buscar_usuario_por_email(u["email"]):
            logger.info("Usuário %s já existe; ignorado.", u["email"])
            continue
        hash_senha = gerar_hash_senha(u["senha"])
        criar_usuario(u["nome"], u["email"], hash_senha, u["papel"])
        logger.info("Usuário %s criado com perfil %s.", u["email"], u["papel"])
