import os
import logging
import json
import io
import re
import zipfile
import hashlib
import hmac
from datetime import datetime
import mysql.connector
from dotenv import load_dotenv

from sla import calcular_prazos
from observability import configurar_logging

logger = logging.getLogger(__name__)

load_dotenv()

TRANSICOES_STATUS = {
    "Novo": ("Em Andamento",),
    "Em Andamento": ("Em Espera", "Resolvido"),
    "Em Espera": ("Em Andamento",),
    "Resolvido": ("Em Andamento",),
    "Fechado": (),
    "Cancelado": (),
}

CATEGORIAS_VALIDAS = {"Acesso", "Software", "Hardware", "Rede", "Outros"}
URGENCIAS_VALIDAS = {"Baixa", "Media", "Alta", "Critica"}
EQUIPES_VALIDAS = {"Suporte", "Software", "Hardware", "Redes"}
VERSAO_POLITICA_PRIVACIDADE = os.getenv("POLITICA_PRIVACIDADE_VERSAO", "1.1.0")


def status_disponiveis(status_atual):
    return list(TRANSICOES_STATUS.get(status_atual, ()))


def conectar():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def _coluna_existe(cursor, tabela, coluna):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (tabela, coluna),
    )
    return cursor.fetchone()[0] > 0


def _fk_existe(cursor, tabela, nome_fk):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
             AND CONSTRAINT_NAME = %s AND CONSTRAINT_TYPE = 'FOREIGN KEY'""",
        (tabela, nome_fk),
    )
    return cursor.fetchone()[0] > 0


def _trigger_existe(cursor, nome_trigger):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.TRIGGERS
           WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = %s""",
        (nome_trigger,),
    )
    return cursor.fetchone()[0] > 0


def _indice_existe(cursor, tabela, nome_indice):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s""",
        (tabela, nome_indice),
    )
    return cursor.fetchone()[0] > 0


def _registrar_auditoria(cursor, usuario_id, acao, entidade, entidade_id=None,
                         resultado="SUCESSO", detalhes=None):
    """Registra metadados mínimos do evento; nunca inclua senhas, textos ou anexos."""
    if resultado not in {"SUCESSO", "FALHA"}:
        raise ValueError("Resultado de auditoria inválido.")
    detalhes_json = json.dumps(detalhes, ensure_ascii=False) if detalhes else None
    cursor.execute(
        """INSERT INTO auditoria
           (usuario_id, acao, entidade, entidade_id, resultado, detalhes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (usuario_id, acao, entidade, entidade_id, resultado, detalhes_json),
    )


def registrar_auditoria(usuario_id, acao, entidade, entidade_id=None,
                        resultado="SUCESSO", detalhes=None):
    """Registra evento fora de uma operação de domínio, como login ou logout."""
    conn = conectar()
    cursor = conn.cursor()
    try:
        _registrar_auditoria(cursor, usuario_id, acao, entidade, entidade_id, resultado, detalhes)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def registrar_login(usuario_id):
    """Persiste o último acesso e a auditoria na mesma transação."""
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE usuarios SET ultimo_login_em = %s WHERE id = %s", (datetime.now(), usuario_id))
        _registrar_auditoria(cursor, usuario_id, "LOGIN_REALIZADO", "sessao")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def criar_tabela_auditoria():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NULL,
            acao VARCHAR(80) NOT NULL,
            entidade VARCHAR(40) NOT NULL,
            entidade_id INT NULL,
            resultado VARCHAR(10) NOT NULL,
            detalhes JSON NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_auditoria_criado_em (criado_em),
            INDEX idx_auditoria_usuario (usuario_id),
            INDEX idx_auditoria_entidade (entidade, entidade_id)
        )
    """)
    protecoes = {
        "bloquear_update_auditoria": """
            CREATE TRIGGER bloquear_update_auditoria
            BEFORE UPDATE ON auditoria
            FOR EACH ROW SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Registros de auditoria não podem ser alterados'
        """,
        "bloquear_delete_auditoria": """
            CREATE TRIGGER bloquear_delete_auditoria
            BEFORE DELETE ON auditoria
            FOR EACH ROW SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Registros de auditoria não podem ser excluídos'
        """,
    }
    for nome_trigger, comando in protecoes.items():
        if not _trigger_existe(cursor, nome_trigger):
            cursor.execute(comando)
    conn.commit()
    cursor.close()
    conn.close()


def _hash_politica_privacidade():
    caminho = os.path.join(os.path.dirname(__file__), "PRIVACIDADE.md")
    try:
        with open(caminho, "rb") as arquivo:
            return hashlib.sha256(arquivo.read()).hexdigest()
    except OSError:
        return None


def criar_tabelas_privacidade():
    """Registra a versão publicada e os aceites vinculados a ela."""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS politicas_privacidade (
            versao VARCHAR(30) PRIMARY KEY,
            conteudo_hash CHAR(64) NULL,
            publicada_em DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aceites_privacidade (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            politica_versao VARCHAR(30) NOT NULL,
            finalidade VARCHAR(80) NOT NULL,
            aceito_em DATETIME NOT NULL,
            revogado_em DATETIME NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            INDEX idx_aceites_usuario_finalidade (usuario_id, finalidade, aceito_em)
        )
    """)
    cursor.execute(
        """INSERT IGNORE INTO politicas_privacidade (versao, conteudo_hash, publicada_em)
           VALUES (%s, %s, %s)""",
        (VERSAO_POLITICA_PRIVACIDADE, _hash_politica_privacidade(), datetime.now()),
    )
    conn.commit()
    cursor.close()
    conn.close()


