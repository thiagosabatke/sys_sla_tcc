# Operação do banco de dados

O Streamlit **não executa DDL nem migrações**. Antes de publicar uma versão, em uma
janela de manutenção, execute `python migrations.py status` e depois
`python migrations.py upgrade` com um usuário de banco que tenha apenas as permissões
necessárias para schema. Registre a versão, responsável, horário UTC e resultado.

## Backup e rollback

No estado atual do projeto, as migrações não criam cópias `schema_bkp_*` dentro do banco.
Antes de executar uma migração, faça e valide um backup lógico ou gerenciado externo.

Se uma migração falhar, interrompa a publicação, preserve os logs e restaure o backup
externo em ambiente isolado antes de aplicar qualquer correção. Não execute `DROP TABLE`
ou renomeie tabelas de produção sem aprovação do responsável pelo banco.

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
