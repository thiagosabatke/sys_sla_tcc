# Análise e refatoração de UI/UX

## Escopo

Trabalho realizado conforme o `C:/Users/tsaba/Desktop/AGENTS.md`, preservando as
entradas Streamlit e as operações existentes de autenticação, autorização, IA,
persistência e SLA. As alterações locais que já existiam em `database.py`,
`sla.py` e `pages/_telas.py` foram consideradas como ponto de partida.
Na refatoração inicial, nenhuma migração, criação de chamados ou inserção de demonstrações foi executada.
Na ampliação solicitada pelo usuário, foi excluído somente o departamento incorreto
`Recursos Humanos (RH)` (ID 1), após confirmar a ausência de vínculos por ID ou nome e
de referências adicionais no banco. A operação foi auditada e a consulta posterior
confirmou zero registros com esse nome.

## Diagnóstico da estrutura

- `pages/_telas.py` concentrava apresentação, sessão, navegação, filtros e relatórios.
  Também mantinha aproximadamente 600 linhas de CSS após um retorno antecipado.
- Componentes ativos dependiam de classes desse CSS inativo. Etiquetas aplicavam
  fundos fixos, e gráficos Matplotlib mantinham fundos e textos sem adaptação ao tema.
- O destino inicial priorizava administração mesmo sem permissão de relatórios;
  a seção administrativa padrão era Usuários.
- A fila mostrava muitos filtros simultaneamente e etiquetas sem os prazos vigentes.
- O portal destacava o catálogo de artigos, com menos orientação para iniciar uma conversa.
- O dashboard não colocava os quatro indicadores operacionais pedidos no primeiro plano.
  Uma seleção incompleta de datas podia deixar a consulta sem filtro de período.
- O relatório operacional consultava históricos por chamado, exigindo acesso à fila
  mesmo para quem só tinha acesso aos relatórios.
- A saída removia algumas chaves, mas conservava anexos preparados, exportações e
  outros estados temporários que poderiam permanecer na sessão da próxima conta.

## Organização resultante

| Módulo | Responsabilidade |
| --- | --- |
| `core/navigation.py` | Rotas existentes, permissões efetivas e prioridade do destino inicial. |
| `core/session.py` | Valores iniciais e descarte do estado ao encerrar a sessão. |
| `ui/components.py` | Cabeçalhos, indicadores, cartões, prazos e gráficos nativos. |
| `ui/requester_view.py` | Introdução do portal, contexto real da conversa e atalho para acompanhamento. |
| `ui/analyst_view.py` | Filtros da fila e aplicação de filtros sem mudar sua ordenação. |
| `ui/admin_dashboard.py` | Agregação por `sla.py`, departamento e visão executiva. |
| `pages/_telas.py` | Composição das telas e chamadas às operações existentes. |

O arquivo de telas permanece como coordenador: não houve uma reescrita integral.
`executar_aplicacao()` continua disponível para `app.py` e as três páginas.
O inventário anterior de acessos e chaves de sessão está em [SESSAO_UI.md](SESSAO_UI.md).
As chaves de autenticação, navegação e conversa foram preservadas. Os filtros
atuais do dashboard usam `dashboard_periodo_abertura`, `dashboard_intervalo_datas`,
`dashboard_categoria`, `dashboard_urgencia` e `dashboard_situacao`, conforme o
inventário de sessão. São descartados, junto com todo o estado, ao sair.

Foi avaliada a navegação com `st.Page`/`st.navigation`. Nesta alteração foram mantidos
`st.page_link`/`st.switch_page` para preservar rotas e não misturar os dois modelos.
A seleção inicial foi extraída e testada independentemente dessa decisão.

## Melhorias de experiência

- Destino inicial: administração com relatórios → Dashboards; caso contrário,
  fila autorizada → Fila ativa; portal autorizado → Central de ajuda; por fim,
  primeira área permitida. A própria tela verifica novamente seu acesso.
- Portal: convite para descrever o problema, explicação sobre a confirmação,
  filtros de artigos recolhidos e atalho para acompanhar o chamado registrado.
  Perfis sem IA ou abertura não recebem os respectivos controles.
