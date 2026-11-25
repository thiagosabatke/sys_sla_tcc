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

Na conversa, o painel da IA informa a etapa atual, o tempo de espera e quando
fragmentos da resposta estão sendo recebidos. Após 30 segundos sem atualização,
avisa sobre a demora. A espera total é limitada a três minutos; falhas de conexão,
indisponibilidade e interrupções da resposta mostram uma orientação e o botão
**Tentar novamente**, preservando a mensagem e o histórico. Cada conexão tem
limite de 5 segundos e cada espera por novos dados, de 60 segundos. Nenhum chamado
é aberto por uma falha ou pelo botão de tentar novamente.

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

A aplicação verifica o esquema ao iniciar. As migrações são executadas separadamente,
conforme [DATABASE_OPERATIONS.md](DATABASE_OPERATIONS.md), com backup e janela de manutenção.

## Organização da interface

As entradas existentes compõem as telas de `pages/_telas.py`, com componentes em
`ui/` e regras de navegação e sessão em `core/`. O destino inicial depende das
permissões efetivas; os temas claro e escuro usam o estilo nativo do Streamlit.
Consulte a [análise da refatoração de UI/UX](docs/REFATORACAO_UI_UX.md) para decisões,
testes e limitações de validação.

Após editar arquivos Python, reinicie o aplicativo pelo BAT. O observador automático
de módulos está desativado para evitar que o Streamlit tente carregar dependências
multimodais opcionais do `transformers`, que não são usadas neste sistema.

Nos dashboards, o período de abertura oferece **Último mês** (30 dias), **Última
semana** (7 dias), **Último dia** (24 horas), **Intervalo de datas** (da data inicial
à final, incluindo os dois dias completos) e **Até agora** (sem data inicial,
até o momento atual), no horário de São Paulo. A consulta carrega todas as páginas de
chamados, sem o corte anterior de 5.000 registros. Categoria, urgência e situação podem ser combinadas nos
filtros visíveis; **Limpar filtros** restaura o último mês e o escopo de backlog.
O mesmo recorte alimenta Executivo, Visão geral e Operação e SLA. Pessoas considera
o cadastro atual; IA e conhecimento identifica o escopo de suas próprias métricas.
Os dashboards abrem em **Backlog do período**: somente novos, em andamento, em
espera e resolvidos aguardando confirmação, abertos nas datas escolhidas. Use essa
visão para distribuir trabalho e agir sobre riscos e violações. Gráficos e tabelas
não mostram colunas de finalizados; a carga por analista destaca pendências,
violações, risco e confirmações aguardadas.

Selecione **Tudo no período** para analisar volume histórico e produtividade,
incluindo fechados e cancelados, com a legenda **Ativos → Cancelados → Fechados**.
Cada tabela e gráfico identifica o escopo, inclusive os recortes exclusivos de
backlog ou cancelamentos. Para todo o histórico, combine **Tudo no período** com
**Até agora**. Listas detalhadas e matrizes ficam recolhidas em consultas opcionais.
Fechados com SLA violado não entram nas prioridades imediatas da operação.
Cadastros de pessoas e bases globais da IA têm identificação própria; a visão
Pessoas não apresenta filtros de chamados. O Atendimento continua com fila ativa,
histórico de fechados e cancelados em áreas separadas.

No Atendimento, **Histórico (fechados)** apresenta cards compactos e busca por
número, título ou solicitante. Use **Anterior**, **Próxima** ou o número da página
no rodapé para consultar chamados mais antigos, cinco por vez. O histórico carrega
todos os fechados autorizados; **Ver detalhes** abre o registro completo sem perder
a página atual. Os indicadores de SLA continuam disponíveis em um expansor.

Administradores podem usar **Administração → Dashboards → Chamados de demonstração**
para adicionar lotes de 12 a 500 chamados (padrão: 120) ou remover as demonstrações.
Os exemplos usam os usuários, permissões e departamentos atuais, sem alterar os
cadastros, e incluem mensagens, histórico e avaliações. Há registros recentes e
antigos, até 90 dias. A quantidade de ativos respeita o limite por solicitante e
reserva uma vaga para uma solicitação real; os demais exemplos ficam no histórico.
Novos lotes são acrescentados aos existentes. A remoção exige o marcador interno
e a indicação de dado sintético, apaga os dados dependentes desses chamados e
preserva os chamados reais e a auditoria.

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
- Aprendizado por casos: ao resolver um chamado, o analista informa o diagnóstico e a solução aplicada. Se autorizar o compartilhamento e o solicitante confirmar a resolução, o chamado é copiado para a tabela `base_casos_ia`. Somente essa tabela de casos validados é usada pela IA como experiência operacional; chamados, conversas e respostas não confirmadas nunca são usados como conhecimento.

Se `python main.py` rodar sem erro e você ver os chamados classificados
e salvos no banco, o núcleo do protótipo já está funcionando - o resto
(frontend, painel do analista) é construído em cima disso.

## Onde mexer para evoluir
- `base_conhecimento/*.md` — adicione mais categorias e exemplos conforme for testando
- `ia_engine.py` — ajuste o `PROMPT_SISTEMA` se o modelo errar muito a classificação
- `rag.py` — troque `top_k=2` por mais trechos se as respostas vierem sem contexto suficiente
