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
  ia_engine.py            <- Toda a lógica de IA: classificação final + chat de coleta
  rag.py                  <- Busca semântica nos .md (usado tanto na classificação quanto no chat)
  database.py              <- Todas as funções de banco (chamados, usuarios, códigos)
  auth.py                   <- Hash de senha, TOTP (autenticador), geração de código
  email_utils.py             <- Envio de e-mail real via SMTP
  seed_usuarios.py            <- Cria os 3 usuários de teste (rodar 1x)
  main.py                      <- Script de teste antigo (fluxo sem chat, sem login) — só para debug isolado
  base_conhecimento/
    hardware.md, rede.md, software.md
  .env                          <- Credenciais (não versionar/compartilhar)
  requirements.txt
```

## Como rodar (rotina padrão)

```powershell
cd Desktop\projeto_tcc
py -3.11 -m streamlit run app.py
```

Se mudou `database.py`, `auth.py` ou qualquer módulo importado (não só `app.py`), **precisa
reiniciar o Streamlit** (Ctrl+C e rodar de novo) — ele só recarrega sozinho o `app.py`.

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

## Cronograma original (13 semanas / 7 sprints) — status

1. **Sprint 1-2 (setup + classificação básica)** ✅ concluído
2. **Sprint 2-3 (base de conhecimento + RAG)** ✅ concluído
3. **Sprint 3 (integração + prompt)** ✅ concluído, prompt evoluiu bastante (SLA, mapeamento
   categoria/equipe, few-shot, depois virou chat adaptativo)
4. **Sprint 4 (interface)** ✅ concluído e **ampliado além do planejado originalmente**
   (que previa só formulário simples): login, 3 telas por perfil, chat de coleta com IA,
   e agora também UI redesenhada (abas, cards, badges), fluxo de atendimento estilo ITIL 4
   no analista (assignment + ciclo de vida do incidente) e conversa persistida por chamado
5. **Sprint 5 (testes e métricas de acurácia)** ⬜ ainda não iniciado — próximo passo real
6. **Sprint 6 (documentação do TCC)** ⬜ pendente — o texto do TCC ainda reflete a
   arquitetura ANTIGA (React/Node/microsserviços/TF-IDF), precisa reescrever Metodologia,
   Arquitetura e Resultados para refletir o que foi construído de fato
7. **Buffer** ⬜

## Histórico de mudanças recentes

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

## Próximos passos sugeridos (em ordem)

1. Rodar o app após o redesign (`py -3.11 -m streamlit run app.py`) e conferir na prática:
   migração automática das tabelas (`analista_id`, `mensagens_chamado`), o novo fluxo de
   "Atender chamado" no analista e a conversa por chamado nas duas pontas
2. Testar bastante o chat de coleta com casos variados e ambíguos, ajustar prompt conforme
   os erros aparecerem
3. Montar um conjunto de ~30-50 casos de teste com classificação esperada conhecida, para
   medir % de acerto (isso é o que falta para o capítulo de Resultados ter números reais)
4. Reescrever as seções do TCC (Arquitetura, Metodologia, Resultados) refletindo a stack
   real usada, não a original — **agora incluindo o alinhamento a ITIL 4** na gestão de
   incidentes (assignment do analista, ciclo de vida de status) como diferencial do projeto
5. Polimento final (tratar avisos do Streamlit tipo `use_container_width`, revisar UX)

## Como retomar em um novo chat

Cole este arquivo inteiro como contexto inicial. Se for pedir ajuda em algo específico,
já diga direto qual arquivo/funcionalidade, citando o nome do arquivo acima — evita ter
que re-explicar toda a arquitetura de novo.