- Fila: quatro indicadores explicados, busca inclusive por número, seleção múltipla
  de estados e filtros secundários recolhidos. A busca e a seleção permanecem ao
  abrir detalhes; a ordenação existente por SLA, urgência e abertura foi mantida.
- Histórico de fechados: cards compactos com número, título, solicitante, responsável,
  categoria, urgência e datas. Descrição, conversa e SLA permanecem no detalhe.
  O rodapé navega de cinco em cinco registros, com Anterior, Próxima e número da página.
  A consulta percorre todas as páginas de fechados no banco, ordenadas por abertura
  e número, e a busca alcança os chamados antigos. Indicadores ficam em um expansor.
- Chamados: estado e urgência com texto e ícone; resposta e resolução com prazos
  efetivos fornecidos por `sla.py`, incluindo seus ajustes de pausa.
- Ações: assumir, cancelar, responder, anexar, confirmar, resolver e transferir
  respeitam as permissões consultadas. O backend continua validando cada operação.
- Dashboard: ativos, violações, risco e cumprimento do SLA; tendência diária,
  carga por departamento, urgências, situação por etapa e tabela de exceções.
  Chamados cancelados não entram nos alertas nem no cumprimento.
- Carga por departamento considera todo o recorte em barras empilhadas de ativos,
  fechados e cancelados. O histórico participa do volume total de cada setor;
  os KPIs e as exceções continuam usando os ativos conforme as regras existentes.
- Os gráficos de volume de chamados compartilham `ui/charts.py`: três séries fixas,
  na ordem Ativos, Cancelados e Fechados, em barras empilhadas. A mesma classificação
  vale para datas de abertura, urgências, equipes, departamentos, categorias,
  analistas, confiança da IA e análises de priorização. Recortes específicos mantêm
  sua seleção de registros. A evolução mostra a situação atual dos chamados de
  cada dia de abertura, preenchendo com zero os dias intermediários sem chamados.
- Cumprimento exige ambos os marcos e prazos: resposta e resolução cumpridas
  divididas pela amostra com essas informações. Sem amostra, o indicador informa
  isso em vez de apresentar uma porcentagem artificial.
- O período de abertura oferece janelas móveis de 30 dias, 7 dias e 24 horas,
  além de um intervalo de dias completos e todo o histórico até agora, no horário de São Paulo.
  As páginas de chamados são carregadas até o fim, sem truncar em 5.000 registros. Categoria,
  urgência e situação ficam visíveis, com resumo da seleção e botão para limpar.
  O antigo expansor de departamento e equipe foi removido. Cadastros e métricas globais de IA são identificados
  como escopos distintos do recorte de chamados.
- As análises complementares existentes e os controles de demonstração foram mantidos
  fora da leitura principal. Os controles de demonstração só aparecem a administradores.
- A demonstração agora usa os solicitantes e analistas com permissões efetivas e os
  departamentos atuais. O painel permite adicionar lotes de 12 a 500 chamados e remover
  somente os marcados como sintéticos. Os cadastros não são alterados. Os dados incluem
  conversas, histórico, avaliações e prazos calculados por `sla.py`; o volume de ativos
  deixa uma vaga por solicitante para um chamado real. A geração está em `demo_data.py`.
- CSS inativo e HTML dependente dele foram removidos. Gráficos simples usam os
  componentes nativos; as hipóteses de causa são apresentadas em blocos legíveis.
  A configuração continua permitindo os temas nativos Light e Dark.

## Validação

Na padronização dos gráficos, os 106 testes passaram, incluindo a renderização
dos relatórios com as três séries, os totais sem duplicação e a evolução com dias
sem abertura. A validação desta revisão usou o AppTest do Streamlit; não houve
nova conferência visual no navegador.

Na revisão das demonstrações, os 99 testes passaram. Foram adicionados 120 chamados
no MySQL local, totalizando 132 demonstrações. Impressões SHA-256 confirmaram que os
27 registros anteriores, cinco usuários e três departamentos foram preservados. A
remoção dos 132 exemplos foi executada em uma transação revertida ao final: os 15
chamados reais permaneceram e as demonstrações continuaram disponíveis após o teste.

