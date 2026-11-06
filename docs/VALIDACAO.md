# Validação e status

**Status: NÃO PRONTO para produção ou dados reais.**

## Verificado localmente

Revisão de 05/11/2026, em cópia isolada com dados fictícios:

- 21 testes automatizados passaram no PostgreSQL, inclusive concorrência entre dois carimbos, cadastro apenas com celular, recuperação de contatos legados e consentimento opcional versionado.
- Brave/Chromium headless: tela de 320 pixels sem rolagem horizontal no início, cadastro e passaporte; consentimento inicialmente desmarcado e alinhado; painel da equipe com seis áreas.
- Leitura de QR com câmera simulada e decodificador local: QR abriu a tela de confirmação sem criar carimbo; o envio confirmou o registro. Permissão negada apresentou orientação e manteve a digitação manual.
- O teste de URLs do leitor rejeitou origens e caminhos externos à aplicação. A câmera real e navegadores móveis ainda não foram testados.

Revisão de 05/11/2026 (entrada pelo QR e horário do próximo carimbo), com dados fictícios em banco PostgreSQL temporário, já removido:

- 25 testes automatizados passaram no PostgreSQL, inclusive a concorrência entre dois carimbos. Novos testes: QR lido sem sessão oferece cadastro e retoma a visita; estande inexistente responde 404 sem guardar visita pendente; código de QR expirado pede nova leitura sem criar carimbo; o horário exibido nunca antecede o fim do intervalo.
- O intervalo continua decidido em record_stamp, sob bloqueio no PostgreSQL. A tela apenas exibe o horário a partir do último carimbo, arredondado para o minuto seguinte.
- Os textos de intervalo do início e do passaporte passaram a usar o gap_seconds do evento (testados com 300, 90 e 0 segundos); o contador do passaporte voltou a exibir "carimbos registrados" com espaço em 360 pixels. Suíte com 27 testes aprovada no PostgreSQL.
- Brave headless com viewport emulado de 320 pixels: entrada pelo QR, cadastro com visita pendente, passaporte, confirmação com espera e código expirado sem rolagem horizontal. Não testado em Android ou iOS reais nem com leitor de tela.

Revisão de 05/11/2026 (premiação no topo, retorno do carimbo, ícones e nome único para entrar), com dados fictícios em banco PostgreSQL temporário, já removido:

- 30 testes automatizados passaram no PostgreSQL, inclusive a concorrência entre dois carimbos. Novos testes: a premiação sobe para o topo só enquanto pode ser retirada; o carimbo informa estande e horário e destaca o cartão uma única vez; as telas de entrada usam apenas "Entrar no passaporte" e não exibem o ícone de link externo.
- Brave headless com viewport emulado de 320 pixels: passaporte após carimbo, passaporte elegível com código de retirada e início sem rolagem horizontal. A animação do carimbo é desativada pela preferência de movimento reduzido já existente; o estado novo também é indicado por texto ("Novo"). Não testado em aparelhos reais nem com leitor de tela.

Revisão de 06/11/2026 (limite de tentativas no acesso da equipe e no /admin/), com dados fictícios em banco PostgreSQL temporário, já removido:

- O login da equipe e o do /admin/ usam o mesmo formulário com limite: 5 tentativas por conta (nome normalizado em minúsculas, exista ou não) e 50 por endereço, em janela fixa de 15 minutos. A tentativa é consumida antes da verificação da senha; quando bloqueada, a senha nem é verificada e a mensagem é a mesma para contas existentes ou não. O acerto zera o contador da conta, mas não o do endereço.
- 37 testes automatizados passaram no PostgreSQL. Novos testes: bloqueio da conta após 5 erros sem chamar a autenticação; conta inexistente bloqueada da mesma forma; acerto zera as falhas; bloqueio expira após a janela; limite por endereço abrange várias contas sem afetar outro endereço; /admin/ e acesso da equipe compartilham o contador; 10 tentativas simultâneas erradas na mesma conta resultam em exatamente 5 verificações de senha.
- Limitações: o endereço vem só de REMOTE_ADDR; atrás de proxy, todos compartilhariam o mesmo contador até que o encaminhamento confiável seja configurado. Um atacante consegue bloquear por 15 minutos a conta de um funcionário conhecendo apenas o nome de usuário (negação de serviço dirigida); não há desbloqueio manual além de remover o registro em RateBucket. Não há registro em log de bloqueios. Os valores não foram ajustados ao número real de funcionários nem testados sob carga. Tela de login com erro não verificada no navegador; a marcação usa a mesma classe errorlist das demais telas.

