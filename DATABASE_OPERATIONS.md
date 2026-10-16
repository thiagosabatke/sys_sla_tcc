# Operação do banco de dados

O Streamlit **não executa DDL nem migrações**. Antes de publicar uma versão, em uma
janela de manutenção, execute `python migrations.py status` e depois
`python migrations.py upgrade` com um usuário de banco que tenha apenas as permissões
necessárias para schema. Registre a versão, responsável, horário UTC e resultado.

## Backup e rollback

Antes de uma migração que altera schema, o gerenciador cria cópias das tabelas
operacionais com o prefixo registrado em `schema_migrations.backup_prefixo`. Esse é um
backup de contingência no mesmo servidor, não substitui um dump criptografado e testado
fora do servidor. Faça e valide também um backup lógico/gerenciado antes da janela.

Se uma migração falhar, interrompa a publicação, preserve logs e restaure o dump externo.
Para rollback pontual, compare a cópia `schema_bkp_v<versão>_<UTC>_<tabela>` com a tabela
atual em ambiente isolado; depois restaure dados e schema por script revisado. Não execute
`DROP TABLE` ou renomeie tabelas de produção sem aprovação do responsável pelo banco.

## Retenção

| Dado | Retenção padrão | Destino ao fim do prazo |
| --- | --- | --- |
| Códigos de verificação | 30 dias após expiração/uso | Expurgo automático agendado |
| Anexos, mensagens e chamados | 5 anos após fechamento | Anonimização ou eliminação aprovada pelo controlador |
| Atendimentos/casos de IA | 2 anos | Eliminação ou revisão humana para nova finalidade |
| Auditoria e logs de segurança | 5 anos | Arquivamento protegido; eliminação conforme obrigação aplicável |
| Exportações LGPD | 7 dias | Arquivo temporário expira e é removido |

Os prazos são parâmetros organizacionais e devem ser validados pelo controlador/DPO antes
da produção. Expurgos de conteúdo e auditoria exigem procedimento aprovado, pois podem
conflitar com obrigações legais ou investigação de incidentes.