Na revisão do histórico de fechados, os 85 testes da suíte passaram. A prévia
local com dados fictícios foi conferida no navegador em 1280 × 720 e 390 × 844,
incluindo os cards, a segunda página e o rodapé. O tema escuro e os dados reais
não foram verificados visualmente nesta revisão.

Ambiente encontrado: Python 3.11 e Streamlit 1.61.1. `requirements.txt` declara a
versão mínima de Streamlit utilizada na validação; não foram adicionadas bibliotecas.
Os parâmetros obsoletos `use_container_width=True` da interface foram atualizados
para `width="stretch"`.

Executado: `python -m unittest discover -s tests -v`: **68 testes aprovados**. A suíte inclui os testes
anteriores de RBAC, SLA comercial, primeira resposta, fuso, classificação e validações,
além das regressões em `tests/test_ui_refatoracao.py`.

Os testes AppTest usam dados e dependências simuladas somente no processo de teste,
sem conexão com o banco. Cobrem estados vazios, apenas cancelados, acesso restrito
a relatórios, confirmação explícita antes de persistir, permissões de interface,
seleção e busca da fila, segundo fator e privacidade antes do redirecionamento.

O modelo de embeddings já estava no cache. Para evitar consultas à rede durante a
importação da suíte, foram usados `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`.
Essas opções não foram gravadas na configuração da aplicação.

Também foram executados compilação dos módulos e `git diff --check`.

## Ampliação para todas as áreas da interface

Nesta etapa não foram criadas novas pastas. `core`, `ui` e `docs` foram criadas na
primeira etapa; `pages` e `tmp_modelo_render` já existiam no primeiro inventário.
`core`/`ui` seguem a organização sugerida na seção 6 do AGENTS; `docs` reúne o
inventário de sessão exigido e estas decisões. As pastas preexistentes não foram removidas.

- Acesso, segundo fator, recuperação e privacidade usam um formulário central com
  largura confortável, sem colunas vazias comprimindo a interface em telas pequenas.
- Chamados ativos, próprios, fechados e cancelados têm listas recolhíveis e paginação
  visual de cinco cartões. Busca, filtros e seleção continuam disponíveis nos detalhes.
- Estado e urgência usam etiquetas nativas acessíveis. Resposta e resolução têm blocos
  próprios, com prazos calculados pelo módulo de SLA.
- Conversa, anexos e histórico são agrupados; confirmação de solução e cancelamento
  aparecem antes desses conteúdos secundários no portal.
- Usuários usam tabela selecionável, sem a grade manual de cinco colunas por pessoa.
  Consulta e cadastro são separados; consulta sem gerenciamento não oferece edição.
- Perfis separam consulta, criação e edição. Os grupos de permissões são recolhíveis,
  mantendo suas dependências e a proteção do Administrador. O cadastro limpa campos
  somente na próxima execução, antes da recriação dos widgets.
- Departamentos separam consulta, cadastro e edição. SLA agrupa agenda, metas e
  regras operacionais, preservando configurações que não forem editadas.
- Auditoria reúne filtros em formulário, com combinações avançadas recolhidas e
  tratamento explícito de intervalo de datas incompleto.
- Privacidade descarta a seleção anterior quando a nova busca falha; ações permanentes
  ficam em área separada. O titular é revalidado pela consulta autorizada de privacidade,
  sem exigir acesso genérico à lista de usuários.
- O dashboard e o cadastro de pessoas consultam somente os dados do painel escolhido.
- Feedback de operações confirmadas persiste por notificações após a recarga. Erros
  de atendimento permanecem visíveis; falhas de conexão exibem uma ação de recuperação.
- O tempo médio de resolução dos relatórios usa `sla.minutos_uteis_entre`, respeita
  o calendário do chamado e desconta pausas, incluindo campos Decimal e datas ausentes.
- Na validação real, o observador de módulos do Streamlit tentou inspecionar imports
  multimodais opcionais de `transformers`, produzindo tracebacks por falta de `torchvision`.
  A configuração `server.fileWatcherType = "none"` evita essa inspeção sem instalar
  bibliotecas não utilizadas. Mudanças no código exigem reiniciar o app pelo BAT;
  a execução normal, os widgets, a navegação e os temas continuam disponíveis.

