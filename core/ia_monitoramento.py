"""Acompanha trabalho da IA sem acessar o Streamlit na thread de execução."""

from contextvars import ContextVar
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic


LIMITE_ESPERA_IA = 180
_acompanhamento = ContextVar("acompanhamento_ia", default=None)


class FalhaIA(RuntimeError):
    """Falha com uma mensagem que pode ser apresentada ao solicitante."""


def informar_progresso_ia(etapa, *, recebendo=False):
    acompanhamento = _acompanhamento.get()
    if acompanhamento is not None:
        acompanhamento(etapa, recebendo)


def executar_com_progresso(operacao, atualizar, *, limite_segundos=LIMITE_ESPERA_IA):
    """Impõe um prazo total e descarta resultados tardios após sair da tela."""
    progresso, conclusao = Queue(maxsize=1), Queue(maxsize=1)
    cancelado = Event()
    inicio = monotonic()

    def informar(etapa, recebendo):
        if cancelado.is_set() or monotonic() - inicio >= limite_segundos:
            raise FalhaIA("A IA excedeu o tempo de espera. Tente novamente em instantes.")
        evento = (etapa, recebendo, monotonic())
        try:
            progresso.get_nowait()
        except Empty:
            pass
        try:
            progresso.put_nowait(evento)
        except Full:
            pass

    def executar():
        token = _acompanhamento.set(informar)
        try:
            conclusao.put((True, operacao()))
        except Exception as erro:
            conclusao.put((False, erro))
        finally:
            _acompanhamento.reset(token)

    Thread(target=executar, name="resposta-ia", daemon=True).start()
    etapa, recebendo, ultimo_evento = "Preparando sua solicitação…", False, inicio
    try:
        while True:
            agora = monotonic()
            restante = limite_segundos - (agora - inicio)
            if restante <= 0:
                raise FalhaIA("A IA excedeu o tempo de espera de 3 minutos. Tente novamente em instantes.")
            try:
                etapa, recebendo, ultimo_evento = progresso.get_nowait()
            except Empty:
                pass
            atualizar(etapa, int(agora - inicio), recebendo, max(0, int(agora - ultimo_evento)))
            try:
                sucesso, resultado = conclusao.get(timeout=min(1, restante))
            except Empty:
                continue
            if monotonic() - inicio >= limite_segundos:
                raise FalhaIA("A IA excedeu o tempo de espera. Tente novamente em instantes.")
            if not sucesso:
                raise resultado
            return resultado
    finally:
        cancelado.set()
