"""Progresso real, falhas do serviço e descarte de respostas fora do prazo."""

from threading import Event
import unittest
from unittest.mock import patch

import httpx

from core.ia_monitoramento import (
    FalhaIA, executar_com_progresso, informar_progresso_ia,
)
from ia_engine import _chat_ia


class MonitoramentoIA(unittest.TestCase):
    def test_progresso_isolado_e_resultado_preservado(self):
        liberar = Event()
        atualizacoes = []

        def operacao():
            informar_progresso_ia("Recebendo resposta", recebendo=True)
            self.assertTrue(liberar.wait(5))
            return {"acao": "perguntar", "mensagem": "Qual erro aparece?"}

        def atualizar(*evento):
            atualizacoes.append(evento)
            if evento[2]:
                liberar.set()

        resultado = executar_com_progresso(operacao, atualizar, limite_segundos=5)
        self.assertEqual(resultado["acao"], "perguntar")
        self.assertTrue(any(e[0] == "Recebendo resposta" and e[2] for e in atualizacoes))
        # Fora do trabalho monitorado, não resta callback de outra solicitação.
        informar_progresso_ia("Sem acompanhamento")

    def test_limite_total_nao_aguarda_thread_e_descarta_resultado_tardio(self):
        liberar, terminou, interrompido = Event(), Event(), Event()

        def operacao():
            try:
                liberar.wait(5)
                informar_progresso_ia("Próxima etapa")
            except FalhaIA:
                interrompido.set()
                raise
            finally:
                terminou.set()

        try:
            with self.assertRaises(FalhaIA):
                executar_com_progresso(operacao, lambda *args: None, limite_segundos=0.02)
        finally:
            liberar.set()
        self.assertTrue(terminou.wait(5))
        self.assertTrue(interrompido.is_set())

    def test_erro_da_operacao_chega_a_tela(self):
        def falhar():
            raise FalhaIA("Serviço indisponível")

        with self.assertRaisesRegex(FalhaIA, "Serviço indisponível"):
            executar_com_progresso(falhar, lambda *args: None)


class StreamingIA(unittest.TestCase):
    def test_reconstroi_resposta_completa_e_fecha_fluxo(self):
        fechado = Event()

        def fragmentos():
            try:
                yield {"message": {"thinking": "interno"}, "done": False}
                yield {"message": {"content": '{"acao":'}, "done": False}
                yield {"message": {"content": '"perguntar"}'}, "done": False}
                yield {"message": {"content": ""}, "done": True}
            finally:
                fechado.set()

        with patch("ia_engine.ollama.Client") as cliente, patch("ia_engine.informar_progresso_ia") as progresso:
            cliente.return_value.__enter__.return_value.chat.return_value = fragmentos()
            resultado = _chat_ia(model="teste", messages=[], format="json")
        self.assertEqual(resultado["message"]["content"], '{"acao":"perguntar"}')
        self.assertTrue(fechado.is_set())
        self.assertTrue(any(c.kwargs.get("recebendo") for c in progresso.call_args_list))
        self.assertNotIn("interno", str(progresso.call_args_list))

    def test_fluxo_interrompido_ou_vazio_nao_vira_orientacao(self):
        for itens in ([{"message": {"content": "incompleta"}, "done": False}],
                      [{"message": {"content": ""}, "done": True}]):
            with self.subTest(itens=itens), patch("ia_engine.ollama.Client") as cliente:
                cliente.return_value.__enter__.return_value.chat.return_value = (i for i in itens)
                with self.assertRaisesRegex(FalhaIA, "não concluiu"):
                    _chat_ia(model="teste", messages=[])

    def test_falhas_exibem_mensagem_sem_detalhes_privados(self):
        for erro, mensagem in ((httpx.ReadTimeout("privado"), "tempo demais"),
                               (ConnectionError("privado"), "conectar")):
            with self.subTest(erro=erro), patch("ia_engine.ollama.Client") as cliente:
                cliente.return_value.__enter__.return_value.chat.side_effect = erro
                with self.assertRaisesRegex(FalhaIA, mensagem) as capturado:
                    _chat_ia(model="teste", messages=[])
                self.assertNotIn("privado", str(capturado.exception))


if __name__ == "__main__":
    unittest.main()
