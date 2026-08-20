# Projeto TCC — Sistema de Chamados com IA Local

## O que é o projeto

TCC sobre um sistema de gerenciamento de chamados de TI que usa **IA rodando localmente**
(sem depender de API paga/nuvem) para interpretar a descrição do usuário, classificar o
chamado (categoria, urgência, SLA, equipe responsável) e apoiar a triagem do analista.

**Pivô importante feito no meio do projeto:** a ideia original do TCC era um sistema com
PLN clássico (TF-IDF + ML) e arquitetura de microsserviços (React + Node/Python + MySQL).
Foi trocado para uma abordagem mais simples e moderna: **LLM local via Ollama + RAG**,
tudo em Python, rodando em processo único (sem microsserviços, sem VM, sem Flask separado
— decisões deliberadas para caber no prazo).

## Stack definida

| Camada | Tecnologia | Observação |
|---|---|---|
| Frontend + Backend | **Streamlit** (Python puro) | Um único app.py, sem Flask/API separada |
| Motor de IA | **Ollama** + **Qwen2.5:3b** | Roda 100% local, sem chamada externa |
| RAG | Embeddings próprios (`sentence-transformers`, modelo multilíngue) + busca por similaridade em `numpy` | Sem ChromaDB/FAISS — simplicidade proposital |
| Base de conhecimento | Arquivos `.md` em `base_conhecimento/` | Curadoria manual, alimenta o RAG |
| Banco de dados | MySQL | Tabelas: `chamados`, `usuarios`, `codigos_verificacao` |
| Autenticação | bcrypt (hash de senha) + 2FA (e-mail/TOTP) | Só admin tem 2FA obrigatório |
| E-mail | SMTP real (Gmail com senha de app) | Usado no "esqueci senha" |

## Ambiente de desenvolvimento (Windows) — detalhes que já causaram dor de cabeça

- **Python 3.11** instalado (trocado de uma versão mais nova por recomendação de compatibilidade com libs de IA)
- **Sem venv** — decisão deliberada, para simplificar (projeto único nessa máquina)
- Comando `python`/`pip` sozinhos **não funcionam** no terminal do usuário (problema de PATH do Windows) — usar sempre:
  - `py -3.11 arquivo.py` para rodar scripts
  - `py -3.11 -m pip install pacote` para instalar
  - `py -3.11 -m streamlit run app.py` para rodar o Streamlit
- MySQL: usar `DB_HOST=127.0.0.1` no `.env` (não `localhost` — dava erro de named pipe)
- Existe um `.bat` que já funciona, rodando `py -3.11 -m streamlit run app.py` (abre o navegador automaticamente)

## Estrutura de arquivos

```
projeto_tcc/
  app.py                 <- Streamlit: login + 3 telas por perfil (usuario/analista/admin)
  sla.py                   <- NOVO: motor de cálculo de SLA (prazos, status, pausa de relógio)
  ia_engine.py               <- Toda a lógica de IA: classificação final + chat de coleta
  rag.py                       <- Busca semântica nos .md (usado tanto na classificação quanto no chat)
  database.py                    <- Todas as funções de banco (chamados, usuarios, códigos, SLA)
  auth.py                          <- Hash de senha, TOTP (autenticador), geração de código
  email_utils.py                     <- Envio de e-mail real via SMTP
  seed_usuarios.py                     <- Cria os 3 usuários de teste (rodar 1x)
  main.py                                <- Script de teste antigo (fluxo sem chat, sem login) — só para debug isolado
  base_conhecimento/
    hardware.md, rede.md, software.md
  .env                                     <- Credenciais (não versionar/compartilhar)
  requirements.txt
```

## Como rodar (rotina padrão)

```powershell
cd Desktop\projeto_tcc
py -3.11 -m streamlit run app.py
```

Se mudou `database.py`, `auth.py` ou qualquer módulo importado (não só `app.py`), **precisa
reiniciar o Streamlit** (Ctrl+C e rodar de novo) — ele só recarrega sozinho o `app.py`.

**Depois de atualizar `database.py` com as colunas de SLA (ver changelog abaixo), rode uma vez
antes de subir o Streamlit**, para o `atualizar_tabela()` criar as colunas novas no MySQL:

```powershell
py -3.11 database.py
```

## Funcionalidades já implementadas e testadas

