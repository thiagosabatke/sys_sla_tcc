"""Testes puros para validar saídas não confiáveis do modelo."""

import unittest
import sys
from pathlib import Path

# Permite executar este arquivo diretamente no Windows, além de pytest/unittest discovery.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ia_engine import validar_classificacao


class TesteValidacaoDeClassificacao(unittest.TestCase):
    def test_aplica_fallback_independente_para_campos_invalidos(self):
        resultado = validar_classificacao(
            {
                "categoria": "Financeiro", "urgencia": "Urgente", "equipe_destino": "Outra",
                "titulo_resumido": "", "descricao_padronizada": "", "confiabilidade": "100%",
            },
            "Falha no sistema", "O sistema apresenta uma falha ao abrir.",
        )
        self.assertEqual(resultado["categoria"], "Outros")
        self.assertEqual(resultado["urgencia"], "Media")
        self.assertEqual(resultado["equipe_destino"], "Suporte")
        self.assertEqual(resultado["titulo_resumido"], "Falha no sistema")
        self.assertEqual(resultado["descricao_padronizada"], "O sistema apresenta uma falha ao abrir.")
        self.assertEqual(resultado["confiabilidade"], "Baixa")
        self.assertEqual(resultado["tempo_sla_resposta"], "4 horas")

    def test_preserva_campos_validos_e_recalcula_sla_deterministico(self):
        resultado = validar_classificacao(
            {"categoria": "Rede", "urgencia": "Alta", "equipe_destino": "Redes",
             "titulo_resumido": "Sem internet", "descricao_padronizada": "Sem navegação.",
             "confiabilidade": "Alta", "tempo_sla_resposta": "um século"},
            "Original", "Original",
        )
        self.assertEqual(resultado["categoria"], "Rede")
        self.assertEqual(resultado["tempo_sla_resposta"], "1 hora")
        self.assertEqual(resultado["tempo_sla_resolucao"], "8 horas")


if __name__ == "__main__":
    unittest.main()
