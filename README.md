# Sistema de chamados com IA local (protótipo TCC)

## Passo a passo para rodar

### 1. Instalar o Ollama e baixar o modelo
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
```

### 2. Criar o banco no MySQL
No seu MySQL local, rode:
```sql
CREATE DATABASE sistema_chamados;
```

### 3. Configurar o projeto
```bash
# copie o arquivo de exemplo e edite com sua senha do MySQL
cp .env.example .env

# crie um ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\Activate.ps1   # Windows: venv\Scripts\activate

# instale as dependências
pip install -r requirements.txt
```

### 4. Testar cada parte, na ordem
```bash
python database.py     # cria a tabela 'chamados' no MySQL
python rag.py           # testa a busca semântica nos arquivos .md
python ia_engine.py     # testa a classificação completa (RAG + IA)
python main.py           # roda o fluxo completo e grava no banco
```

Se `python main.py` rodar sem erro e você ver os chamados classificados
e salvos no banco, o núcleo do protótipo já está funcionando - o resto
(frontend, painel do analista) é construído em cima disso.

## Onde mexer para evoluir
- `base_conhecimento/*.md` — adicione mais categorias e exemplos conforme for testando
- `ia_engine.py` — ajuste o `PROMPT_SISTEMA` se o modelo errar muito a classificação
- `rag.py` — troque `top_k=2` por mais trechos se as respostas vierem sem contexto suficiente