- [x] Classificação de chamado via LLM local (categoria, urgência, SLA de resposta/resolução
      com matriz fixa no prompt, equipe destino, confiabilidade como autoavaliação qualitativa)
- [x] RAG puxando contexto da base de conhecimento markdown
- [x] Login com senha criptografada (bcrypt)
- [x] 3 perfis: usuario, analista, admin — cada um com tela própria
- [x] Usuário vê só os próprios chamados; analista vê todos
- [x] Analista pode filtrar por status e urgência, atender (assignment) e mudar status do chamado
- [x] Admin pode cadastrar novos usuários (acesso restrito)
- [x] **UI redesenhada (telas por perfil) — CSS próprio (cards, badges de status/urgência,
      cabeçalho com gradiente), sem alterar `ia_engine.py`/`rag.py`/`auth.py`/`email_utils.py`:**
  - Tela do **usuário**: separada em abas — "Abrir novo chamado" (chat com a IA, como já era)
    e "Meus chamados" (lista em cards, com histórico de conversa por chamado)
  - Tela do **analista**: reformulada como workbench de service desk alinhado a **ITIL 4**
    (gestão de incidentes) — métricas no topo (total/novos/em andamento/atribuídos a mim),
    filtros, fila de chamados + painel de detalhe, botão "Atender chamado" (assignment),
    dropdown de status seguindo o ciclo de vida do incidente, chat com o solicitante
  - Tela **administrativa**: reorganizada em abas (Listar / Cadastrar / Editar / Excluir)
    com métricas no topo, em vez de tudo empilhado verticalmente
- [x] **Conversa persistida por chamado** (novidade): tabela `mensagens_chamado` — usuário e
      analista trocam mensagens dentro do próprio chamado (não é mais só o chat inicial de
      coleta da IA); usado nas duas telas via `painel_conversa_chamado()`
- [x] **Status do chamado migrado para nomenclatura ITIL 4** (incident lifecycle):
      `Novo → Em Andamento → Em Espera → Resolvido → Fechado` (antes era só
      Aberto/Em Andamento/Resolvido)
- [x] "Esqueci minha senha" com código real por e-mail (SMTP/Gmail)
- [x] 2FA (e-mail ou app autenticador/TOTP) **só obrigatório para o perfil admin**
- [x] Tela do usuário é um **chat** (não formulário fixo): a IA faz perguntas adaptadas
      ao problema relatado (usa RAG pra saber o que perguntar), até ter dado suficiente
      pra abrir o chamado sozinha — limite de 6 turnos pra evitar loop infinito
- [x] Prompt do chat instruído a não concordar automaticamente com tudo (evitar sycophancy) —
      questiona contradições/inconsistências antes de aceitar como fato
- [x] Fallback: se o modelo não devolver JSON válido, usa o texto bruto dele como pergunta
      em vez de mostrar uma mensagem genérica (o modelo geralmente já pergunta certo, só
      esquece de embrulhar em JSON)
- [x] **Correção de bug visual**: título dos cards de chamado ficava branco em cima de fundo
      branco (`.card-title` herdava a cor do tema do Streamlit em vez de ter cor própria) —
      corrigido fixando `color: #0f172a` em `.card` e `.card-title`
- [x] **Motor de SLA real, alinhado a ITIL 4 (novo módulo `sla.py`)** — antes o "SLA" era só
      um texto solto vindo da IA (ex: "4 horas"), sem prazo, contagem ou violação de verdade:
  - Matriz de prazos em minutos por urgência (Crítica/Alta/Média/Baixa), calculados e
    gravados no banco (`prazo_resposta`, `prazo_resolucao`) no momento da abertura do chamado
  - Relógio de **resposta** (tempo até a 1ª mensagem do analista no chamado) e de
    **resolução** (tempo até o status virar Resolvido/Fechado), tratados como métricas
    independentes — igual OLA/SLA de resposta x resolução do ITIL 4
  - Status dinâmico de cada métrica: `Dentro do prazo` / `Em risco` (a partir de 80% do
    tempo consumido) / `Violado` / `Cumprido` / `Pausado`
  - **Pausa do relógio de SLA**: ao mudar o status para `Em Espera` (aguardando o
    solicitante), o relógio para de contar; ao sair de `Em Espera`, o tempo pausado é
    somado e descontado do prazo — prática padrão do ITIL 4 para não penalizar o analista
    por tempo de espera do lado do cliente
  - Novas colunas em `chamados`: `prazo_resposta`, `prazo_resolucao`,
    `primeira_resposta_em`, `resolvido_em`, `pausado_em`, `tempo_pausado_min`
  - `primeira_resposta_em` é preenchida automaticamente na primeira mensagem do analista
    no chamado (`enviar_mensagem_chamado`); `resolvido_em`/pausa são geridos em
    `atualizar_status_chamado`
  - Badges coloridos de SLA (verde/amarelo/vermelho/roxo) nos cards e no painel de detalhe,
    com prazo formatado, tempo restante ou "atrasado há Xh", em ambas as telas
    (usuário e analista); borda lateral colorida nos cards conforme o pior status entre
    resposta e resolução
