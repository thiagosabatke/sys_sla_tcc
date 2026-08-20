
import secrets
import io
import bcrypt
import pyotp
import qrcode
from database import buscar_usuario_por_email


def gerar_hash_senha(senha_texto_puro):
    senha_bytes = senha_texto_puro.encode("utf-8")
    hash_bytes = bcrypt.hashpw(senha_bytes, bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_senha(senha_texto_puro, hash_salvo):
    senha_bytes = senha_texto_puro.encode("utf-8")
    hash_bytes = hash_salvo.encode("utf-8")
    return bcrypt.checkpw(senha_bytes, hash_bytes)


def autenticar(email, senha):
    usuario = buscar_usuario_por_email(email)
    if usuario is None:
        return None
    if verificar_senha(senha, usuario["senha_hash"]):
        return usuario
    return None



def gerar_codigo_numerico(digitos=6):
    return "".join(secrets.choice("0123456789") for _ in range(digitos))


def gerar_totp_secret():
    return pyotp.random_base32()


def gerar_qrcode_totp(secret, email, emissor="Sistema Chamados TCC"):

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=emissor)
    imagem = qrcode.make(uri)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def verificar_totp(secret, codigo_digitado):
    totp = pyotp.TOTP(secret)
    return totp.verify(codigo_digitado, valid_window=1)