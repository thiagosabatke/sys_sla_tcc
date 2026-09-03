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

### Executar a aplicação web

```bash
streamlit run app.py
```

Na primeira execução, a aplicação cria/migra automaticamente as tabelas de
usuários, chamados, mensagens, anexos e pesquisas de satisfação.

## Fluxo implementado

- Usuário: consulta o portal de artigos, conversa com a IA para coleta e
  classificação do chamado, acompanha o histórico, comenta/anexa arquivos,
  cancela chamados ativos e avalia chamados fechados.
- Analista: visualiza a fila com chamados críticos priorizados, assume o
  atendimento, atualiza o status (`Novo`, `Em Andamento`, `Em Espera`,
  `Resolvido` e `Fechado`) e consulta o histórico encerrado.
  Chamados cancelados ficam em uma lista própria, são mantidos para auditoria
  e não entram na taxa de cumprimento de SLA.
- Ciclo de vida: o chamado percorre `Novo → Em Andamento → Em Espera` (quando
  depende do solicitante) `→ Em Andamento → Resolvido`. Após a validação do
  solicitante, ele é `Fechado`; caso a solução não atenda, retorna para `Em
  Andamento`. O solicitante só pode cancelar um chamado em `Novo`, antes de
  ele ser atribuído a um analista, informando o motivo. As transições são
  validadas no banco, não apenas na tela.
- Administrador: cadastra, edita e exclui contas de usuário, analista e admin.

Se `python main.py` rodar sem erro e você ver os chamados classificados
e salvos no banco, o núcleo do protótipo já está funcionando - o resto
(frontend, painel do analista) é construído em cima disso.

## Onde mexer para evoluir
- `base_conhecimento/*.md` — adicione mais categorias e exemplos conforme for testando
- `ia_engine.py` — ajuste o `PROMPT_SISTEMA` se o modelo errar muito a classificação
- `rag.py` — troque `top_k=2` por mais trechos se as respostas vierem sem contexto suficiente