- [x] **Fila Ativa x Histórico na tela do analista (separação por ciclo de vida ITIL 4)**:
      antes todos os chamados (inclusive fechados) ficavam juntos na mesma fila, e o
      chamado continuava atribuído ao analista para sempre (isso é correto — é o "owner"
      do registro, usado para histórico e métricas —, mas não devia poluir a fila de
      trabalho). Agora a tela do analista tem 2 abas:
  - **📥 Fila Ativa**: só chamados com status diferente de `Fechado` — é onde o analista
    trabalha (atender, conversar, mudar status); ao salvar status como `Fechado`, o
    chamado sai da fila e a seleção é limpa automaticamente
  - **🗂️ Histórico (Fechados)**: só chamados `Fechado`, somente consulta (sem opção de
    mudar status, já que fechado é estado final do ciclo de vida) — mostra métricas de
    taxa de cumprimento de SLA, filtro "somente atendidos por mim", datas de
    abertura/resolução e o histórico da conversa; pensado como repositório de
    auditoria/relatório de desempenho, prática recomendada pelo ITIL 4

## Limitações conhecidas (documentar no TCC como tal)

- Modelo de 3B ocasionalmente esquece campos do JSON pedido ou foge do formato — tratado
  com valores padrão (`.setdefault`) e fallback, mas é uma limitação real do modelo pequeno,
  vale mencionar nos Resultados
- Campo "confiabilidade" é autoavaliação textual do modelo, **não é métrica estatística
  calculada** — importante deixar isso claro na escrita do TCC
- Sem proteção real contra acesso direto às funções de tela por manipulação de sessão
  (aceitável para escopo de protótipo/TCC)
- Migração de status é automática e idempotente (`atualizar_tabela()` roda no início do
  `app.py`), mas chamados antigos gravados como `"Aberto"` continuam com esse valor no banco
  (o código trata como status desconhecido e cai no primeiro item do select) — se quiser
  unificar visualmente, rodar um `UPDATE chamados SET status = 'Novo' WHERE status = 'Aberto'`
  manual
- Conversa em `mensagens_chamado` não tem paginação nem marcação de lida/não lida — para o
  volume de um protótipo de TCC não é um problema, mas vale citar como limitação/trabalho
  futuro
- O relógio de SLA considera **24/7 corrido** (sem calendário de horário comercial/plantão).
  ITIL 4 permite tanto SLA 24/7 quanto por janela de atendimento (ex: 9h-18h em dias úteis);
  para este protótipo foi escolhido 24/7 por simplicidade — vale citar como decisão de
  escopo e possível trabalho futuro (calendário de expediente)
- Chamados abertos **antes** da migração de SLA ficam com `prazo_resposta`/`prazo_resolucao`
  nulos (não é possível calcular retroativamente sem saber o `criado_em` correto na hora do
  cálculo) — só chamados abertos depois da migração têm o relógio de SLA completo
- O status "Em risco" usa um limiar fixo de 80% do tempo decorrido; não é configurável pela
  interface (fica hardcoded em `sla.LIMIAR_RISCO`) — suficiente para o protótipo, mas seria
  candidato a virar parâmetro configurável num sistema de produção

## Cronograma original (13 semanas / 7 sprints) — status

1. **Sprint 1-2 (setup + classificação básica)** ✅ concluído
2. **Sprint 2-3 (base de conhecimento + RAG)** ✅ concluído
3. **Sprint 3 (integração + prompt)** ✅ concluído, prompt evoluiu bastante (SLA, mapeamento
   categoria/equipe, few-shot, depois virou chat adaptativo)
