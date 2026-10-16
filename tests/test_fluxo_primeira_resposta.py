"""Testes do fluxo que libera a resolução após a primeira resposta."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


class CursorResolucao:
    def __init__(self, primeira_resposta=True):
        self.comandos = []
        self.rowcount = 0
        self.primeira_resposta = primeira_resposta

    def execute(self, comando, parametros=None):
        self.comandos.append((comando, parametros))

    def fetchone(self):
        return {
            "status": "Em Espera",
            "analista_id": 7,
            "primeira_resposta_em": self.primeira_resposta,
            "titulo": "Falha de acesso",
            "descricao": "Não consigo entrar no sistema.",
            "categoria_ia": "Acesso",
            "urgencia_ia": "Media",
            "equipe_ia": "Suporte",
            "confiabilidade": "Alta",
            "nome": "Solicitante",
            "sobrenome": "",
            "email": "solicitante@example.com",
            "telefone": "",
        }

    def close(self):
        pass


class ConexaoResolucao:
    def __init__(self, primeira_resposta=True):
        self.cursores = []
        self.primeira_resposta = primeira_resposta

    def cursor(self, **_kwargs):
        cursor = CursorResolucao(self.primeira_resposta)
        self.cursores.append(cursor)
        return cursor

    def commit(self):
        pass

    def close(self):
        pass


class TestesFluxoPrimeiraResposta(unittest.TestCase):
    def test_espera_permite_transicao_para_resolvido(self):
        self.assertIn("Resolvido", database.status_disponiveis("Em Espera"))

    def test_analista_pode_resolver_apos_primeira_resposta_em_espera(self):
        conexao = ConexaoResolucao()
        with patch.object(database, "exigir_permissao"), \
             patch.object(database, "usuario_eh_administrador", return_value=False), \
             patch.object(database, "conectar", return_value=conexao):
            database.registrar_resolucao_chamado(
                1, 7, "Credencial expirada", "Senha redefinida", False,
                "Acesso", "Media", "Suporte",
            )

        atualizacao = conexao.cursores[1].comandos[0][0]
        self.assertIn("status = 'Resolvido'", atualizacao)

    def test_resolucao_sem_primeira_resposta_e_bloqueada(self):
        conexao = ConexaoResolucao(primeira_resposta=None)
        with patch.object(database, "exigir_permissao"), \
             patch.object(database, "usuario_eh_administrador", return_value=False), \
             patch.object(database, "conectar", return_value=conexao):
            with self.assertRaisesRegex(ValueError, "primeira mensagem"):
                database.registrar_resolucao_chamado(
                    1, 7, "Credencial expirada", "Senha redefinida", False,
                    "Acesso", "Media", "Suporte",
                )

        self.assertEqual(len(conexao.cursores), 1)


if __name__ == "__main__":
    unittest.main()
