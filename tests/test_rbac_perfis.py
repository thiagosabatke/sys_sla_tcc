"""Testes sem banco real para as barreiras de autorização do RBAC."""

import sys
import unittest
from types import ModuleType
from unittest.mock import patch

try:
    import mysql.connector
except ModuleNotFoundError:
    mysql = ModuleType("mysql")
    connector = ModuleType("mysql.connector")
    connector.Error = Exception
    mysql.connector = connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = connector

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv

import database


class CursorPerfilAdministrador:
    def __init__(self):
        self.comandos = []

    def execute(self, comando, parametros=None):
        self.comandos.append((comando, parametros))

    def fetchone(self):
        return {"id": 1, "chave": "administrador", "sistema": True}

    def close(self):
        pass


class ConexaoPerfilAdministrador:
    def __init__(self):
        self.cursor_fake = CursorPerfilAdministrador()

    def cursor(self, **_kwargs):
        return self.cursor_fake

    def rollback(self):
        pass

    def close(self):
        pass


class CursorConsultaVazia:
    def execute(self, _comando, _parametros=None):
        pass

    def fetchall(self):
        return []

    def close(self):
        pass


class ConexaoConsultaVazia:
    def cursor(self, **_kwargs):
        return CursorConsultaVazia()

    def close(self):
        pass


class CursorPermissoesAdministrativas:
    def execute(self, _comando, _parametros=None):
        pass

    def fetchall(self):
        return [(7, "departamentos.gerenciar", "Administração")]


class CursorPermissoesAdministrativasComAcesso:
    def execute(self, _comando, _parametros=None):
        pass

    def fetchall(self):
        return [
            (6, "administracao.acessar", "Administração"),
            (7, "departamentos.gerenciar", "Administração"),
        ]


class CursorPermissaoAtendimentoSemFila:
    def execute(self, _comando, _parametros=None):
        pass

    def fetchall(self):
        return [(8, "chamados.assumir", "Chamados")]


class TestesAutorizacaoPerfis(unittest.TestCase):
    def test_matriz_dos_perfis_padrao(self):
        permissoes_administrador = database.PERMISSOES_POR_PERFIL_PADRAO["administrador"]
        todos_os_codigos = {permissao[0] for permissao in database.PERMISSOES_PADRAO_RBAC}

        self.assertEqual(permissoes_administrador, todos_os_codigos)
        self.assertIn("administracao.acessar", permissoes_administrador)
        self.assertIn("perfis.gerenciar", permissoes_administrador)
        self.assertNotIn(
            "administracao.acessar",
            database.PERMISSOES_POR_PERFIL_PADRAO["analista"],
        )
        self.assertNotIn(
            "perfis.gerenciar",
            database.PERMISSOES_POR_PERFIL_PADRAO["usuario"],
        )

    def test_permissao_administrativa_depende_do_acesso_ao_painel(self):
        with self.assertRaises(ValueError):
            database._validar_dependencia_administrativa(
                CursorPermissoesAdministrativas(), {7},
            )

        database._validar_dependencia_administrativa(
            CursorPermissoesAdministrativasComAcesso(), {6, 7},
        )

    def test_acoes_de_atendimento_dependem_do_acesso_a_fila(self):
        with self.assertRaises(ValueError):
            database._validar_dependencia_administrativa(
                CursorPermissaoAtendimentoSemFila(), {8},
            )

    def test_dashboard_pode_ler_dados_sem_liberar_fila_operacional(self):
        with patch.object(database, "usuario_tem_permissao", return_value=True), \
             patch.object(database, "conectar", return_value=ConexaoConsultaVazia()):
            chamados = database.listar_chamados(
                limite=10, executor_id=42, para_relatorio=True,
            )
        self.assertEqual(chamados, [])

    def test_gerenciamento_de_perfis_exige_permissao_especifica(self):
        with patch.object(database, "usuario_tem_permissao", return_value=False):
            with self.assertRaises(PermissionError):
                database.exigir_gerenciamento_perfis(42)

        with patch.object(database, "usuario_tem_permissao", return_value=True):
            database.exigir_gerenciamento_perfis(42)

    def test_operacoes_de_perfil_negam_usuario_sem_permissao_antes_do_banco(self):
        operacoes = (
            (database.listar_permissoes, (42,)),
            (database.listar_perfis, (42,)),
            (database.permissoes_do_perfil, (1, 42)),
            (database.criar_perfil, ("Suporte", "", [], 42)),
            (database.atualizar_perfil, (1, "Suporte", "", True, [], 42)),
            (database.excluir_perfil, (1, 42)),
        )
        with patch.object(database, "usuario_tem_permissao", return_value=False), \
             patch.object(database, "conectar") as conectar:
            for operacao, argumentos in operacoes:
                with self.subTest(operacao=operacao.__name__):
                    with self.assertRaises(PermissionError):
                        operacao(*argumentos)
            conectar.assert_not_called()

    def test_atribuicao_de_perfil_exige_gerenciamento_de_usuarios(self):
        with patch.object(database, "usuario_tem_permissao", return_value=False), \
             patch.object(database, "conectar") as conectar:
            with self.assertRaises(PermissionError):
                database.listar_perfis_para_atribuicao(42)
            conectar.assert_not_called()

    def test_gerente_de_perfis_nao_altera_perfil_administrador(self):
        conexao = ConexaoPerfilAdministrador()
        with patch.object(database, "exigir_gerenciamento_perfis"), \
             patch.object(database, "usuario_eh_administrador", return_value=False), \
             patch.object(database, "conectar", return_value=conexao):
            with self.assertRaises(PermissionError):
                database.atualizar_perfil(1, "Administrador", "", True, [], 42)

        self.assertEqual(len(conexao.cursor_fake.comandos), 1)


if __name__ == "__main__":
    unittest.main()
