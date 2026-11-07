# Validação da interface — 06/11/2026

Escopo: identidade no cabeçalho e rodapé, grafismo lateral, redução de setas decorativas, largura do conteúdo e ação da tabela da equipe. As mudanças não alteram regras de carimbo, permissões ou armazenamento.

## Verificado

- 112 testes automatizados do projeto passaram no PostgreSQL, com banco de teste isolado.
- Brave/Chromium headless: início em 320, 375, 430, 768, 1024, 1280 e 1600 px sem rolagem horizontal; cadastro e passaporte em 320 px; painel da equipe em 768, 1024 e 1280 px; pesquisa e QR do estande em 768 px. O nome e o contato fictícios permaneceram no formulário após um erro de validação. As imagens de insígnia carregaram.
- A pesquisa da equipe foi verificada também em 320, 700, 768, 800 e 1024 px, sem rolagem horizontal; o link de detalhes apresentou alvo de 44 px de altura.
- Na página inicial em 320 px, os cinco primeiros alvos acessados por Tab apresentaram foco visível. O grafismo lateral não intercepta ponteiros.
- O aviso global repetido e o texto de desenvolvimento do rodapé foram retirados; um aviso de teste permanece no cadastro enquanto o sistema não estiver homologado para dados reais.

## Revisão adicional de laterais, rodapé e registro

- 115 testes passaram no PostgreSQL, em banco de teste isolado. As regras e os dados do ambiente principal não foram alterados.
- O grafismo foi separado em dois SVGs com fundo transparente e sem elementos cortados na junção vertical. O arquivo original enviado foi preservado.
- Brave/Chromium headless: início em 320, 375, 768, 1280, 1600 e 1920 px e passaporte em 320, 480, 601, 768, 900, 1024, 1280 e 1920 px, sem rolagem horizontal. Na amostra de seis estandes, os cartões ocuparam a largura disponível; o número de estandes continua dinâmico.
- Os três links do rodapé tiveram altura de 44 px; o link Como funciona abriu a seção correspondente e Área da equipe levou ao acesso de equipe. Para as cores declaradas no CSS, o contraste calculado é 6,56:1 no texto secundário e 12,95:1 na navegação, sobre o fundo do rodapé.
- A grade foi simulada no navegador com 1, 2, 3, 6, 7 e 9 cartões, em 320, 768 e 1920 px, sem rolagem horizontal. Essa simulação alterou apenas a página temporária, não os dados do evento.
- O cartão inteiro de registro é um único link. Clique e teclado abriram a página que contém as opções de QR e código; a câmera não foi ativada automaticamente. A informação de espera também permanece associada ao link quando exibida.

## Revisão do cadastro

- O botão de criar passaporte ocupa 100% da largura do formulário, sem alterar o botão de recuperação.
- Brave/Chromium headless: largura do botão igual à do formulário em 320, 375, 768 e 1280 px, sem rolagem horizontal.
- Após o ajuste, 116 testes passaram no PostgreSQL em banco de teste isolado; `manage.py check` não apontou problemas.

## Revisão do painel de estande e falha de sessão

- Nesta revisão anterior, o QR foi ampliado e o código manual foi posicionado abaixo; a apresentação compacta preservava a identidade e o retorno aos estandes. QR e código derivam da mesma janela e são renovados a cada minuto, independentemente do intervalo entre carimbos.
- Brave/Chromium headless: QR e código visíveis sem rolagem nas janelas testadas de 320×800, 375×812, 768×1024, 1024×768, 1366×768 e 1920×1080, sem rolagem horizontal. Falha e retorno de rede foram simulados: o QR vencido fica oculto e o código indisponível até atualização válida.
- Foram executados 122 testes no PostgreSQL e três testes JavaScript. A resposta CSRF permanece 403, com opção para reabrir a página sem reenviar dados. Um teste reproduziu o token antigo após login em outra aba; isso é uma hipótese para o caso observado, não prova de sua causa.

## Revisão provisória do formulário de cadastro

- Segmento de interesse obrigatório em seletor móvel, nome completo e celular; imagem e comunicações em caixas independentes, opcionais e desmarcadas. O PIN permanece obrigatório para recuperação.
- Brave/Chromium headless em 320, 375, 768 e 1280 px: sem rolagem horizontal; caixas alinhadas com seus rótulos; botão com a largura do formulário; erro e cadastro verificados com dados fictícios. A análise não substitui validação em aparelhos reais ou por leitor de tela.

## Painel de exibição e máscara de celular

- Cada cartão da equipe abre o estande em nova aba e informa isso no texto; o painel anterior continua disponível. A tela de exibição não tem mais o botão de retorno e destaca QR e código manual juntos.
- Contagem regressiva e barra indicam a próxima troca, calculada a partir da janela informada pelo servidor; não indicam o fim da aceitação do código anterior nem o intervalo entre carimbos. Na verificação em navegador, QR e código mudaram juntos na virada real de um minuto. Em falha de atualização o código anterior é ocultado; a próxima tentativa ocorre automaticamente.
- Cadastro: rótulo Celular/WhatsApp com DDD e máscara progressiva, inclusive para colagem e DDI +55. O servidor continua validando e normalizando o número; a máscara não prova posse nem descarta dígitos excedentes.
- Brave/Chromium headless: 1280×720, 1366×768, 1024×768, 768×1024 e 320×800 sem rolagem horizontal; QR, código e barra visíveis nas janelas testadas. Digitação da máscara testada em 375 px. Não substitui teste em aparelhos, câmeras, teclados móveis ou leitores de tela reais.
- Suíte com 129 testes passou em PostgreSQL isolado; nove testes JavaScript passaram. No teste em SQLite houve erro de tabela bloqueada no teste de logins simultâneos. A cópia SQLite da rede é apenas uma demonstração, não ambiente para o evento.

## Não verificado e impedimentos

- Android/iOS reais, câmera real, leitor de tela, zoom de 200%, contraste integral, carga e rede do evento não foram testados nesta revisão. A verificação parcial não comprova conformidade WCAG.
- O comando `check --deploy` na configuração local de desenvolvimento apontou cinco avisos referentes a DEBUG, proteção de cookies, HTTPS e HSTS. Isso não é uma análise de uma configuração de produção.
- A aplicação permanece **não pronta para uso com dados reais ou no evento**. Permanecem os bloqueadores de segurança, capacidade, hospedagem, operação e privacidade descritos em `VALIDACAO.md`; não houve deploy nem homologação.
