import os
import smtplib
import logging
from email.mime.text import MIMEText
from dotenv import load_dotenv
from observability import configurar_logging

logger = logging.getLogger(__name__)

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def enviar_email(destinatario, assunto, corpo):
    msg = MIMEText(corpo)
    msg["Subject"] = assunto
    msg["From"] = SMTP_FROM
    msg["To"] = destinatario

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(SMTP_USER, SMTP_PASSWORD)
        servidor.sendmail(SMTP_FROM, destinatario, msg.as_string())


if __name__ == "__main__":
    configurar_logging()
    destino = input("Digite um e-mail para receber o teste: ")
    enviar_email(destino, "Teste - Sistema de Chamados", "Se você recebeu isso, o SMTP está funcionando.")
    logger.info("E-mail de teste enviado; verifique a caixa de entrada e o spam.")
