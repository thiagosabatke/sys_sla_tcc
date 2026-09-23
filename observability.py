
import logging
import os


def configurar_logging(nivel=None):
    nome_nivel = (nivel or os.getenv("LOG_LEVEL", "INFO")).upper()
    nivel_log = getattr(logging, nome_nivel, logging.INFO)
    logging.basicConfig(
        level=nivel_log,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
