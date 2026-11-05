# Validação e status

**Status: NÃO PRONTO para produção ou dados reais.**

## Verificado localmente

Revisão de 05/11/2026, em cópia isolada com dados fictícios:

- 21 testes automatizados passaram no PostgreSQL, inclusive concorrência entre dois carimbos, cadastro apenas com celular, recuperação de contatos legados e consentimento opcional versionado.
- Brave/Chromium headless: tela de 320 pixels sem rolagem horizontal no início, cadastro e passaporte; consentimento inicialmente desmarcado e alinhado; painel da equipe com seis áreas.
- Leitura de QR com câmera simulada e decodificador local: QR abriu a tela de confirmação sem criar carimbo; o envio confirmou o registro. Permissão negada apresentou orientação e manteve a digitação manual.
- O teste de URLs do leitor rejeitou origens e caminhos externos à aplicação. A câmera real e navegadores móveis ainda não foram testados.

Resultados da versão inicial, preservados para histórico:

- Django check sem erros.
- 17 testes automatizados com PostgreSQL passaram, incluindo criação e recuperação, consentimento, duplicidade, intervalo, expiração, permissões e entrega idempotente.
- Teste de dois carimbos concorrentes em estandes distintos: um aceito e o outro aguardando, com bloqueio transacional no PostgreSQL.
- Navegador Brave/Chromium headless, em 320 e 1280 pixels: início, cadastro, recuperação, passaporte e digitação de código sem rolagem horizontal. Cadastro e recuperação sintéticos testados no navegador. Não equivale a teste em Android ou iOS reais.
- Na versão inicial, sem cache e sem compressão, a página inicial mediu 8.182 bytes de HTML e CSS. Esta medida não se aplica automaticamente à interface revisada e deve ser refeita.
- Durante o teste real, uma política de referrer provocou falha CSRF em POST e foi alterada para same-origin. A navegação por tela pequena também foi ajustada.

## Bloqueadores antes de qualquer evento

1. Definir e testar carga esperada, picos e limites; executar testes de carga e estresse em ambiente semelhante ao real. Medir tempos, falhas, CPU, conexões e locks de banco. Um teste de duas requisições concorrentes não é teste de capacidade. O servidor runserver é apenas para desenvolvimento.
2. Definir hospedagem, TLS, servidor de aplicação, backups e teste de restauração, monitoramento, disponibilidade e rede do local; configurar estáticos com cache e compressão sem cachear respostas pessoais.
3. Fazer revisão de segurança: login de equipe e admin ainda não têm limitação de tentativas; endurecer acesso e sessões, política de senhas, logs e proxy confiável, uso seguro de segredos e recuperação. A chave atual também participa da derivação dos identificadores de contato: rotação sem estratégia poderá impedir recuperação.
4. Endurecer e testar limites de tentativas sob carga e atrás do proxy; evitar bloqueio indevido de toda uma rede compartilhada; simular abuso, concorrência, mudança de sessão, fraude e indisponibilidade. Revisar possibilidade de vazamento de códigos temporários em URLs e logs.
5. Validar aviso e tratamento de dados com responsáveis institucionais: finalidades, contato, consentimento, retenção, menores, direitos e operação de suporte. O consentimento mostrado é provisório.
6. Testar jornada completa e QR em aparelhos Android/iOS reais, redes móveis lentas e redes do local; testar navegabilidade por teclado, leitor de tela, contraste e zoom com evidências. Não há alegação de conformidade WCAG.
7. Aprovar identidade visual, conteúdo, quantidade de estandes, regras da premiação, supervisão humana e plano operacional.

## Limitações funcionais conhecidas

Telefone e e-mail não são verificados por SMS, WhatsApp ou e-mail. Conhecer o contato e o PIN é uma credencial de recuperação, não prova da identidade ou posse do telefone. Pessoas podem compartilhar contatos ou códigos; uma entrega por passaporte não garante uma entrega por pessoa. A perda do PIN exige um procedimento assistido que ainda não está implementado. Não existe uso offline. Nenhuma exportação de leads ou procedimento de exclusão/retenção foi implementado.
