from database import criar_tabela_usuarios, criar_usuario, buscar_usuario_por_email
from auth import gerar_hash_senha
 
USUARIOS_TESTE = [
    {"nome": "Usuário Teste", "email": "usuario@teste.com", "senha": "usuario123", "papel": "usuario"},
    {"nome": "Analista Teste", "email": "analista@teste.com", "senha": "analista123", "papel": "analista"},
    {"nome": "Admin Teste", "email": "admin@teste.com", "senha": "admin123", "papel": "admin"},
]
 
if __name__ == "__main__":
    criar_tabela_usuarios()
    for u in USUARIOS_TESTE:
        if buscar_usuario_por_email(u["email"]):
            print(f"Usuário {u['email']} já existe, pulando.")
            continue
        hash_senha = gerar_hash_senha(u["senha"])
        criar_usuario(u["nome"], u["email"], hash_senha, u["papel"])
        print(f"Criado: {u['email']} / senha: {u['senha']} / papel: {u['papel']}")
 