Revisão de 06/11/2026 (desbloqueio manual e log de bloqueios), com dados fictícios em banco PostgreSQL temporário, já removido:

- O primeiro bloqueio de cada janela gera um único aviso no logger passport.security, com o tipo do limite e a chave derivada (HMAC), sem nome de usuário, endereço, contato ou senha. Vale para todos os limites (login, recuperação, cadastro, carimbo).
- No /admin/, a lista de usuários mostra até quando o acesso está bloqueado e oferece a ação "Desbloquear acesso da equipe", que exige permissão de alteração de usuários, grava LogEntry do Django e registra no log os ids do usuário e de quem desbloqueou. Os contadores (RateBucket) podem ser consultados pela chave do log e excluídos, o que libera bloqueios por endereço; a exclusão também é registrada.
- 40 testes passaram no PostgreSQL. O destino, a retenção e o monitoramento dos logs em produção não foram definidos.

Revisão de 06/11/2026 (dois níveis de acesso, pesquisa, intervalo configurável, identificador e insígnias), com dados fictícios em banco PostgreSQL temporário, já removido:

- 86 testes automatizados passaram no PostgreSQL, além do teste de URLs do leitor em Node. Novos testes cobrem: acesso direto às rotas por anônimo, conta sem equipe, staff sem estande, staff de estande, premiação, gestor por permissão (sem superusuário) e superusuário; POST direto à gestão sem permissão; detalhe e pesquisa sem métodos de escrita; pesquisa por trecho do nome, por celular nos formatos do cadastro (com e sem +55) e por registro legado com 55; celular parcial não lista visitantes; identificador com hífen e minúsculas; paginação de 20; outro evento invisível; celular mascarado e ausência de número completo, hash do PIN e digest na página; auditoria sem o termo; alteração do intervalo com auditoria e log, valores inválidos, CSRF, valor não inteiro preservado, efeito no próximo carimbo e textos do visitante; identificadores únicos, estáveis, nova tentativa em colisão e restrição no banco; migração que preenche 30 passaportes legados sem alterar outros campos; insígnias pendentes, conquistadas só após POST confirmado, código inválido sem conquista, estandes extras ou inativos e área não identificada.
- Concorrência no PostgreSQL: dois cadastros simultâneos com o mesmo identificador forçado resultam em um registro e um IntegrityError; alteração do intervalo simultânea a um carimbo termina com resultado coerente com um dos dois valores e uma única auditoria. O teste anterior de dois carimbos concorrentes continua aprovado.
- Brave headless com viewport emulado de 320 e 1280 pixels: passaporte com insígnias, painel da equipe, pesquisa com resultados e sem resultados, detalhe e gestão, sem rolagem horizontal. Na largura de 320 px a tabela vira lista rotulada. Contraste calculado: textos novos de 4,5:1 ou mais; contorno tracejado da insígnia pendente 3,6:1; o estado também é indicado por texto ("A conquistar"/"Conquistada às") e pela marca de verificação.
- Não verificado: aparelhos Android e iOS reais, leitor de tela, navegação por teclado nas novas telas, zoom de 200%, desempenho da pesquisa por nome com volume real (icontains sem índice de texto) e carga. visual.css passou de 16,4 kB para 22,2 kB sem compressão; o tamanho transferido não foi medido.
- Limitações: a área do estande é deduzida do nome; a insígnia é a mesma para todos os visitantes daquela área, e a personalização vem de nome, identificador e progresso; o identificador pode ser visto por terceiros e não autentica ninguém; a auditoria fica no banco sem política de retenção definida.

Revisão de 06/11/2026 (endereço do cliente atrás de proxy), sem dados pessoais:

