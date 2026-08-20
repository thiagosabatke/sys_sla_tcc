import os
import numpy as np
from sentence_transformers import SentenceTransformer

PASTA_BASE = os.path.join(os.path.dirname(__file__), "base_conhecimento")

_modelo_embeddings = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

_documentos = []       
_vetores = None        


def carregar_base():
    global _documentos, _nomes_arquivos, _vetores

    _documentos = []
    _nomes_arquivos = []

    for nome_arquivo in os.listdir(PASTA_BASE):
        if nome_arquivo.endswith(".md"):
            caminho = os.path.join(PASTA_BASE, nome_arquivo)
            with open(caminho, "r", encoding="utf-8") as f:
                conteudo = f.read()
            _documentos.append(conteudo)
            _nomes_arquivos.append(nome_arquivo)

    if _documentos:
        _vetores = _modelo_embeddings.encode(_documentos)
        print(f"Base de conhecimento carregada: {len(_documentos)} arquivo(s).")
    else:
        print("Nenhum arquivo .md encontrado em base_conhecimento/.")


def _similaridade_cosseno(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def buscar_contexto(texto_chamado, top_k=2):

    if _vetores is None:
        carregar_base()

    vetor_chamado = _modelo_embeddings.encode([texto_chamado])[0]

    similaridades = [
        _similaridade_cosseno(vetor_chamado, doc_vetor)
        for doc_vetor in _vetores
    ]

    indices_ordenados = np.argsort(similaridades)[::-1][:top_k]

    resultados = []
    for i in indices_ordenados:
        resultados.append({
            "arquivo": _nomes_arquivos[i],
            "conteudo": _documentos[i],
            "similaridade": float(similaridades[i]),
        })
    return resultados


if __name__ == "__main__":
    carregar_base()
    exemplo = "não consigo acessar a internet no meu computador"
    resultados = buscar_contexto(exemplo)
    for r in resultados:
        print(f"\nArquivo: {r['arquivo']} (similaridade: {r['similaridade']:.2f})")
        print(r["conteudo"][:150], "...")
