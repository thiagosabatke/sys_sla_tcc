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

### Logs do terminal

Os comandos exibem somente marcos de execução, como indexação da base, classificação,
gravação de chamado, migrações aplicadas e avisos. Para diagnóstico detalhado no
PowerShell, use `$env:LOG_LEVEL="DEBUG"; python main.py`; o nível padrão é `INFO`.
Respostas brutas da IA e senhas não são enviadas ao terminal.

### Auditoria e privacidade

Na primeira execução, o sistema cria a tabela `auditoria`, que registra eventos de
segurança e operações sem armazenar senhas, códigos 2FA, mensagens, anexos ou respostas
brutas da IA. Administradores podem consultar os eventos na aba **Auditoria**.

O aviso e os pontos organizacionais que precisam ser definidos antes de produção estão
em [PRIVACIDADE.md](PRIVACIDADE.md).

### Executar a aplicação web

```bash
streamlit run app.py
```

Na primeira execução, a aplicação cria/migra automaticamente as tabelas de
usuários, chamados, mensagens, anexos, pesquisas de satisfação e auditoria.

## Fluxo implementado

- Usuário: consulta a Central de ajuda e inicia a conversa com uma mensagem
  livre. A IA classifica a intenção: responde dúvidas com apoio da base de
  conhecimento ou inicia a coleta de dados quando identifica um problema.
  A cada mensagem, uma única análise decide se é necessário perguntar, orientar,
  sugerir solução ou preparar o chamado. Quando a base trouxer um procedimento
  aplicável, a IA apresenta uma solução segura ao usuário antes da abertura e registra
  o resultado informado. Caso a orientação não resolva, o usuário revisa os dados e
  confirma a abertura do chamado;
  também pode iniciar uma nova conversa a qualquer momento. O usuário acompanha o histórico, comenta/anexa arquivos,
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
