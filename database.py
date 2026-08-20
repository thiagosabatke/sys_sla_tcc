import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def conectar():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def criar_tabela():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chamados (
            id INT AUTO_INCREMENT PRIMARY KEY,
            titulo VARCHAR(255) NOT NULL,
            descricao TEXT NOT NULL,
            categoria VARCHAR(100),
            urgencia VARCHAR(50),
            sla_resposta VARCHAR(50),
            sla_resolucao VARCHAR(50),
            equipe_destino VARCHAR(100),
            titulo_resumido VARCHAR(255),
            descricao_padronizada TEXT,
            confiabilidade VARCHAR(50),
            usuario_id INT,
            analista_id INT,
            status VARCHAR(50) DEFAULT 'Novo',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Tabela 'chamados' pronta.")


def criar_tabela_mensagens():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensagens_chamado (
            id INT AUTO_INCREMENT PRIMARY KEY,
            chamado_id INT NOT NULL,
            autor_id INT,
            autor_nome VARCHAR(255),
            autor_papel VARCHAR(20),
            mensagem TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chamado_id) REFERENCES chamados(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Tabela 'mensagens_chamado' pronta.")


def atualizar_tabela():
    colunas_novas = {
        "sla_resposta": "VARCHAR(50)",
        "sla_resolucao": "VARCHAR(50)",
        "equipe_destino": "VARCHAR(100)",
        "titulo_resumido": "VARCHAR(255)",
        "descricao_padronizada": "TEXT",
        "confiabilidade": "VARCHAR(50)",
        "usuario_id": "INT",
        "analista_id": "INT",
        "atualizado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    }
    conn = conectar()
    cursor = conn.cursor()
    for nome_coluna, tipo in colunas_novas.items():
        try:
            cursor.execute(f"ALTER TABLE chamados ADD COLUMN {nome_coluna} {tipo}")
            conn.commit()
            print(f"Coluna '{nome_coluna}' adicionada.")
        except mysql.connector.errors.ProgrammingError:
            pass
    cursor.close()
    conn.close()
    print("Tabela migrada/verificada.")


def atualizar_tabela_usuarios():
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN totp_secret VARCHAR(64)")
        conn.commit()
        print("Coluna 'totp_secret' adicionada.")
    except mysql.connector.errors.ProgrammingError:
        pass
    cursor.close()
    conn.close()


def salvar_chamado(titulo, descricao, categoria, urgencia, sla_resposta=None,
                    sla_resolucao=None, equipe_destino=None, titulo_resumido=None,
                    descricao_padronizada=None, confiabilidade=None, usuario_id=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO chamados
           (titulo, descricao, categoria, urgencia, sla_resposta, sla_resolucao,
            equipe_destino, titulo_resumido, descricao_padronizada, confiabilidade, usuario_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (titulo, descricao, categoria, urgencia, sla_resposta, sla_resolucao,
         equipe_destino, titulo_resumido, descricao_padronizada, confiabilidade, usuario_id),
    )
    conn.commit()
    novo_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return novo_id


def listar_chamados(limite=20, usuario_id=None):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    base_query = """
        SELECT c.*, u.nome AS nome_usuario, a.nome AS nome_analista
        FROM chamados c
        LEFT JOIN usuarios u ON c.usuario_id = u.id
        LEFT JOIN usuarios a ON c.analista_id = a.id
    """
    if usuario_id is not None:
        cursor.execute(
            base_query + " WHERE c.usuario_id = %s ORDER BY c.criado_em DESC LIMIT %s",
            (usuario_id, limite),
        )
    else:
        cursor.execute(
            base_query + " ORDER BY c.criado_em DESC LIMIT %s", (limite,)
        )
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados


def buscar_chamado_por_id(chamado_id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT c.*, u.nome AS nome_usuario, a.nome AS nome_analista
           FROM chamados c
           LEFT JOIN usuarios u ON c.usuario_id = u.id
           LEFT JOIN usuarios a ON c.analista_id = a.id
           WHERE c.id = %s""",
        (chamado_id,),
    )
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def atualizar_status_chamado(chamado_id, novo_status):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chamados SET status = %s WHERE id = %s", (novo_status, chamado_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def atribuir_chamado(chamado_id, analista_id):
    """Vincula um analista ao chamado (assignment, conforme ITIL 4) e,
    se o chamado ainda estiver 'Novo', move para 'Em Andamento'."""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET analista_id = %s,
               status = IF(status = 'Novo', 'Em Andamento', status)
           WHERE id = %s""",
        (analista_id, chamado_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def listar_mensagens_chamado(chamado_id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM mensagens_chamado WHERE chamado_id = %s ORDER BY criado_em ASC",
        (chamado_id,),
    )
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados


def enviar_mensagem_chamado(chamado_id, autor_id, autor_nome, autor_papel, mensagem):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO mensagens_chamado (chamado_id, autor_id, autor_nome, autor_papel, mensagem)
           VALUES (%s, %s, %s, %s, %s)""",
        (chamado_id, autor_id, autor_nome, autor_papel, mensagem),
    )
    conn.commit()
    novo_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return novo_id


def criar_tabela_usuarios():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            senha_hash VARCHAR(255) NOT NULL,
            papel VARCHAR(20) NOT NULL DEFAULT 'usuario',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Tabela 'usuarios' pronta.")


def criar_usuario(nome, email, senha_hash, papel):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, papel) VALUES (%s, %s, %s, %s)",
        (nome, email, senha_hash, papel),
    )
    conn.commit()
    novo_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return novo_id


def buscar_usuario_por_email(email):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def listar_usuarios():
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, email, papel, criado_em FROM usuarios ORDER BY criado_em DESC")
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados


def buscar_usuario_por_id(usuario_id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def atualizar_usuario(usuario_id, nome, email, papel, senha_hash=None):
    conn = conectar()
    cursor = conn.cursor()
    if senha_hash:
        cursor.execute(
            "UPDATE usuarios SET nome = %s, email = %s, papel = %s, senha_hash = %s WHERE id = %s",
            (nome, email, papel, senha_hash, usuario_id),
        )
    else:
        cursor.execute(
            "UPDATE usuarios SET nome = %s, email = %s, papel = %s WHERE id = %s",
            (nome, email, papel, usuario_id),
        )
    conn.commit()
    linhas_afetadas = cursor.rowcount
    cursor.close()
    conn.close()
    return linhas_afetadas


def excluir_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    conn.commit()
    linhas_afetadas = cursor.rowcount
    cursor.close()
    conn.close()
    return linhas_afetadas


def atualizar_senha(usuario_id, novo_hash_senha):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET senha_hash = %s WHERE id = %s", (novo_hash_senha, usuario_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def salvar_totp_secret(usuario_id, secret):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET totp_secret = %s WHERE id = %s", (secret, usuario_id)
    )
    conn.commit()
    cursor.close()
    conn.close()



def criar_tabela_codigos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codigos_verificacao (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            codigo VARCHAR(10) NOT NULL,
            tipo VARCHAR(30) NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expira_em TIMESTAMP NOT NULL,
            usado BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Tabela 'codigos_verificacao' pronta.")


def salvar_codigo_verificacao(usuario_id, codigo, tipo, validade_minutos=10):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO codigos_verificacao (usuario_id, codigo, tipo, expira_em)
           VALUES (%s, %s, %s, NOW() + INTERVAL %s MINUTE)""",
        (usuario_id, codigo, tipo, validade_minutos),
    )
    conn.commit()
    cursor.close()
    conn.close()


def verificar_codigo(usuario_id, codigo, tipo):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT * FROM codigos_verificacao
           WHERE usuario_id = %s AND codigo = %s AND tipo = %s
             AND usado = FALSE AND expira_em > NOW()
           ORDER BY criado_em DESC LIMIT 1""",
        (usuario_id, codigo, tipo),
    )
    resultado = cursor.fetchone()
    if resultado:
        cursor.execute(
            "UPDATE codigos_verificacao SET usado = TRUE WHERE id = %s", (resultado["id"],)
        )
        conn.commit()
    cursor.close()
    conn.close()
    return resultado is not None


if __name__ == "__main__":
    criar_tabela()
    atualizar_tabela()
    criar_tabela_usuarios()
    atualizar_tabela_usuarios()
    criar_tabela_codigos()
    criar_tabela_mensagens()