def usuario_aceitou_politica(usuario_id, finalidade="uso_do_sistema"):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT 1 FROM aceites_privacidade
           WHERE usuario_id = %s AND politica_versao = %s AND finalidade = %s
             AND revogado_em IS NULL
           ORDER BY aceito_em DESC LIMIT 1""",
        (usuario_id, VERSAO_POLITICA_PRIVACIDADE, finalidade),
    )
    aceitou = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return aceitou


def registrar_aceite_privacidade(usuario_id, finalidade, autor_id=None):
    conn = conectar()
    cursor = conn.cursor()
    agora = datetime.now()
    cursor.execute(
        """INSERT INTO aceites_privacidade (usuario_id, politica_versao, finalidade, aceito_em)
           VALUES (%s, %s, %s, %s)""",
        (usuario_id, VERSAO_POLITICA_PRIVACIDADE, finalidade, agora),
    )
    _registrar_auditoria(
        cursor, autor_id or usuario_id, "ACEITE_PRIVACIDADE_REGISTRADO", "usuario", usuario_id,
        detalhes={"politica_versao": VERSAO_POLITICA_PRIVACIDADE, "finalidade": finalidade},
    )
    conn.commit()
    cursor.close()
    conn.close()


def listar_auditoria(limite=200, usuario_id=None):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    consulta = """SELECT a.id, a.criado_em, a.usuario_id, a.acao, a.entidade,
                         a.entidade_id, a.resultado, a.detalhes, u.nome AS nome_usuario
                  FROM auditoria a
                  LEFT JOIN usuarios u ON u.id = a.usuario_id"""
    parametros = [limite]
    if usuario_id is not None:
        consulta += " WHERE a.usuario_id = %s"
        parametros.insert(0, usuario_id)
    consulta += " ORDER BY a.id DESC LIMIT %s"
    cursor.execute(consulta, tuple(parametros))
    eventos = cursor.fetchall()
    cursor.close()
    conn.close()
    return eventos


def criar_tabela_departamentos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departamentos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(100) NOT NULL UNIQUE,
            descricao VARCHAR(255) NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def criar_tabela_usuarios():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,

            -- Perfil
            nome VARCHAR(255) NOT NULL,
            sobrenome VARCHAR(255) NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            cpf_hash CHAR(64) NULL,
            UNIQUE KEY uq_usuarios_cpf_hash (cpf_hash),
            papel VARCHAR(20) NOT NULL DEFAULT 'usuario',
            telefone VARCHAR(30) NULL,
            departamento VARCHAR(100) NULL,
            departamento_id INT NULL,
            cargo VARCHAR(100) NULL,

            -- Autenticação
            senha_hash VARCHAR(255) NOT NULL,
            totp_secret VARCHAR(64),
            senha_deve_ser_redefinida BOOLEAN NOT NULL DEFAULT FALSE,
            conta_anonimizada_em DATETIME NULL,
            ultimo_login_em DATETIME NULL,

            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.debug("Tabela de usuários verificada.")


def migrar_tabela_usuarios():
    conn = conectar()
    cursor = conn.cursor()
    colunas_novas = {
        "totp_secret": "VARCHAR(64)",
        "senha_deve_ser_redefinida": "BOOLEAN NOT NULL DEFAULT FALSE",
        "conta_anonimizada_em": "DATETIME NULL",
        "ultimo_login_em": "DATETIME NULL",
        "sobrenome": "VARCHAR(255) NULL",
        "telefone": "VARCHAR(30) NULL",
        "cpf_hash": "CHAR(64) NULL",
        "departamento": "VARCHAR(100) NULL",
        "departamento_id": "INT NULL",
        "cargo": "VARCHAR(100) NULL",
    }
    for nome_coluna, tipo in colunas_novas.items():
        if not _coluna_existe(cursor, "usuarios", nome_coluna):
            cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {nome_coluna} {tipo}")
            conn.commit()
            logger.info("Migração aplicada: coluna %s adicionada em usuários.", nome_coluna)
    if not _indice_existe(cursor, "usuarios", "uq_usuarios_cpf_hash"):
        cursor.execute("CREATE UNIQUE INDEX uq_usuarios_cpf_hash ON usuarios (cpf_hash)")
        conn.commit()
        logger.info("Migração aplicada: índice único de CPF adicionado em usuários.")
    cursor.close()
    conn.close()


def migrar_departamentos_usuarios():
    """Converte departamentos legados em registros reutilizáveis e vincula as contas."""
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT IGNORE INTO departamentos (nome)
               SELECT DISTINCT TRIM(departamento)
               FROM usuarios
               WHERE departamento IS NOT NULL AND TRIM(departamento) <> ''"""
        )
        cursor.execute(
            """UPDATE usuarios u
               INNER JOIN departamentos d ON d.nome = TRIM(u.departamento)
               SET u.departamento_id = d.id
               WHERE u.departamento_id IS NULL
                 AND u.departamento IS NOT NULL AND TRIM(u.departamento) <> ''"""
        )
        if not _fk_existe(cursor, "usuarios", "fk_usuarios_departamento"):
            cursor.execute(
                """ALTER TABLE usuarios
                   ADD CONSTRAINT fk_usuarios_departamento
                   FOREIGN KEY (departamento_id) REFERENCES departamentos(id) ON DELETE SET NULL"""
            )
        conn.commit()
    except mysql.connector.Error as erro:
        conn.rollback()
        logger.warning("Não foi possível concluir a migração de departamentos: %s", erro)
    finally:
        cursor.close()
        conn.close()