4. **Sprint 4 (interface)** ✅ concluído e **ampliado além do planejado originalmente**
   (que previa só formulário simples): login, 3 telas por perfil, chat de coleta com IA,
   UI redesenhada (abas, cards, badges), fluxo de atendimento estilo ITIL 4 no analista
   (assignment + ciclo de vida do incidente), conversa persistida por chamado, **motor de
   SLA completo com prazos/violação/pausa de relógio** e **separação Fila Ativa x Histórico**
5. **Sprint 5 (testes e métricas de acurácia)** ⬜ ainda não iniciado — próximo passo real
6. **Sprint 6 (documentação do TCC)** ⬜ pendente — o texto do TCC ainda reflete a
   arquitetura ANTIGA (React/Node/microsserviços/TF-IDF), precisa reescrever Metodologia,
   Arquitetura e Resultados para refletir o que foi construído de fato
7. **Buffer** ⬜

## Histórico de mudanças recentes

- **Limpeza do schema de `chamados` e `usuarios` (`database.py`)**: as colunas
  `titulo_resumido`/`descricao_padronizada` foram removidas — elas não guardavam o texto
  "original" do usuário, e sim uma segunda versão gerada pela IA (a classificação refinava
  o mesmo título/descrição que já vinham refinados do chat de coleta), e o `app.py` tinha
  o fallback `titulo_resumido or titulo` espalhado em vários pontos só para escolher a
  melhor versão na hora de exibir. Agora `salvar_chamado()` já recebe título/descrição
  finais (a versão refinada da IA quando existe, senão a do chat) e grava só uma vez.
  Outras mudanças de organização:
  - `usuarios` criada antes de `chamados`, e `chamados.usuario_id`/`analista_id` ganharam
    FOREIGN KEY para `usuarios(id)` (antes não havia integridade referencial nenhuma)
  - `totp_secret` passou a fazer parte da criação de `usuarios` (era só uma migração solta)
  - Colunas de `chamados` reagrupadas por finalidade no `CREATE TABLE`: conteúdo,
    classificação da IA, relacionamentos, ciclo de vida, controle de SLA
  - Funções renomeadas para o padrão `criar_tabela_<entidade>()` /
    `migrar_tabela_<entidade>()` em todo o arquivo (antes só `chamados` fugia do padrão,
    com `criar_tabela()`/`atualizar_tabela()`)
  - `migrar_tabela_chamados()` (antes `atualizar_tabela()`) faz a migração de bancos já
    existentes: copia `titulo_resumido`→`titulo` e `descricao_padronizada`→`descricao`
    antes de remover as colunas antigas (não perde chamados já cadastrados), e tenta
    adicionar as FKs sem quebrar o banco caso haja `usuario_id`/`analista_id` órfãos
  - `app.py` e `main.py` atualizados para o novo schema/assinatura de `salvar_chamado()`

- **Repaginação das 3 telas + conversa por chamado (ITIL 4)**: reescrito `app.py` (CSS
  próprio, cards, badges de status/urgência) e `database.py` (sem tocar em `ia_engine.py`,
  `rag.py`, `auth.py`, `email_utils.py`). Principais mudanças:
  - Tela do usuário dividida em abas: chat de abertura x lista "Meus chamados"
  - Tela do analista virou um workbench (fila + detalhe + assignment + chat + status ITIL)
  - Tela admin reorganizada em 4 abas com métricas no topo
  - Novo campo `chamados.analista_id` (quem está atendendo, via `atribuir_chamado()`)
  - Nova tabela `mensagens_chamado` (thread de conversa usuário↔analista por chamado, via
    `enviar_mensagem_chamado()` / `listar_mensagens_chamado()`)
  - Status passou de `Aberto/Em Andamento/Resolvido` para o ciclo ITIL 4 de incidente:
    `Novo/Em Andamento/Em Espera/Resolvido/Fechado`
- **RAG no chat de coleta**: busca por similaridade roda a cada mensagem do usuário
  (não só na primeira), usando tudo que ele já escreveu até aquele ponto
