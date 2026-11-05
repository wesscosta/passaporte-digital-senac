---
name: release-validacao
description: "Validar conclusão de incremento, PR, merge, tag e release por gates técnicos verificáveis"
---

# release validacao

> **Estado: em validação.** Instruções operacionais adaptadas; preservar a documentação original e confirmar fidelidade antes de classificá-las como versão definitiva.

## Quando usar
Validar conclusão de incremento, PR, merge, tag e release por gates técnicos verificáveis. Use em tarefas recorrentes desse domínio e não para assuntos alheios ao escopo.

## Procedimento obrigatório
1. Confirme escopo, critérios de aceite e integridade do workspace.
2. Revise diff e dependências; execute lint, tipagem, testes, build e migrações aplicáveis.
3. Teste UI/E2E, acessibilidade, runtime, smoke e segurança conforme as alterações.
4. Confirme documentação, changelog, ADR, README e pendências técnicas.
5. Verifique pipeline remoto e status dos checks no commit exato; resultados locais não bastam para alegar CI aprovado.
6. Declare READY, READY WITH NON-BLOCKING RISKS ou NOT READY com justificativa.
7. Commit, push, merge, tag e release somente com autorização e evidência. Nunca reescreva histórico silenciosamente.

## Entregável
Tabela de gates com comando, evidência, estado, bloqueadores e decisão de prontidão.

## Regras invariantes
- Não inventar evidências, registros, disponibilidade, testes ou estados de implementação.
- Antes de ação irreversível (destruição, compra, protocolo, publicação), exigir autorização pertinente.
- Citar fontes atuais quando depender de informações externas.
- Proteger dados pessoais, segredos e conteúdo interno.
- Se faltar acesso à ferramenta, marcar como não verificado e descrever o bloqueio.

## Fonte histórica
Consulte SOURCE.md para a página canônica no Notion.