- A primeira versão (DJANGO_TRUSTED_PROXY_HOPS, nunca publicada em commit) aceitava X-Forwarded-For sem verificar a origem da conexão: um acesso direto à aplicação escolhia o endereço contado nos limites. Foi substituída.
- Regra atual: DJANGO_TRUSTED_PROXIES lista IPs ou redes (CIDR) dos proxies. Vazio (padrão) = só REMOTE_ADDR. O cabeçalho só é lido se REMOTE_ADDR pertence à lista; a cadeia é lida da direita para a esquerda pulando proxies da lista, e o primeiro endereço fora dela é o cliente. Entradas mais à esquerda nunca são lidas. Cabeçalho ausente, entrada inválida ou com porta e cadeia com mais de 20 entradas fazem valer o endereço do proxy (mais restritivo, nunca mais permissivo). Configuração inválida, rede com host bits ou 0.0.0.0/0 e ::/0 impedem a inicialização; DJANGO_TRUSTED_PROXY_HOPS diferente de 0 também, para não ser ignorado em silêncio.
- 106 testes passaram no PostgreSQL. Novos testes: padrão ignora o cabeçalho; acesso direto com cabeçalho forjado em IPv4 e IPv6; um proxy de confiança; entradas forjadas à esquerda; IPv6 e IPv4 mapeado em IPv6; rede CIDR; dois proxies; cliente que pula o proxy de borda e finge ter passado por ele; proxy não confiável na cadeia; conexão de proxy não confiável; cadeia só de proxies; dez formatos de cabeçalho inválido; cadeia longa; REMOTE_ADDR inválido; validação da configuração; limite do login por visitante atrás do proxy; atacante direto que alterna o cabeçalho continua bloqueado.
- Teste com proxy real, em rede Docker isolada e removida ao final (sem portas publicadas): dois nginx 1.27 (borda e interno, com $proxy_add_x_forwarded_for) à frente de um servidor mínimo que só chama client_address(), sem banco. Em IPv4 e IPv6, com três configurações (nenhum proxy, só o interno, ambos): acesso direto com cabeçalho forjado contou o endereço real da conexão; pelos dois proxies confiáveis contou o cliente, ignorando o valor forjado; confiando só no interno contou o endereço do proxy de borda; quem acessou o interno diretamente fingindo ter passado pela borda contou o próprio endereço; cabeçalho com entrada inválida à esquerda não afetou o resultado.
- Não verificado: balanceadores gerenciados, CDN, cabeçalho Forwarded (RFC 7239) e X-Real-IP (não são lidos), proxies que sobrescrevem em vez de acrescentar ao cabeçalho, servidor de aplicação de produção (gunicorn/uWSGI) e o bloqueio de acesso direto, que depende da rede da implantação. Redes compartilhadas do local (Wi-Fi do evento com NAT ou operadora móvel com CGNAT) continuam somando tentativas de muitos visitantes num único endereço; os limites por endereço (100 cadastros e 100 recuperações por janela, 50 logins) não foram dimensionados para isso.

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
3. Fazer revisão de segurança: o limite de tentativas do login da equipe e do admin ainda precisa de ajuste ao tamanho real da equipe e da definição de DJANGO_TRUSTED_PROXIES e do bloqueio de acesso direto conforme a implantação (o desbloqueio manual pelo /admin/ já existe, mas falta definir quem o executa durante o evento); endurecer acesso e sessões, política de senhas, logs e proxy confiável, uso seguro de segredos e recuperação. A chave atual também participa da derivação dos identificadores de contato: rotação sem estratégia poderá impedir recuperação.
4. Endurecer e testar limites de tentativas sob carga e atrás do proxy; evitar bloqueio indevido de toda uma rede compartilhada; simular abuso, concorrência, mudança de sessão, fraude e indisponibilidade. Revisar possibilidade de vazamento de códigos temporários em URLs e logs.
5. Validar aviso e tratamento de dados com responsáveis institucionais: finalidades, contato, consentimento, retenção, menores, direitos e operação de suporte. O consentimento mostrado é provisório.
6. Testar jornada completa e QR em aparelhos Android/iOS reais, redes móveis lentas e redes do local; testar navegabilidade por teclado, leitor de tela, contraste e zoom com evidências. Não há alegação de conformidade WCAG.
7. Aprovar identidade visual, conteúdo, quantidade de estandes, regras da premiação, supervisão humana e plano operacional.

## Limitações funcionais conhecidas

Telefone e e-mail não são verificados por SMS, WhatsApp ou e-mail. Conhecer o contato e o PIN é uma credencial de recuperação, não prova da identidade ou posse do telefone. Pessoas podem compartilhar contatos ou códigos; uma entrega por passaporte não garante uma entrega por pessoa. A perda do PIN exige um procedimento assistido que ainda não está implementado. Não existe uso offline. Nenhuma exportação de leads ou procedimento de exclusão/retenção foi implementado.
