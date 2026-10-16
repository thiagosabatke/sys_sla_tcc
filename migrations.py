"""Migrações versionadas do banco.

Uso em uma janela de manutenção (nunca pelo Streamlit):
    python migrations.py upgrade
    python migrations.py status

Cada migração de schema cria uma cópia consistente das tabelas operacionais no
próprio banco antes de executar DDL. O procedimento de restauração está em
DATABASE_OPERATIONS.md.
"""

import argparse
import logging
from datetime import datetime, timezone

import mysql.connector

import database

logger = logging.getLogger(__name__)

TABELAS_PROTEGIDAS = (
    "usuarios", "chamados", "mensagens_chamado", "anexos_chamado",
    "pesquisas_satisfacao", "atendimentos_ia", "base_casos_ia", "auditoria",
    "codigos_verificacao", "aceites_privacidade",
)


def _agora_utc():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _tabela_existe(cursor, nome):
    cursor.execute(
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema = DATABASE() AND table_name = %s""",
        (nome,),
    )
    return cursor.fetchone() is not None


def _preparar_controle(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            versao INT PRIMARY KEY,
            nome VARCHAR(120) NOT NULL,
            aplicado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            backup_prefixo VARCHAR(80) NULL,
            checksum VARCHAR(64) NULL
        )
    """)


def _backup_pre_migracao(conn, versao):
    """Copia tabelas existentes antes de DDL; não substitui backup externo."""
    cursor = conn.cursor()
    prefixo = f"schema_bkp_v{versao}_{_agora_utc()}"
    try:
        for tabela in TABELAS_PROTEGIDAS:
            if not _tabela_existe(cursor, tabela):
                continue
            destino = f"{prefixo}_{tabela}"
            cursor.execute(f"CREATE TABLE `{destino}` LIKE `{tabela}`")
            cursor.execute(f"INSERT INTO `{destino}` SELECT * FROM `{tabela}`")
        conn.commit()
        return prefixo
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def migracao_001_inicial():
    """Provisiona o schema atual em instalações novas."""
    database.criar_tabela_departamentos()
    database.criar_tabelas_rbac()
    database.criar_tabela_usuarios()
    database.criar_tabela_configuracao_sla()
    database.criar_tabela_chamados()
    database.criar_tabela_historico_chamados()
    database.criar_tabela_base_casos_ia()
    database.criar_tabela_codigos()
    database.criar_tabela_mensagens()
    database.criar_tabela_anexos()
    database.criar_tabela_pesquisas_satisfacao()
    database.criar_tabela_atendimentos_ia()
    database.criar_tabela_casos_avaliacao_ia()
    database.criar_tabela_execucoes_avaliacao_ia()
    database.criar_tabela_auditoria()
    database.criar_tabelas_privacidade()


def migracao_002_legado():
    """Evolui instalações anteriores; DDL legado só é executado por este comando."""
    database.migrar_tabela_usuarios()
    database.migrar_usuarios_rbac()
    database.migrar_departamentos_usuarios()
    database.migrar_tabela_chamados()
    database.migrar_tabela_base_casos_ia()
    database.migrar_tabela_codigos()
    database.migrar_tabela_atendimentos_ia()


def _restricao_existe(cursor, nome):
    cursor.execute(
        """SELECT 1 FROM information_schema.table_constraints
           WHERE constraint_schema = DATABASE() AND constraint_name = %s""", (nome,)
    )
    return cursor.fetchone() is not None


def migracao_003_integridade():
    """Restrições que tornam inválidos dados fora do domínio da aplicação."""
    conn = database.conectar(); cursor = conn.cursor()
    restricoes = (
        ("chk_chamados_status", "ALTER TABLE chamados ADD CONSTRAINT chk_chamados_status CHECK (status IN ('Novo','Em Andamento','Em Espera','Resolvido','Fechado','Cancelado'))"),
        ("chk_chamados_urgencia", "ALTER TABLE chamados ADD CONSTRAINT chk_chamados_urgencia CHECK (urgencia IN ('Baixa','Media','Alta','Critica'))"),
        ("chk_pesquisas_nota", "ALTER TABLE pesquisas_satisfacao ADD CONSTRAINT chk_pesquisas_nota CHECK (nota BETWEEN 1 AND 5)"),
        ("chk_codigos_tentativas", "ALTER TABLE codigos_verificacao ADD CONSTRAINT chk_codigos_tentativas CHECK (tentativas >= 0)"),
        ("fk_mensagens_autor", "ALTER TABLE mensagens_chamado ADD CONSTRAINT fk_mensagens_autor FOREIGN KEY (autor_id) REFERENCES usuarios(id) ON DELETE SET NULL"),
    )
    try:
        for nome, comando in restricoes:
            if not _restricao_existe(cursor, nome):
                cursor.execute(comando)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close(); conn.close()


MIGRACOES = (
    (1, "schema_inicial", migracao_001_inicial, False),
    (2, "consolidacao_legado", migracao_002_legado, True),
    (3, "restricoes_de_integridade", migracao_003_integridade, True),
)


def status_migracoes():
    conn = database.conectar()
    cursor = conn.cursor(dictionary=True)
    try:
        if not _tabela_existe(cursor, "schema_migrations"):
            return []
        cursor.execute("SELECT versao, nome, aplicado_em, backup_prefixo FROM schema_migrations ORDER BY versao")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def executar_migracoes():
    conn = database.conectar()
    cursor = conn.cursor(dictionary=True)
    try:
        _preparar_controle(cursor)
        conn.commit()
        cursor.execute("SELECT versao FROM schema_migrations")
        aplicadas = {item["versao"] for item in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    for versao, nome, funcao, exige_backup in MIGRACOES:
        if versao in aplicadas:
            continue
        conn = database.conectar()
        try:
            backup = _backup_pre_migracao(conn, versao) if exige_backup else None
        finally:
            conn.close()
        logger.warning("Aplicando migração %s (%s); backup=%s", versao, nome, backup or "não aplicável")
        funcao()
        conn = database.conectar()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO schema_migrations (versao, nome, backup_prefixo) VALUES (%s, %s, %s)",
                (versao, nome, backup),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()


def schema_pronto():
    """Falha de modo seguro: o app não modifica o banco ao iniciar."""
    conn = database.conectar()
    cursor = conn.cursor()
    try:
        if not _tabela_existe(cursor, "schema_migrations"):
            return False
        cursor.execute("SELECT COALESCE(MAX(versao), 0) FROM schema_migrations")
        return cursor.fetchone()[0] == MIGRACOES[-1][0]
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerenciador de migrações do banco")
    parser.add_argument("acao", choices=("upgrade", "status"))
    args = parser.parse_args()
    if args.acao == "upgrade":
        executar_migracoes()
    else:
        for item in status_migracoes():
            print(f"v{item['versao']} {item['nome']} — {item['aplicado_em']} — backup: {item['backup_prefixo'] or '-'}")
