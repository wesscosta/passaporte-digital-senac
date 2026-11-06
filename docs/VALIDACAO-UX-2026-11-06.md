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

## Não verificado e impedimentos

- Android/iOS reais, câmera real, leitor de tela, zoom de 200%, contraste integral, carga e rede do evento não foram testados nesta revisão. A verificação parcial não comprova conformidade WCAG.
- O comando `check --deploy` na configuração local de desenvolvimento apontou cinco avisos referentes a DEBUG, proteção de cookies, HTTPS e HSTS. Isso não é uma análise de uma configuração de produção.
- A aplicação permanece **não pronta para uso com dados reais ou no evento**. Permanecem os bloqueadores de segurança, capacidade, hospedagem, operação e privacidade descritos em `VALIDACAO.md`; não houve deploy nem homologação.