- **Correção de bug crítico**: o chat nunca abria o chamado, ficava em loop de perguntas.
  Causa: quando o JSON do modelo falhava, o código sempre tratava como "perguntar" —
  mesmo no modo forçado (`forcar_finalizar=True`, acionado a partir do 6º turno). Corrigido
  para: (1) tentar extrair JSON de dentro de texto solto antes de desistir
  (`_extrair_json()`), e (2) no modo forçado, se mesmo assim não vier JSON, montar o
  fechamento do chamado manualmente em vez de continuar perguntando
- **Correção de bug visual (cards ilegíveis)**: `.card-title` não tinha cor de texto
  própria e herdava o tema do Streamlit, ficando branco em cima do fundo branco do
  `.card`. Corrigido fixando `color: #0f172a` nas duas classes em `app.py`
- **Motor de SLA completo, alinhado a ITIL 4 (novo `sla.py` + mudanças em `database.py`
  e `app.py`)**: antes o "SLA" era só um texto vindo da IA (ex: "4 horas"), sem prazo real,
  contagem ou violação. Agora:
  - `sla.py` calcula prazo de resposta e de resolução em cima da matriz de urgência,
    avalia status (`Dentro do prazo`/`Em risco`/`Violado`/`Cumprido`/`Pausado`) e formata
    tempo restante/atraso
  - `database.py`: novas colunas (`prazo_resposta`, `prazo_resolucao`,
    `primeira_resposta_em`, `resolvido_em`, `pausado_em`, `tempo_pausado_min`);
    `salvar_chamado()` grava os prazos calculados na abertura; `atualizar_status_chamado()`
    ganhou lógica de pausar/retomar o relógio ao entrar/sair de `Em Espera` e de marcar
    `resolvido_em`; `enviar_mensagem_chamado()` grava `primeira_resposta_em` automaticamente
    na 1ª mensagem do analista
  - `app.py`: badges de SLA coloridos (verde/amarelo/vermelho/roxo/azul) nos cards e no
    detalhe, borda lateral colorida nos cards pelo pior status, bloco de detalhe com prazo,
    tempo restante/atraso e explicação da pausa — nas telas de usuário e analista
- **Fila Ativa x Histórico na tela do analista**: o `analista_id` continua preenchido para
  sempre no chamado fechado (correto — é o "owner" do registro, usado para métricas e
  reabertura), mas isso poluía a fila de trabalho. `tela_analista()` foi dividida em
  `_aba_fila_ativa_analista()` (chamados não-fechados, com todo o fluxo de atendimento) e
  `_aba_historico_analista()` (só fechados, somente consulta, com taxa de cumprimento de
  SLA e filtro "somente atendidos por mim") — reflete a separação do ITIL 4 entre fila
  operacional e registros encerrados/auditoria

## Próximos passos sugeridos (em ordem)

1. Rodar `py -3.11 database.py` uma vez para migrar as colunas novas de SLA no MySQL, depois
   subir o app (`py -3.11 -m streamlit run app.py`) e conferir na prática: badges de SLA nos
   cards, pausa do relógio ao mudar para "Em Espera", e a separação Fila Ativa x Histórico
   na tela do analista
2. Testar bastante o chat de coleta com casos variados e ambíguos, ajustar prompt conforme
   os erros aparecerem
3. Montar um conjunto de ~30-50 casos de teste com classificação esperada conhecida, para
   medir % de acerto (isso é o que falta para o capítulo de Resultados ter números reais)
4. Reescrever as seções do TCC (Arquitetura, Metodologia, Resultados) refletindo a stack
   real usada, não a original — **agora incluindo o alinhamento a ITIL 4** na gestão de
   incidentes (assignment do analista, ciclo de vida de status, motor de SLA com prazo/
   violação/pausa de relógio, separação fila ativa x histórico) como diferencial do projeto
5. Considerar calendário de horário comercial para o cálculo de SLA (hoje é 24/7 corrido) —
   citar como decisão de escopo ou implementar se sobrar tempo
6. Polimento final (tratar avisos do Streamlit tipo `use_container_width`, revisar UX)

## Como retomar em um novo chat

Cole este arquivo inteiro como contexto inicial. Se for pedir ajuda em algo específico,
já diga direto qual arquivo/funcionalidade, citando o nome do arquivo acima — evita ter
que re-explicar toda a arquitetura de novo.