def criar_tabela_chamados():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chamados (
            id INT AUTO_INCREMENT PRIMARY KEY,

            -- Conteúdo (título/descrição já na versão final: a IA refina o
            -- texto coletado no chat antes de o chamado ser salvo)
            titulo VARCHAR(255) NOT NULL,
            descricao TEXT NOT NULL,

            -- Classificação (IA)
            categoria VARCHAR(100),
            urgencia VARCHAR(50),
            confiabilidade VARCHAR(50),
            equipe_destino VARCHAR(100),
            categoria_ia VARCHAR(100),
            urgencia_ia VARCHAR(50),
            equipe_ia VARCHAR(100),
            categoria_final VARCHAR(100) NULL,
            urgencia_final VARCHAR(50) NULL,
            equipe_final VARCHAR(100) NULL,
            sla_resposta VARCHAR(50),
            sla_resolucao VARCHAR(50),

            -- Relacionamentos
            usuario_id INT,
            analista_id INT,

            -- Ciclo de vida (ITIL 4)
            status VARCHAR(50) NOT NULL DEFAULT 'Novo',
            motivo_cancelamento VARCHAR(255) NULL,
            diagnostico_final TEXT NULL,
            solucao_final TEXT NULL,
            compartilhar_conhecimento BOOLEAN NOT NULL DEFAULT FALSE,
            uso_ia_autorizado_em DATETIME NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            -- Controle de SLA (motor em sla.py)
            prazo_resposta DATETIME NULL,
            prazo_resolucao DATETIME NULL,
            primeira_resposta_em DATETIME NULL,
            resolvido_em DATETIME NULL,
            pausado_em DATETIME NULL,
            tempo_pausado_min INT DEFAULT 0,

            CONSTRAINT fk_chamados_usuario FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE SET NULL,
            CONSTRAINT fk_chamados_analista FOREIGN KEY (analista_id)
                REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.debug("Tabela de chamados verificada.")


def migrar_tabela_chamados():
    conn = conectar()
    cursor = conn.cursor()

    colunas_novas = {
        "sla_resposta": "VARCHAR(50)",
        "sla_resolucao": "VARCHAR(50)",
        "equipe_destino": "VARCHAR(100)",
        "confiabilidade": "VARCHAR(50)",
        "categoria_ia": "VARCHAR(100)",
        "urgencia_ia": "VARCHAR(50)",
        "equipe_ia": "VARCHAR(100)",
        "categoria_final": "VARCHAR(100) NULL",
        "urgencia_final": "VARCHAR(50) NULL",
        "equipe_final": "VARCHAR(100) NULL",
        "usuario_id": "INT",
        "analista_id": "INT",
        "motivo_cancelamento": "VARCHAR(255) NULL",
        "diagnostico_final": "TEXT NULL",
        "solucao_final": "TEXT NULL",
        "compartilhar_conhecimento": "BOOLEAN NOT NULL DEFAULT FALSE",
        "uso_ia_autorizado_em": "DATETIME NULL",
        "atualizado_em": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        "prazo_resposta": "DATETIME NULL",
        "prazo_resolucao": "DATETIME NULL",
        "primeira_resposta_em": "DATETIME NULL",
        "resolvido_em": "DATETIME NULL",
        "pausado_em": "DATETIME NULL",
        "tempo_pausado_min": "INT DEFAULT 0",
    }
    for nome_coluna, tipo in colunas_novas.items():
        if not _coluna_existe(cursor, "chamados", nome_coluna):
            cursor.execute(f"ALTER TABLE chamados ADD COLUMN {nome_coluna} {tipo}")
            conn.commit()
            logger.info("Migração aplicada: coluna %s adicionada em chamados.", nome_coluna)

    if _coluna_existe(cursor, "chamados", "titulo_resumido"):
        cursor.execute(
            "UPDATE chamados SET titulo = COALESCE(NULLIF(titulo_resumido, ''), titulo)"
        )
        cursor.execute("ALTER TABLE chamados DROP COLUMN titulo_resumido")
        conn.commit()
        logger.info("Migração aplicada: titulo_resumido consolidada em titulo.")

    if _coluna_existe(cursor, "chamados", "descricao_padronizada"):
        cursor.execute(
            "UPDATE chamados SET descricao = COALESCE(NULLIF(descricao_padronizada, ''), descricao)"
        )
        cursor.execute("ALTER TABLE chamados DROP COLUMN descricao_padronizada")
        conn.commit()
        logger.info("Migração aplicada: descricao_padronizada consolidada em descricao.")

    for nome_fk, coluna in (
        ("fk_chamados_usuario", "usuario_id"),
        ("fk_chamados_analista", "analista_id"),
    ):
        if not _fk_existe(cursor, "chamados", nome_fk):
            try:
                cursor.execute(
                    f"""ALTER TABLE chamados
                        ADD CONSTRAINT {nome_fk} FOREIGN KEY ({coluna})
                        REFERENCES usuarios(id) ON DELETE SET NULL"""
                )
                conn.commit()
                logger.info("Migração aplicada: chave estrangeira %s adicionada.", nome_fk)
            except mysql.connector.Error as erro:
                logger.warning("Não foi possível criar a chave estrangeira %s: %s", nome_fk, erro)

    for coluna_excedente in ("classificacao_validada_em", "classificacao_validada_por"):
        if _coluna_existe(cursor, "chamados", coluna_excedente):
            cursor.execute(f"ALTER TABLE chamados DROP COLUMN {coluna_excedente}")
            conn.commit()
            logger.info("Minimização aplicada: coluna sem leitor removida de chamados: %s", coluna_excedente)

    cursor.execute("UPDATE chamados SET status = 'Em Andamento' WHERE status = 'Em Aberto'")
    cursor.execute("UPDATE chamados SET status = 'Em Espera' WHERE status = 'Aguardando'")
    cursor.execute("UPDATE chamados SET status = 'Fechado' WHERE status = 'Finalizado'")
    cursor.execute("""UPDATE chamados
                      SET categoria_ia = COALESCE(categoria_ia, categoria),
                          urgencia_ia = COALESCE(urgencia_ia, urgencia),
                          equipe_ia = COALESCE(equipe_ia, equipe_destino)
                   """)
    conn.commit()

    cursor.close()
    conn.close()
    logger.debug("Migrações de chamados verificadas.")


def criar_tabela_base_casos_ia():
    """Cria a memória operacional usada pelo RAG.

    A tabela só recebe chamados cuja resolução foi confirmada pelo solicitante e
    autorizada pelo analista. Ela é deliberadamente separada dos chamados brutos.
    """
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_casos_ia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            chamado_id INT NOT NULL UNIQUE,
            titulo VARCHAR(255) NOT NULL,
            descricao_problema TEXT NOT NULL,
            categoria_ia VARCHAR(100) NULL,
            urgencia_ia VARCHAR(50) NULL,
            equipe_ia VARCHAR(100) NULL,
            confiabilidade_ia VARCHAR(50) NULL,
            categoria_final VARCHAR(100) NOT NULL,
            urgencia_final VARCHAR(50) NOT NULL,
            equipe_final VARCHAR(100) NOT NULL,
            classificacao_corrigida BOOLEAN NOT NULL DEFAULT FALSE,
            diagnostico TEXT NOT NULL,
            solucao TEXT NOT NULL,
            analista_id INT NULL,
            confirmado_em DATETIME NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_base_casos_chamado FOREIGN KEY (chamado_id)
                REFERENCES chamados(id) ON DELETE CASCADE,
            CONSTRAINT fk_base_casos_analista FOREIGN KEY (analista_id)
                REFERENCES usuarios(id) ON DELETE SET NULL,
            INDEX idx_base_casos_categoria_final (categoria_final)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.debug("Tabela de base de casos da IA verificada.")


def migrar_tabela_base_casos_ia():
    """Evolui a base de aprendizado sem perder casos já confirmados."""
    conn = conectar()
    cursor = conn.cursor()
    colunas_novas = {
        "categoria_ia": "VARCHAR(100) NULL",
        "urgencia_ia": "VARCHAR(50) NULL",
        "equipe_ia": "VARCHAR(100) NULL",
        "confiabilidade_ia": "VARCHAR(50) NULL",
        "categoria_final": "VARCHAR(100) NULL",
        "urgencia_final": "VARCHAR(50) NULL",
        "equipe_final": "VARCHAR(100) NULL",
        "classificacao_corrigida": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    for nome_coluna, tipo in colunas_novas.items():
        if not _coluna_existe(cursor, "base_casos_ia", nome_coluna):
            cursor.execute(f"ALTER TABLE base_casos_ia ADD COLUMN {nome_coluna} {tipo}")
            conn.commit()
            logger.info("Migração aplicada: coluna %s adicionada em base_casos_ia.", nome_coluna)

    # Migra o valor legado antes de removê-lo; as novas colunas passam a ser a fonte única.
    if _coluna_existe(cursor, "base_casos_ia", "categoria"):
        cursor.execute("""UPDATE base_casos_ia
                          SET categoria_final = COALESCE(categoria_final, categoria),
                              categoria_ia = COALESCE(categoria_ia, categoria)""")
        conn.commit()
        cursor.execute("ALTER TABLE base_casos_ia DROP COLUMN categoria")
        conn.commit()
        logger.info("Migração aplicada: coluna legada categoria removida de base_casos_ia.")
    cursor.execute("""UPDATE base_casos_ia
                      SET urgencia_final = COALESCE(urgencia_final, 'Media'),
                          equipe_final = COALESCE(equipe_final, 'Suporte')""")
    # Casos legados não possuem autorização registrada do titular. A remoção
    # alcança somente a cópia de aprendizagem; o chamado original é preservado.
    cursor.execute("""DELETE b FROM base_casos_ia b
                      LEFT JOIN chamados c ON c.id = b.chamado_id
                      WHERE c.uso_ia_autorizado_em IS NULL""")
    if cursor.rowcount:
        logger.info("%d caso(s) legado(s) removido(s) da base da IA por falta de autorização do titular.", cursor.rowcount)
    conn.commit()
    cursor.close()
    conn.close()


def listar_casos_base_ia():
    """Retorna exclusivamente os casos confirmados que podem orientar a IA."""
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, chamado_id, titulo, descricao_problema, categoria_ia, urgencia_ia,
               equipe_ia, confiabilidade_ia, categoria_final, urgencia_final, equipe_final,
               classificacao_corrigida, diagnostico, solucao, confirmado_em
        FROM base_casos_ia
        ORDER BY confirmado_em DESC
    """)
    casos = cursor.fetchall()
    cursor.close()
    conn.close()
    return casos


def salvar_chamado(titulo, descricao, categoria, urgencia, confiabilidade=None,
                    sla_resposta=None, sla_resolucao=None, equipe_destino=None,
                    usuario_id=None):
    criado_em = datetime.now()
    prazo_resposta, prazo_resolucao = calcular_prazos(criado_em, urgencia)

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO chamados
           (titulo, descricao, categoria, urgencia, confiabilidade, equipe_destino,
            categoria_ia, urgencia_ia, equipe_ia,
            sla_resposta, sla_resolucao, usuario_id, criado_em, prazo_resposta, prazo_resolucao)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (titulo, descricao, categoria, urgencia, confiabilidade, equipe_destino,
         categoria, urgencia, equipe_destino,
         sla_resposta, sla_resolucao, usuario_id, criado_em, prazo_resposta, prazo_resolucao),
    )
    novo_id = cursor.lastrowid
    _registrar_auditoria(
        cursor, usuario_id, "CHAMADO_ABERTO", "chamado", novo_id,
        detalhes={"categoria": categoria, "urgencia": urgencia},
    )
    conn.commit()
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


def atualizar_status_chamado(chamado_id, novo_status, autor_id=None):
    agora = datetime.now()

    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT status, pausado_em, tempo_pausado_min, resolvido_em FROM chamados WHERE id = %s",
        (chamado_id,),
    )
    atual = cursor.fetchone()
    cursor.close()

    if not atual:
        conn.close()
        raise ValueError("Chamado não encontrado.")

    status_atual = atual["status"]
    if novo_status == status_atual:
        conn.close()
        return

    if novo_status not in status_disponiveis(status_atual):
        conn.close()
        raise ValueError(
            f"Transição inválida: '{status_atual}' não pode ser alterado para '{novo_status}'."
        )
    pausado_em_novo = atual["pausado_em"]
    tempo_pausado_min_novo = atual["tempo_pausado_min"] or 0
    resolvido_em_novo = atual["resolvido_em"]

    if novo_status == "Em Espera" and status_atual != "Em Espera":
        pausado_em_novo = agora
    elif status_atual == "Em Espera" and novo_status != "Em Espera":
        if atual["pausado_em"]:
            tempo_pausado_min_novo += (agora - atual["pausado_em"]).total_seconds() / 60
        pausado_em_novo = None

    if novo_status in ("Resolvido", "Fechado"):
        if resolvido_em_novo is None:
            resolvido_em_novo = agora
    else:
        resolvido_em_novo = None

    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET status = %s, pausado_em = %s, tempo_pausado_min = %s, resolvido_em = %s
           WHERE id = %s""",
        (novo_status, pausado_em_novo, tempo_pausado_min_novo, resolvido_em_novo, chamado_id),
    )
    _registrar_auditoria(
        cursor, autor_id, "STATUS_ALTERADO", "chamado", chamado_id,
        detalhes={"anterior": status_atual, "novo": novo_status},
    )
    conn.commit()
    cursor.close()
    conn.close()


def registrar_resolucao_chamado(chamado_id, analista_id, diagnostico, solucao,
                                compartilhar_conhecimento, categoria_final,
                                urgencia_final, equipe_final):
    """Registra a resolução técnica antes de marcar o chamado como resolvido."""
    diagnostico = (diagnostico or "").strip()
    solucao = (solucao or "").strip()
    if not diagnostico or not solucao:
        raise ValueError("Informe o diagnóstico e a solução aplicada antes de resolver o chamado.")
    if categoria_final not in CATEGORIAS_VALIDAS:
        raise ValueError("Categoria final inválida.")
    if urgencia_final not in URGENCIAS_VALIDAS:
        raise ValueError("Urgência final inválida.")
    if equipe_final not in EQUIPES_VALIDAS:
        raise ValueError("Equipe final inválida.")

    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT status, analista_id, categoria_ia, urgencia_ia, equipe_ia FROM chamados WHERE id = %s",
        (chamado_id,),
    )
    chamado = cursor.fetchone()
    if not chamado or chamado["analista_id"] != analista_id or chamado["status"] != "Em Andamento":
        cursor.close()
        conn.close()
        raise ValueError("Somente o analista responsável pode registrar a resolução deste chamado.")
    cursor.close()

    agora = datetime.now()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET diagnostico_final = %s, solucao_final = %s,
               compartilhar_conhecimento = %s,
               categoria = %s, urgencia = %s, equipe_destino = %s,
               categoria_final = %s, urgencia_final = %s, equipe_final = %s,
               status = 'Resolvido', resolvido_em = %s
           WHERE id = %s""",
        (diagnostico, solucao, bool(compartilhar_conhecimento),
         categoria_final, urgencia_final, equipe_final,
         categoria_final, urgencia_final, equipe_final,
         agora, chamado_id),
    )
    classificacao_corrigida = any((
        chamado["categoria_ia"] != categoria_final,
        chamado["urgencia_ia"] != urgencia_final,
        chamado["equipe_ia"] != equipe_final,
    ))
    _registrar_auditoria(
        cursor, analista_id, "RESOLUCAO_REGISTRADA", "chamado", chamado_id,
        detalhes={
            "compartilhar_conhecimento": bool(compartilhar_conhecimento),
            "classificacao_corrigida": classificacao_corrigida,
        },
    )
    conn.commit()
    cursor.close()
    conn.close()


def atribuir_chamado(chamado_id, analista_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET analista_id = %s,
               status = 'Em Andamento'
           WHERE id = %s AND status = 'Novo' AND analista_id IS NULL""",
        (analista_id, chamado_id),
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("Este chamado já foi atribuído ou não está mais disponível para atendimento.")
    _registrar_auditoria(
        cursor, analista_id, "CHAMADO_ATRIBUIDO", "chamado", chamado_id,
        detalhes={"analista_id": analista_id, "status_anterior": "Novo", "status_novo": "Em Andamento"},
    )
    conn.commit()
    cursor.close()
    conn.close()


