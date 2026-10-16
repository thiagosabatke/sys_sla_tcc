# Aviso de Privacidade — Sistema Inteligente de Chamados

**Versão 1.3.0 — publicada em 13/10/2026**

Este aviso explica como os dados pessoais são tratados no Sistema Inteligente de
Chamados, em conformidade com a Lei nº 13.709, de 14 de agosto de 2018 — Lei Geral
de Proteção de Dados Pessoais (LGPD).

> Antes da produção, configure os dados reais de controlador e DPO no ambiente e
> valide este aviso com o encarregado/DPO ou assessoria jurídica. Não é seguro inventar
> esses dados em um projeto acadêmico.

## Controlador e canal de contato

**Controlador:** a organização operadora configurada como `ORGANIZACAO_CONTROLADORA`
(CNPJ `CNPJ_CONTROLADOR`), responsável pelas decisões sobre o tratamento dos dados.

**Encarregado/DPO ou canal de privacidade:** `DPO_NOME`, pelo canal
`CANAL_PRIVACIDADE` divulgado ao titular.

## Dados pessoais tratados

Podem ser tratados os seguintes dados, conforme informados ou gerados durante o uso:

- identificação e contato: nome, sobrenome, e-mail, telefone e CPF quando informado;
- vínculo organizacional: departamento, cargo e perfil de acesso;
- autenticação e segurança: senha armazenada em formato protegido, configuração de
  segundo fator, registros de acesso e eventos de segurança;
- atendimento: títulos, descrições, mensagens, anexos, avaliações e histórico dos
  chamados; e
- dados técnicos mínimos de auditoria, como data/hora, ação executada, entidade afetada
  e resultado.

Senhas, códigos de verificação e segredos de autenticação não são exibidos nas
exportações de dados. O CPF é validado e armazenado apenas como identificador protegido
para busca exata, não sendo exibido nas telas ou exportações. Evite inserir nos chamados
dados pessoais que não sejam necessários para o atendimento.

## Finalidades e bases legais

Os dados são utilizados para autenticar e administrar contas, receber e atender
solicitações de suporte, comunicar-se sobre os chamados, proteger o sistema, prevenir
fraudes e incidentes, manter auditoria técnica e cumprir obrigações legais ou
regulatórias aplicáveis.

O controlador deve registrar e validar com o DPO a base legal de cada operação:

| Operação | Base legal a validar | Responsável |
| --- | --- | --- |
| Conta, autenticação e atendimento | execução de contrato/procedimentos preliminares (art. 7º, V) | Operações de suporte |
| Segurança, prevenção a fraude e logs | legítimo interesse com LIA documentado (art. 7º, IX) | Segurança da informação |
| Obrigações regulatórias | obrigação legal/regulatória (art. 7º, II) | Jurídico/Compliance |
| IA e conhecimento interno | finalidade compatível e avaliação de impacto | DPO e responsável de IA |

O aceite exibido no sistema registra ciência do aviso; ele não é uma base genérica para
tratamentos que se sustentam em contrato, obrigação legal ou legítimo interesse.

## Compartilhamento e uso de tecnologia

Os dados são acessados somente por pessoas autorizadas, conforme suas permissões e a
necessidade de atendimento. O compartilhamento com operadores ou fornecedores deverá
ocorrer somente quando necessário para as finalidades informadas, sob instruções do
controlador e com medidas de segurança apropriadas.

O sistema pode utilizar recursos de inteligência artificial para apoiar a orientação,
classificação e o atendimento de chamados. A inclusão de um caso na base interna de
conhecimento exige revisão humana e aprovação explícita. A anonimização por regex é
apenas uma barreira inicial e não garante a remoção de dado pessoal em texto livre; o
revisor deve remover identificadores diretos, indiretos, segredos e contexto sensível.

## Retenção e segurança

Os dados são mantidos apenas pelo período necessário às finalidades descritas, à
segurança, à auditoria e às obrigações legais aplicáveis. A tabela de retenção formal é:

| Categoria | Prazo padrão | Ação ao término |
| --- | --- | --- |
| Códigos temporários | 30 dias após expiração/uso | expurgo agendado e auditável |
| Chamados, mensagens e anexos | 5 anos após fechamento | anonimização ou eliminação autorizada |
| Casos e atendimentos de IA | 2 anos | eliminação ou nova revisão humana |
| Logs e auditoria | 5 anos | arquivamento protegido ou eliminação autorizada |
| Arquivo de exportação LGPD | 7 dias | remoção do local temporário |

São adotados controles de acesso por perfil, proteção de credenciais, registros de
auditoria e recursos de anonimização. A organização também deve proteger o banco de
dados, utilizar conexões seguras, manter cópias de segurança e revisar periodicamente
as permissões concedidas.

## Direitos do titular

Nos limites e condições da LGPD, o titular pode solicitar confirmação de tratamento,
acesso, correção, anonimização, bloqueio, eliminação, portabilidade, informação sobre
compartilhamento e revogação de consentimento. As solicitações devem ser enviadas ao
canal de privacidade indicado neste aviso.

## Atualizações deste aviso

Este aviso pode ser atualizado para refletir mudanças no tratamento de dados ou na
legislação. Alterações relevantes serão publicadas com uma nova versão e poderão exigir
novo aceite no sistema.
