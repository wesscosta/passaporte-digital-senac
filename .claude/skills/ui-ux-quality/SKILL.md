---
name: ui-ux-quality
description: Planeja, implementa e revisa interfaces web com foco na tarefa do usuário, consistência visual e acessibilidade. Use para criar, redesenhar ou auditar telas, componentes, formulários, landing pages e dashboards.
metadata:
  version: "0.2.0"
---

# Qualidade de UI/UX

## Escopo e entradas

Identifique o modo solicitado (planejar, implementar ou revisar), o público, a tarefa principal, o critério de sucesso e o material disponível. Use o contexto fornecido. Pergunte apenas quando a resposta mudar materialmente a entrega. Declare suposições reversíveis.

Em projetos existentes, use o Figma aprovado como referência visual quando fornecido e reaproveite componentes e tokens do código. Registre divergências que afetem o resultado. Limite alterações ao escopo autorizado.

## Procedimento

1. Percorra a tarefa principal do início ao fim. Priorize a ação que permite avançar e mantenha ações secundárias visíveis quando necessárias.
2. Defina hierarquia, densidade e adaptação do layout ao conteúdo. Reutilize o sistema de design. Em projetos novos, defina apenas os tokens semânticos usados. Trate fontes, espaçamentos e animações como decisões de projeto.
3. Cubra os estados pertinentes, como carregamento, vazio, erro, sucesso e indisponibilidade. Explique como recuperar de falhas e preserve dados já preenchidos quando possível.
4. Use WCAG 2.2 AA como alvo para web. Verifique semântica, nomes acessíveis, rótulos, mensagens de erro, teclado, foco visível e não totalmente encoberto, contraste e redimensionamento. Para texto, verifique 4,5:1 em tamanho normal e 3:1 em texto grande, conforme o critério 1.4.3. Para informação visual necessária em componentes e estados, aplique 3:1 conforme 1.4.11. Avalie alvos de 24 × 24 px CSS conforme 2.5.8, incluindo as exceções de espaçamento. Teste reflow a 320 px CSS conforme 1.4.10, considerando conteúdo que exige duas dimensões.
5. Use animação para feedback, orientação ou continuidade. Respeite a preferência por movimento reduzido e garanta que a informação essencial permaneça disponível.
6. Verifique o fluxo com o material e as ferramentas disponíveis. Em execução, teste teclado, larguras relevantes e estados críticos. Em captura estática, cite regiões visíveis e deixe interação, semântica e comportamento responsivo como não verificados. Trate automação como evidência parcial.

## Entrega

- Planejamento: fluxo, hierarquia, estados e critérios de aceite.
- Implementação: alterações, decisões relevantes, testes executados e pendências.
- Revisão: achado, evidência, impacto, severidade e correção. Ordene pelo impacto na tarefa. Use bloqueante para tarefa impedida, alta para barreira grave ou risco de perda de dados, média para atrito relevante e baixa para melhoria localizada.

Use os estados Verificado, Falhou, Não verificado e Não se aplica, com evidência para cada resultado reportado. Declare o alcance da revisão. Uma checagem parcial não estabelece conformidade WCAG. Não invente testes, métricas ou pesquisa com usuários.
