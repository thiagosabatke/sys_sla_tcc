"""Testes unitários das validações que devem barrar ações antes do banco."""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Permite executar este arquivo diretamente, além do unittest discovery/pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


class TestesValidacoesCriticas(unittest.TestCase):
    def test_chamado_rejeita_classificacao_fora_do_dominio(self):
        with patch.object(database, "exigir_permissao"), \
             patch.object(database, "conectar") as conectar:
            with self.assertRaises(ValueError):
                database.salvar_chamado(
                    "Falha", "Descrição", "Categoria inexistente", "Media",
                    equipe_destino="Suporte", usuario_id=1,
                )
            conectar.assert_not_called()

    def test_anexo_maior_que_limite_e_bloqueado_no_backend(self):
        with patch.object(database, "conectar") as conectar:
            with self.assertRaises(ValueError):
                database.salvar_anexo_chamado(
                    1, 1, "evidencia.log", "text/plain",
                    b"x" * (database.MAX_TAMANHO_ANEXO_BYTES + 1),
                )
            conectar.assert_not_called()

    def test_pesquisa_rejeita_nota_invalida_antes_do_banco(self):
        with patch.object(database, "exigir_permissao"), \
             patch.object(database, "conectar") as conectar:
            with self.assertRaises(ValueError):
                database.salvar_pesquisa_satisfacao(1, 6, "", autor_id=1)
            conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