## Ajuste da fila após o retorno do usuário

- A fila ativa tem cartões compactos à esquerda e detalhes à direita, com empilhamento
  nativo em telas estreitas. A apresentação resumida é específica da fila, sem reduzir
  as informações disponíveis no detalhe ou mudar a ordenação operacional.
- `Atribuídos a mim` passou dos filtros avançados para um controle ao lado da busca,
  preservando a chave `somente_meus_ativa`. O filtro usa o ID do responsável, desfaz
  conflitos com outro analista selecionado e desabilita essa seleção enquanto ativo.
- Detalhes de uma seleção fora do resultado filtrado ficam ocultos até selecionar
  outro chamado ou restaurar o escopo anterior; o ID anterior permanece preservado.
- Criticidade, SLA, categoria e equipe têm valores maiores e etiquetas semânticas.
  Resposta e resolução exibem prazos em destaque e tempo restante em negrito, usando
  os resultados de `sla.py`. As cores são nativas, sem CSS ou hexadecimais fixos.
- Três testes adicionais verificam atribuição pelo ID, conflito entre filtros e
  detalhes de outro analista após ativar a própria fila.
- A prévia isolada da fila foi inspecionada em Light e Dark, em 1440 × 1000 e 390 × 844,
  com dados fictícios e conexão ao banco bloqueada. O filtro foi operado no navegador;
  a tela de 390 px não apresentou transbordamento horizontal. Nenhum chamado real foi alterado.

## Validação visual e limitações

### Cores por estado e textos sem quebra nos indicadores

Os estados usam uma identificação compartilhada na fila, nos detalhes, no portal e
no histórico: Novo azul, Em Andamento laranja, Em Espera roxo, Resolvido verde,
Fechado cinza e Cancelado vermelho. As etiquetas mantêm texto e ícone além da cor.

Os indicadores e os prazos passam a empilhar conforme a largura real disponível no
painel, inclusive quando a barra lateral está aberta. Os valores têm tipografia
fluida em uma linha; somente nomes extensos usam reticências, com texto completo no
tooltip. O pequeno estilo inline atua apenas no elemento do valor, herda as cores do
tema e escapa o conteúdo HTML; não utiliza seletores internos ou CSS global.

Na prévia isolada, `Dentro do prazo` foi conferido inteiro em uma linha em 975 px com
barra lateral aberta e em 390 px, sem transbordamento horizontal. As cores também
foram conferidas nos temas Light e Dark. Nenhum dado real foi utilizado nessa prévia.

- O bloqueio da primeira etapa foi resolvido iniciando o servidor local com a autorização
  exigida pelo ambiente. A aplicação real abriu em `127.0.0.1:8517`, com MySQL disponível.
- Acesso e recuperação foram inspecionados no navegador em tela estreita e em 1440 × 900.
  O acesso foi conferido nos temas Light e Dark; a preferência de tema foi restaurada.
- As áreas autenticadas e seus formulários foram verificados por AppTest, com dependências
  simuladas. Não houve inspeção com uma sessão real autenticada no navegador. A fila
  também teve a inspeção visual isolada descrita acima, sem acesso ao banco.
- Login real, envio de e-mail, validação real de 2FA, MySQL e geração de respostas
  do Ollama não foram exercitados de ponta a ponta. Os testes dessas barreiras usam mocks.
- A fila continua limitada aos 200 registros mais recentes e o dashboard aos 5.000,
  conforme as consultas existentes. A paginação visual ocorre dentro desses recortes;
  ela não amplia a consulta ao banco.
- Pesquisas de satisfação, casos de IA e qualidade mantêm os limites das consultas
  existentes. Esta alteração não implementa paginação ou um serviço analítico no banco.

Referências de API: [gráficos nativos](https://docs.streamlit.io/develop/api-reference/charts/st.bar_chart)
e [temas do Streamlit](https://docs.streamlit.io/develop/concepts/configuration/theming).
