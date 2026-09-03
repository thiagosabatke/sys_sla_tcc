import os
import re
import numpy as np
from sentence_transformers import SentenceTransformer

PASTA_BASE = os.path.join(os.path.dirname(__file__), "base_conhecimento")

_modelo_embeddings = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

_trechos = []
_vetores = None

_artigos = {}


def _extrair_frontmatter(conteudo):
    conteudo = conteudo.lstrip("\ufeff")
    if not conteudo.startswith("---"):
        return {}, conteudo

    partes = conteudo.split("---", 2)
    if len(partes) < 3:
        return {}, conteudo

    bloco_meta, corpo = partes[1], partes[2]
    metadados = {}
    for linha in bloco_meta.strip().splitlines():
        if ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        chave = chave.strip().lower()
        valor = valor.strip()
        if chave == "tags":
            metadados["tags"] = [t.strip() for t in valor.split(",") if t.strip()]
        else:
            metadados[chave] = valor

    return metadados, corpo.lstrip("\n")


def _dividir_em_secoes(corpo):
    partes = re.split(r"(?=^##\s)", corpo, flags=re.MULTILINE)
    abertura = partes[0].strip() if partes else ""
    secoes = [p.strip() for p in partes[1:] if p.strip()]
    if not secoes and abertura:
        secoes = [abertura]
    return abertura, secoes


def carregar_base():
    global _trechos, _vetores, _artigos

    _trechos = []
    _artigos = {}

    if not os.path.isdir(PASTA_BASE):
        print("Pasta base_conhecimento/ não encontrada.")
        return

    for nome_arquivo in sorted(os.listdir(PASTA_BASE)):
        if not nome_arquivo.endswith(".md"):
            continue

        caminho = os.path.join(PASTA_BASE, nome_arquivo)
        with open(caminho, "r", encoding="utf-8") as f:
            bruto = f.read()

        metadados, corpo = _extrair_frontmatter(bruto)
        titulo = metadados.get("titulo") or nome_arquivo.replace(".md", "").replace("_", " ").title()
        categoria = metadados.get("categoria", "Outros")
        resumo = metadados.get("resumo", "")
        tags = metadados.get("tags", [])

        abertura, secoes = _dividir_em_secoes(corpo)

        _artigos[nome_arquivo] = {
            "arquivo": nome_arquivo,
            "titulo": titulo,
            "categoria": categoria,
            "resumo": resumo,
            "tags": tags,
            "corpo": corpo.strip(),
        }

        cabecalho_busca = (
            f"{titulo}\n"
            f"Categoria: {categoria}\n"
            f"Palavras-chave: {', '.join(tags)}\n"
            f"Resumo: {resumo}"
        ).strip()

        for secao in secoes:
            texto_para_embedding = f"{cabecalho_busca}\n\n{secao}".strip()
            _trechos.append({
                "arquivo": nome_arquivo,
                "texto_embedding": texto_para_embedding,
            })

    if _trechos:
        textos = [t["texto_embedding"] for t in _trechos]
        _vetores = _modelo_embeddings.encode(textos)
        print(f"Base de conhecimento carregada: {len(_artigos)} artigo(s), {len(_trechos)} trecho(s) indexados.")
    else:
        _vetores = None
        print("Nenhum artigo .md encontrado em base_conhecimento/.")


def _similaridade_cosseno(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def buscar_contexto(texto_chamado, top_k=3):


    if _vetores is None:
        carregar_base()
        if _vetores is None:
            return []

    vetor_chamado = _modelo_embeddings.encode([texto_chamado])[0]

    similaridades = [
        _similaridade_cosseno(vetor_chamado, doc_vetor)
        for doc_vetor in _vetores
    ]

    indices_ordenados = np.argsort(similaridades)[::-1]

    resultados = []
    arquivos_incluidos = set()
    for i in indices_ordenados:
        arquivo = _trechos[i]["arquivo"]
        if arquivo in arquivos_incluidos:
            continue
        arquivos_incluidos.add(arquivo)

        artigo = _artigos[arquivo]
        resultados.append({
            "arquivo": arquivo,
            "titulo": artigo["titulo"],
            "categoria": artigo["categoria"],
            "conteudo": artigo["corpo"],
            "similaridade": float(similaridades[i]),
        })

        if len(resultados) >= top_k:
            break

    return resultados


def listar_artigos():
    if not _artigos:
        carregar_base()
    return sorted(_artigos.values(), key=lambda a: a["titulo"])


if __name__ == "__main__":
    carregar_base()
    exemplo = "não consigo acessar a internet no meu computador"
    resultados = buscar_contexto(exemplo)
    for r in resultados:
        print(f"\nArquivo: {r['arquivo']} — {r['titulo']} (similaridade: {r['similaridade']:.2f})")
        print(r["conteudo"][:150], "...")