def cancelar_chamado_sem_atribuicao(chamado_id, motivo, autor_id=None):
    if not motivo or not motivo.strip():
        raise ValueError("Informe o motivo do cancelamento.")

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET status = 'Cancelado', motivo_cancelamento = %s
           WHERE id = %s AND status = 'Novo' AND analista_id IS NULL""",
        (motivo.strip(), chamado_id),
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("O chamado não pode mais ser cancelado porque já foi atribuído ou saiu do status Novo.")
    _registrar_auditoria(
        cursor, autor_id, "CHAMADO_CANCELADO", "chamado", chamado_id,
        detalhes={"status_anterior": "Novo"},
    )
    conn.commit()
    cursor.close()
    conn.close()


def _anonimizar_texto_para_ia(texto, usuario):
    """Remove identificadores diretos antes de reutilizar texto no RAG local."""
    import re

    texto = texto or ""
    texto = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[e-mail removido]", texto)
    texto = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF removido]", texto)
    texto = re.sub(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)", "[telefone removido]", texto)
    for campo in ("email", "nome", "sobrenome", "telefone"):
        valor = (usuario.get(campo) or "").strip()
        if valor:
            texto = re.sub(re.escape(valor), f"[{campo} removido]", texto, flags=re.IGNORECASE)
    return texto


def confirmar_resolucao_usuario(chamado_id, usuario_id, autoriza_uso_ia=False):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    agora = datetime.now()
    cursor.execute(
        """UPDATE chamados
           SET status = 'Fechado',
               uso_ia_autorizado_em = CASE WHEN %s THEN %s ELSE NULL END
           WHERE id = %s AND usuario_id = %s AND status = 'Resolvido'""",
        (bool(autoriza_uso_ia), agora, chamado_id, usuario_id),
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("A resolução não pode ser confirmada para este chamado.")

    cursor.execute(
        """SELECT c.titulo, c.descricao, c.categoria_ia, c.urgencia_ia, c.equipe_ia, c.confiabilidade,
                  c.categoria_final, c.urgencia_final, c.equipe_final, c.diagnostico_final, c.solucao_final,
                  c.compartilhar_conhecimento, c.analista_id, u.nome, u.sobrenome, u.email, u.telefone
           FROM chamados c JOIN usuarios u ON u.id = c.usuario_id
           WHERE c.id = %s""",
        (chamado_id,),
    )
    chamado = cursor.fetchone()
    if autoriza_uso_ia and chamado["compartilhar_conhecimento"] and chamado["diagnostico_final"] and chamado["solucao_final"]:
        cursor.execute(
            """INSERT INTO aceites_privacidade (usuario_id, politica_versao, finalidade, aceito_em)
               VALUES (%s, %s, %s, %s)""",
            (usuario_id, VERSAO_POLITICA_PRIVACIDADE, "uso_ia_referencia_interna", agora),
        )
        classificacao_corrigida = any((
            chamado["categoria_ia"] != chamado["categoria_final"],
            chamado["urgencia_ia"] != chamado["urgencia_final"],
            chamado["equipe_ia"] != chamado["equipe_final"],
        ))
        cursor.execute(
            """INSERT INTO base_casos_ia
               (chamado_id, titulo, descricao_problema,
                categoria_ia, urgencia_ia, equipe_ia, confiabilidade_ia,
                categoria_final, urgencia_final, equipe_final, classificacao_corrigida,
                diagnostico, solucao, analista_id, confirmado_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE titulo = VALUES(titulo),
                   descricao_problema = VALUES(descricao_problema),
                   categoria_ia = VALUES(categoria_ia), urgencia_ia = VALUES(urgencia_ia),
                   equipe_ia = VALUES(equipe_ia), confiabilidade_ia = VALUES(confiabilidade_ia),
                   categoria_final = VALUES(categoria_final), urgencia_final = VALUES(urgencia_final),
                   equipe_final = VALUES(equipe_final), classificacao_corrigida = VALUES(classificacao_corrigida),
                   diagnostico = VALUES(diagnostico), solucao = VALUES(solucao),
                   analista_id = VALUES(analista_id), confirmado_em = VALUES(confirmado_em)""",
            (chamado_id,
             _anonimizar_texto_para_ia(chamado["titulo"], chamado),
             _anonimizar_texto_para_ia(chamado["descricao"], chamado),
             chamado["categoria_ia"], chamado["urgencia_ia"], chamado["equipe_ia"], chamado["confiabilidade"],
             chamado["categoria_final"], chamado["urgencia_final"], chamado["equipe_final"], classificacao_corrigida,
             _anonimizar_texto_para_ia(chamado["diagnostico_final"], chamado),
             _anonimizar_texto_para_ia(chamado["solucao_final"], chamado), chamado["analista_id"], agora),
        )
        _registrar_auditoria(cursor, usuario_id, "CASO_PROMOVIDO_PARA_IA", "base_casos_ia", chamado_id)
    _registrar_auditoria(
        cursor, usuario_id, "RESOLUCAO_CONFIRMADA", "chamado", chamado_id,
        detalhes={"status_anterior": "Resolvido", "status_novo": "Fechado", "uso_ia_autorizado": bool(autoriza_uso_ia)},
    )
    conn.commit()
    cursor.close()
    conn.close()


def reabrir_chamado_usuario(chamado_id, usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE chamados
           SET status = 'Em Andamento', resolvido_em = NULL
           WHERE id = %s AND usuario_id = %s AND status = 'Resolvido'""",
        (chamado_id, usuario_id),
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("A resolução não pode ser reaberta para este chamado.")
    _registrar_auditoria(
        cursor, usuario_id, "CHAMADO_REABERTO", "chamado", chamado_id,
        detalhes={"status_anterior": "Resolvido", "status_novo": "Em Andamento"},
    )
    conn.commit()
    cursor.close()
    conn.close()


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
    logger.debug("Tabela de mensagens verificada.")


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
    cursor.execute("SELECT status FROM chamados WHERE id = %s", (chamado_id,))
    chamado = cursor.fetchone()
    if not chamado:
        cursor.close()
        conn.close()
        raise ValueError("Chamado não encontrado.")
    if chamado[0] in ("Finalizado", "Cancelado", "Fechado"):
        cursor.close()
        conn.close()
        raise ValueError("Não é possível enviar mensagens para um chamado encerrado.")
    cursor.execute(
        """INSERT INTO mensagens_chamado (chamado_id, autor_id, autor_nome, autor_papel, mensagem)
           VALUES (%s, %s, %s, %s, %s)""",
        (chamado_id, autor_id, autor_nome, autor_papel, mensagem),
    )
    novo_id = cursor.lastrowid

    _registrar_auditoria(
        cursor, autor_id, "MENSAGEM_ENVIADA", "chamado", chamado_id,
        detalhes={"mensagem_id": novo_id, "papel_autor": autor_papel},
    )

    if autor_papel == "analista":
        cursor.execute(
            "UPDATE chamados SET primeira_resposta_em = COALESCE(primeira_resposta_em, %s) WHERE id = %s",
            (datetime.now(), chamado_id),
        )
    conn.commit()

    cursor.close()
    conn.close()

    if autor_papel == "analista" and chamado[0] == "Em Andamento":
        atualizar_status_chamado(chamado_id, "Em Espera", autor_id=autor_id)
    if autor_papel == "usuario" and chamado[0] == "Em Espera":
        atualizar_status_chamado(chamado_id, "Em Andamento", autor_id=autor_id)

    return novo_id


def criar_tabela_anexos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anexos_chamado (
            id INT AUTO_INCREMENT PRIMARY KEY,
            chamado_id INT NOT NULL,
            autor_id INT,
            nome_arquivo VARCHAR(255) NOT NULL,
            tipo_arquivo VARCHAR(120),
            conteudo LONGBLOB NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chamado_id) REFERENCES chamados(id) ON DELETE CASCADE,
            FOREIGN KEY (autor_id) REFERENCES usuarios(id) ON DELETE SET NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def salvar_anexo_chamado(chamado_id, autor_id, nome_arquivo, tipo_arquivo, conteudo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM chamados WHERE id = %s", (chamado_id,))
    chamado = cursor.fetchone()
    if not chamado:
        cursor.close()
        conn.close()
        raise ValueError("Chamado não encontrado.")
    if chamado[0] in ("Finalizado", "Cancelado", "Fechado"):
        cursor.close()
        conn.close()
        raise ValueError("Não é possível adicionar anexos a um chamado encerrado.")
    cursor.execute(
        """INSERT INTO anexos_chamado
           (chamado_id, autor_id, nome_arquivo, tipo_arquivo, conteudo)
           VALUES (%s, %s, %s, %s, %s)""",
        (chamado_id, autor_id, nome_arquivo, tipo_arquivo, conteudo),
    )
    _registrar_auditoria(
        cursor, autor_id, "ANEXO_ADICIONADO", "chamado", chamado_id,
        detalhes={"anexo_id": cursor.lastrowid, "tipo_arquivo": tipo_arquivo, "tamanho_bytes": len(conteudo)},
    )
    conn.commit()
    cursor.close()
    conn.close()


def listar_anexos_chamado(chamado_id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT id, nome_arquivo, tipo_arquivo, conteudo, criado_em
           FROM anexos_chamado WHERE chamado_id = %s ORDER BY criado_em ASC""",
        (chamado_id,),
    )
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados


def criar_tabela_pesquisas_satisfacao():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pesquisas_satisfacao (
            id INT AUTO_INCREMENT PRIMARY KEY,
            chamado_id INT NOT NULL UNIQUE,
            nota TINYINT NOT NULL,
            comentario TEXT,
            respondido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chamado_id) REFERENCES chamados(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def buscar_pesquisa_satisfacao(chamado_id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM pesquisas_satisfacao WHERE chamado_id = %s", (chamado_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def salvar_pesquisa_satisfacao(chamado_id, nota, comentario, autor_id=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pesquisas_satisfacao (chamado_id, nota, comentario) VALUES (%s, %s, %s)",
        (chamado_id, nota, comentario),
    )
    _registrar_auditoria(cursor, autor_id, "PESQUISA_RESPONDIDA", "chamado", chamado_id)
    conn.commit()
    cursor.close()
    conn.close()


def criar_tabela_atendimentos_ia():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atendimentos_ia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NULL,
            chamado_id INT NULL,
            resultado VARCHAR(30) NOT NULL DEFAULT 'Pendente',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            respondido_em DATETIME NULL,
            CONSTRAINT fk_atendimentos_ia_usuario FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE SET NULL,
            CONSTRAINT fk_atendimentos_ia_chamado FOREIGN KEY (chamado_id)
                REFERENCES chamados(id) ON DELETE SET NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def migrar_tabela_atendimentos_ia():
    """Remove conteúdo de orientação da IA que não é reutilizado nem exibido."""
    conn = conectar()
    cursor = conn.cursor()
    for coluna_excedente in ("titulo", "descricao", "solucao"):
        if _coluna_existe(cursor, "atendimentos_ia", coluna_excedente):
            cursor.execute(f"ALTER TABLE atendimentos_ia DROP COLUMN {coluna_excedente}")
            conn.commit()
            logger.info("Minimização aplicada: coluna sem leitor removida de atendimentos_ia: %s", coluna_excedente)
    cursor.close()
    conn.close()


def salvar_atendimento_ia(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO atendimentos_ia (usuario_id) VALUES (%s)",
        (usuario_id,),
    )
    atendimento_id = cursor.lastrowid
    _registrar_auditoria(cursor, usuario_id, "ORIENTACAO_IA_APRESENTADA", "atendimento_ia", atendimento_id)
    conn.commit()
    cursor.close()
    conn.close()
    return atendimento_id


def registrar_resultado_atendimento_ia(atendimento_id, resultado, chamado_id=None):
    if resultado not in {"Resolvido", "Nao resolvido"}:
        raise ValueError("Resultado de atendimento IA inválido.")

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE atendimentos_ia
           SET resultado = %s, chamado_id = %s, respondido_em = %s
           WHERE id = %s""",
        (resultado, chamado_id, datetime.now(), atendimento_id),
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("Atendimento de IA não encontrado.")
    _registrar_auditoria(
        cursor, None, "RESULTADO_ORIENTACAO_IA", "atendimento_ia", atendimento_id,
        detalhes={"resultado": resultado, "chamado_id": chamado_id},
    )
    conn.commit()
    cursor.close()
    conn.close()


def listar_atendimentos_ia(limite=5000):
    """Retorna dados agregáveis das orientações da IA para os relatórios administrativos."""
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT id, usuario_id, chamado_id, resultado, criado_em, respondido_em
           FROM atendimentos_ia
           ORDER BY criado_em DESC
           LIMIT %s""",
        (limite,),
    )
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados


def normalizar_cpf(cpf):
    """Retorna o CPF normalizado somente quando seus dígitos verificadores são válidos."""
    cpf_normalizado = re.sub(r"\D", "", cpf or "")
    if len(cpf_normalizado) != 11 or cpf_normalizado == cpf_normalizado[0] * 11:
        return None
    primeiro = (sum(int(digito) * peso for digito, peso in zip(cpf_normalizado[:9], range(10, 1, -1))) * 10) % 11
    primeiro = 0 if primeiro == 10 else primeiro
    segundo = (sum(int(digito) * peso for digito, peso in zip(cpf_normalizado[:9] + str(primeiro), range(11, 1, -1))) * 10) % 11
    segundo = 0 if segundo == 10 else segundo
    return cpf_normalizado if cpf_normalizado[-2:] == f"{primeiro}{segundo}" else None


def _hash_cpf(cpf_normalizado):
    segredo = os.getenv("CPF_HASH_SECRET")
    if not segredo:
        raise ValueError("Configure CPF_HASH_SECRET antes de cadastrar ou pesquisar por CPF.")
    return hmac.new(segredo.encode("utf-8"), cpf_normalizado.encode("utf-8"), hashlib.sha256).hexdigest()


def buscar_usuario_por_cpf(cpf):
    cpf_normalizado = normalizar_cpf(cpf)
    if not cpf_normalizado:
        return None
    cpf_hash = _hash_cpf(cpf_normalizado)
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE cpf_hash = %s", (cpf_hash,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def listar_departamentos(apenas_ativos=False):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    consulta = """SELECT d.id, d.nome, d.descricao, d.ativo, d.criado_em, d.atualizado_em,
                         COUNT(u.id) AS total_usuarios
                  FROM departamentos d
                  LEFT JOIN usuarios u ON u.departamento_id = d.id"""
    if apenas_ativos:
        consulta += " WHERE d.ativo = TRUE"
    consulta += " GROUP BY d.id, d.nome, d.descricao, d.ativo, d.criado_em, d.atualizado_em ORDER BY d.nome"
    cursor.execute(consulta)
    departamentos = cursor.fetchall()
    cursor.close()
    conn.close()
    return departamentos


def criar_departamento(nome, descricao=None, autor_id=None):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do departamento.")
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM departamentos WHERE nome = %s", (nome,))
        if cursor.fetchone():
            raise ValueError("Já existe um departamento com esse nome.")
        cursor.execute(
            "INSERT INTO departamentos (nome, descricao) VALUES (%s, %s)",
            (nome, (descricao or "").strip() or None),
        )
        departamento_id = cursor.lastrowid
        _registrar_auditoria(cursor, autor_id, "DEPARTAMENTO_CRIADO", "departamento", departamento_id)
        conn.commit()
        return departamento_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def atualizar_departamento(departamento_id, nome, descricao, ativo, autor_id=None):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do departamento.")
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM departamentos WHERE nome = %s AND id <> %s", (nome, departamento_id))
        if cursor.fetchone():
            raise ValueError("Já existe um departamento com esse nome.")
        cursor.execute(
            "UPDATE departamentos SET nome = %s, descricao = %s, ativo = %s WHERE id = %s",
            (nome, (descricao or "").strip() or None, bool(ativo), departamento_id),
        )
        if cursor.rowcount:
            cursor.execute(
                "UPDATE usuarios SET departamento = %s WHERE departamento_id = %s",
                (nome, departamento_id),
            )
            _registrar_auditoria(
                cursor, autor_id, "DEPARTAMENTO_ATUALIZADO", "departamento", departamento_id,
                detalhes={"ativo": bool(ativo)},
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def criar_usuario(nome, email, senha_hash, papel, sobrenome=None, telefone=None,
                  cpf=None, departamento=None, departamento_id=None, cargo=None, autor_id=None):
    cpf_hash = None
    if cpf:
        cpf_normalizado = normalizar_cpf(cpf)
        if not cpf_normalizado:
            raise ValueError("CPF inválido.")
        cpf_hash = _hash_cpf(cpf_normalizado)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO usuarios
           (nome, sobrenome, email, senha_hash, papel, telefone, cpf_hash, departamento, departamento_id, cargo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (nome, sobrenome, email, senha_hash, papel, telefone, cpf_hash, departamento, departamento_id, cargo),
    )
    novo_id = cursor.lastrowid
    _registrar_auditoria(
        cursor, autor_id, "USUARIO_CRIADO", "usuario", novo_id,
        detalhes={"papel": papel},
    )
    conn.commit()
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
    cursor.execute(
        """SELECT u.id, u.nome, u.sobrenome, u.email, u.papel, u.telefone,
                  COALESCE(d.nome, u.departamento) AS departamento, u.departamento_id, u.cargo, u.criado_em,
                  u.ultimo_login_em AS ultimo_login
           FROM usuarios u
           LEFT JOIN departamentos d ON d.id = u.departamento_id
           ORDER BY u.criado_em DESC"""
    )
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


def buscar_titular_por_identificador(identificador):
    """Localiza titular por e-mail ou por CPF válido, sem recuperar o número completo."""
    valor = (identificador or "").strip()
    if not valor:
        return None, "Informe um e-mail ou CPF."
    if "@" not in valor:
        if not normalizar_cpf(valor):
            return None, "Informe o e-mail cadastrado ou um CPF válido."
        usuario = buscar_usuario_por_cpf(valor)
        if not usuario:
            return None, "Nenhum titular encontrado para o CPF informado."
        return usuario, None
    usuario = buscar_usuario_por_email(valor)
    if not usuario:
        return None, "Nenhum titular encontrado para o e-mail informado."
    return usuario, None


def _json_seguro(valor):
    if isinstance(valor, (datetime,)):
        return valor.isoformat()
    if isinstance(valor, (bytes, bytearray)):
        return None
    raise TypeError(f"Tipo não serializável: {type(valor).__name__}")


def _buscar_varios(cursor, consulta, parametros=()):
    cursor.execute(consulta, parametros)
    return cursor.fetchall()


def exportar_dados_titular(usuario_id, autor_id=None):
    """Gera ZIP de acesso com dados do titular, sem expor segredos de autenticação."""
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cursor.fetchone()
        if not usuario:
            raise ValueError("Titular não encontrado.")

        conta = {k: v for k, v in usuario.items() if k not in {"senha_hash", "totp_secret"}}
        conta["credenciais_protegidas"] = {
            "senha_hash_armazenado": bool(usuario.get("senha_hash")),
            "totp_configurado": bool(usuario.get("totp_secret")),
            "codigos_de_verificacao_nao_exportados": True,
        }
        chamados_solicitados = _buscar_varios(cursor, "SELECT * FROM chamados WHERE usuario_id = %s ORDER BY criado_em", (usuario_id,))
        chamados_atendidos = _buscar_varios(
            cursor,
            """SELECT id, status, categoria, urgencia, equipe_destino, criado_em, atualizado_em,
                      resolvido_em
               FROM chamados WHERE analista_id = %s ORDER BY criado_em""",
            (usuario_id,),
        )
        ids_chamados = [item["id"] for item in chamados_solicitados]
        clausula_ids = ", ".join(["%s"] * len(ids_chamados)) or "NULL"

        mensagens_autoria = _buscar_varios(
            cursor, "SELECT * FROM mensagens_chamado WHERE autor_id = %s ORDER BY criado_em", (usuario_id,)
        )
        mensagens_chamados = _buscar_varios(
            cursor,
            f"SELECT * FROM mensagens_chamado WHERE chamado_id IN ({clausula_ids}) ORDER BY criado_em",
            tuple(ids_chamados),
        ) if ids_chamados else []
        anexos_autoria = _buscar_varios(
            cursor,
            "SELECT id, chamado_id, autor_id, nome_arquivo, tipo_arquivo, conteudo, criado_em FROM anexos_chamado WHERE autor_id = %s ORDER BY criado_em",
            (usuario_id,),
        )
        anexos_chamados = _buscar_varios(
            cursor,
            f"SELECT id, chamado_id, autor_id, nome_arquivo, tipo_arquivo, conteudo, criado_em FROM anexos_chamado WHERE chamado_id IN ({clausula_ids}) ORDER BY criado_em",
            tuple(ids_chamados),
        ) if ids_chamados else []
        pesquisas = _buscar_varios(
            cursor, f"SELECT * FROM pesquisas_satisfacao WHERE chamado_id IN ({clausula_ids}) ORDER BY respondido_em", tuple(ids_chamados)
        ) if ids_chamados else []
        atendimentos_ia = _buscar_varios(
            cursor,
            "SELECT * FROM atendimentos_ia WHERE usuario_id = %s OR chamado_id IN (" + clausula_ids + ") ORDER BY criado_em",
            (usuario_id, *ids_chamados),
        )
        casos_ia = _buscar_varios(
            cursor,
            "SELECT * FROM base_casos_ia WHERE chamado_id IN (" + clausula_ids + ") OR analista_id = %s ORDER BY criado_em",
            (*ids_chamados, usuario_id),
        )
        auditoria = _buscar_varios(
            cursor,
            """SELECT * FROM auditoria
               WHERE usuario_id = %s OR (entidade = 'usuario' AND entidade_id = %s)
               ORDER BY criado_em""",
            (usuario_id, usuario_id),
        )
        codigos = _buscar_varios(
            cursor,
            "SELECT id, usuario_id, tipo, criado_em, expira_em, usado FROM codigos_verificacao WHERE usuario_id = %s ORDER BY criado_em",
            (usuario_id,),
        )

        todos_anexos = {item["id"]: item for item in anexos_autoria + anexos_chamados}
        anexos_metadados = []
        for anexo in todos_anexos.values():
            metadado = {k: v for k, v in anexo.items() if k != "conteudo"}
            anexos_metadados.append(metadado)

        dados = {
            "gerado_em": datetime.now(),
            "escopo": "Dados associados ao titular como solicitante, autor ou analista; chamados atendidos por ele são limitados a metadados para não expor dados de terceiros.",
            "conta": conta,
            "chamados_solicitados": chamados_solicitados,
            "chamados_atendidos_metadados": chamados_atendidos,
            "mensagens_de_autoria": mensagens_autoria,
            "mensagens_dos_chamados_solicitados": mensagens_chamados,
            "anexos": anexos_metadados,
            "pesquisas_satisfacao": pesquisas,
            "atendimentos_ia": atendimentos_ia,
            "casos_ia": casos_ia,
            "auditoria": auditoria,
            "codigos_verificacao_metadados": codigos,
        }
        arquivo = io.BytesIO()
        with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as pacote:
            pacote.writestr("dados.json", json.dumps(dados, ensure_ascii=False, default=_json_seguro, indent=2))
            for anexo in todos_anexos.values():
                nome_seguro = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(anexo["nome_arquivo"])) or "anexo"
                pacote.writestr(f"anexos/{anexo['id']}_{nome_seguro}", anexo["conteudo"])
        _registrar_auditoria(
            cursor, autor_id, "DADOS_TITULAR_EXPORTADOS", "usuario", usuario_id,
            detalhes={"anexos_exportados": len(todos_anexos)},
        )
        conn.commit()
        return arquivo.getvalue()
    finally:
        cursor.close()
        conn.close()


def anonimizar_titular(usuario_id, autor_id=None):
    """Anonimiza dados pessoais sem apagar métricas e eventos operacionais."""
    conn = conectar()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, conta_anonimizada_em FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cursor.fetchone()
        if not usuario:
            raise ValueError("Titular não encontrado.")
        if usuario.get("conta_anonimizada_em"):
            raise ValueError("Este titular já foi anonimizado.")

        cursor.execute("SELECT id FROM chamados WHERE usuario_id = %s", (usuario_id,))
        chamados_solicitados = [item["id"] for item in cursor.fetchall()]
        clausula_ids = ", ".join(["%s"] * len(chamados_solicitados)) or "NULL"
        parametros_ids = tuple(chamados_solicitados)

        cursor.execute("DELETE FROM codigos_verificacao WHERE usuario_id = %s", (usuario_id,))
        codigos_removidos = cursor.rowcount
        cursor.execute(
            "DELETE a FROM anexos_chamado a LEFT JOIN chamados c ON c.id = a.chamado_id "
            "WHERE a.autor_id = %s OR c.usuario_id = %s",
            (usuario_id, usuario_id),
        )
        anexos_removidos = cursor.rowcount
        cursor.execute(
            """UPDATE mensagens_chamado m LEFT JOIN chamados c ON c.id = m.chamado_id
               SET m.mensagem = '[Conteúdo removido por solicitação de privacidade]',
                   m.autor_nome = CASE WHEN m.autor_id = %s THEN 'Titular anonimizado' ELSE m.autor_nome END,
                   m.autor_id = CASE WHEN m.autor_id = %s THEN NULL ELSE m.autor_id END
               WHERE m.autor_id = %s OR c.usuario_id = %s""",
            (usuario_id, usuario_id, usuario_id, usuario_id),
        )
        mensagens_anonimizadas = cursor.rowcount
        cursor.execute(
            f"DELETE FROM base_casos_ia WHERE chamado_id IN ({clausula_ids}) OR analista_id = %s",
            (*parametros_ids, usuario_id),
        )
        casos_removidos = cursor.rowcount
        if chamados_solicitados:
            cursor.execute(f"DELETE FROM pesquisas_satisfacao WHERE chamado_id IN ({clausula_ids})", parametros_ids)
            pesquisas_removidas = cursor.rowcount
            cursor.execute(
                f"""UPDATE atendimentos_ia
                    SET usuario_id = NULL, chamado_id = NULL
                    WHERE usuario_id = %s OR chamado_id IN ({clausula_ids})""",
                (usuario_id, *parametros_ids),
            )
            atendimentos_anonimizados = cursor.rowcount
            cursor.execute(
                f"""UPDATE chamados
                    SET usuario_id = NULL,
                        titulo = '[Conteúdo removido por solicitação de privacidade]',
                        descricao = '[Conteúdo removido por solicitação de privacidade]',
                        motivo_cancelamento = NULL, diagnostico_final = NULL, solucao_final = NULL,
                        compartilhar_conhecimento = FALSE, uso_ia_autorizado_em = NULL
                    WHERE id IN ({clausula_ids})""",
                parametros_ids,
            )
            chamados_anonimizados = cursor.rowcount
        else:
            pesquisas_removidas = atendimentos_anonimizados = chamados_anonimizados = 0

        cursor.execute("UPDATE chamados SET analista_id = NULL WHERE analista_id = %s", (usuario_id,))
        cursor.execute(
            """UPDATE usuarios
                SET nome = 'Titular anonimizado', sobrenome = NULL,
                    email = %s, telefone = NULL, cpf_hash = NULL, departamento = NULL, departamento_id = NULL, cargo = NULL,
                   totp_secret = NULL, senha_deve_ser_redefinida = TRUE,
                   conta_anonimizada_em = %s
               WHERE id = %s""",
            (f"anonimo-{usuario_id}@local.invalid", datetime.now(), usuario_id),
        )
        _registrar_auditoria(
            cursor, autor_id, "DADOS_TITULAR_ANONIMIZADOS", "usuario", usuario_id,
            detalhes={
                "chamados_anonimizados": chamados_anonimizados,
                "mensagens_anonimizadas": mensagens_anonimizadas,
                "anexos_removidos": anexos_removidos,
                "pesquisas_removidas": pesquisas_removidas,
                "casos_ia_removidos": casos_removidos,
                "atendimentos_ia_anonimizados": atendimentos_anonimizados,
                "codigos_removidos": codigos_removidos,
            },
        )
        conn.commit()
        return {
            "chamados": chamados_anonimizados,
            "mensagens": mensagens_anonimizadas,
            "anexos": anexos_removidos,
            "pesquisas": pesquisas_removidas,
            "casos_ia": casos_removidos,
            "atendimentos_ia": atendimentos_anonimizados,
            "codigos": codigos_removidos,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def atualizar_usuario(usuario_id, nome, email, papel, senha_hash=None, sobrenome=None,
                      telefone=None, cpf=None, departamento=None, departamento_id=None, cargo=None, autor_id=None):
    cpf_hash = None
    atualizar_cpf = bool(cpf)
    if atualizar_cpf:
        cpf_normalizado = normalizar_cpf(cpf)
        if not cpf_normalizado:
            raise ValueError("CPF inválido.")
        cpf_hash = _hash_cpf(cpf_normalizado)
    conn = conectar()
    cursor = conn.cursor()
    if senha_hash:
        if atualizar_cpf:
            cursor.execute(
                """UPDATE usuarios SET nome = %s, sobrenome = %s, email = %s, papel = %s,
                   telefone = %s, cpf_hash = %s, departamento = %s, departamento_id = %s, cargo = %s, senha_hash = %s WHERE id = %s""",
                (nome, sobrenome, email, papel, telefone, cpf_hash, departamento, departamento_id, cargo, senha_hash, usuario_id),
            )
        else:
            cursor.execute(
                """UPDATE usuarios SET nome = %s, sobrenome = %s, email = %s, papel = %s,
                   telefone = %s, departamento = %s, departamento_id = %s, cargo = %s, senha_hash = %s WHERE id = %s""",
                (nome, sobrenome, email, papel, telefone, departamento, departamento_id, cargo, senha_hash, usuario_id),
            )
    else:
        if atualizar_cpf:
            cursor.execute(
                """UPDATE usuarios SET nome = %s, sobrenome = %s, email = %s, papel = %s,
                   telefone = %s, cpf_hash = %s, departamento = %s, departamento_id = %s, cargo = %s WHERE id = %s""",
                (nome, sobrenome, email, papel, telefone, cpf_hash, departamento, departamento_id, cargo, usuario_id),
            )
        else:
            cursor.execute(
                """UPDATE usuarios SET nome = %s, sobrenome = %s, email = %s, papel = %s,
                   telefone = %s, departamento = %s, departamento_id = %s, cargo = %s WHERE id = %s""",
                (nome, sobrenome, email, papel, telefone, departamento, departamento_id, cargo, usuario_id),
            )
    linhas_afetadas = cursor.rowcount
    if linhas_afetadas:
        _registrar_auditoria(
            cursor, autor_id, "USUARIO_ATUALIZADO", "usuario", usuario_id,
            detalhes={"papel": papel, "senha_alterada": bool(senha_hash)},
        )
    conn.commit()
    cursor.close()
    conn.close()
    return linhas_afetadas


def excluir_usuario(usuario_id, autor_id=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    linhas_afetadas = cursor.rowcount
    if linhas_afetadas:
        _registrar_auditoria(cursor, autor_id, "USUARIO_EXCLUIDO", "usuario", usuario_id)
    conn.commit()
    cursor.close()
    conn.close()
    return linhas_afetadas


def atualizar_senha(usuario_id, novo_hash_senha, autor_id=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET senha_hash = %s, senha_deve_ser_redefinida = FALSE WHERE id = %s",
        (novo_hash_senha, usuario_id),
    )
    _registrar_auditoria(cursor, autor_id or usuario_id, "SENHA_ALTERADA", "usuario", usuario_id)
    conn.commit()
    cursor.close()
    conn.close()


def salvar_totp_secret(usuario_id, secret, autor_id=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET totp_secret = %s WHERE id = %s", (secret, usuario_id)
    )
    _registrar_auditoria(cursor, autor_id or usuario_id, "TOTP_CONFIGURADO", "usuario", usuario_id)
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
            usado BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.debug("Tabela de códigos de verificação verificada.")


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
    configurar_logging()
    criar_tabela_usuarios()
    migrar_tabela_usuarios()
    criar_tabela_chamados()
    migrar_tabela_chamados()
    criar_tabela_base_casos_ia()
    migrar_tabela_base_casos_ia()
    criar_tabela_codigos()
    criar_tabela_mensagens()
    criar_tabela_anexos()
    criar_tabela_pesquisas_satisfacao()
    criar_tabela_atendimentos_ia()
    migrar_tabela_atendimentos_ia()
    criar_tabela_auditoria()
    criar_tabelas_privacidade()
