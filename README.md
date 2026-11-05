# Passaporte Digital — Circuito Senac

Protótipo funcional local. **Não está pronto para uso com participantes reais ou publicação.** As seis áreas são dados demonstrativos, não a confirmação da quantidade definitiva de estandes ou carimbos.

## Primeira execução na máquina de desenvolvimento

A partir desta pasta, com Docker disponível:

    docker compose up -d db
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
    export DJANGO_DEBUG=1
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py seed_demo
    .venv/bin/python manage.py runserver 127.0.0.1:8000

Abra http://127.0.0.1:8000 no navegador desta máquina. O processo e o PostgreSQL foram configurados para escutar somente no loopback. Um celular não conseguirá abrir QR codes que apontam para localhost; uma demonstração em outros aparelhos exige endereço e configuração de rede apropriados e autorizados.

Para executar os testes:

    export DJANGO_DEBUG=1
    .venv/bin/python manage.py test passport.tests -v 2
    .venv/bin/python manage.py check

O PostgreSQL local fica em 127.0.0.1:55432, em volume Docker do projeto. As credenciais e configurações de desenvolvimento não são adequadas a produção. O arquivo .env.example documenta as variáveis; ele não é carregado automaticamente.

## Fluxos implementados

- Cadastro com nome, celular brasileiro com DDD, PIN e escolha opcional de marketing.
- Recuperação por contato + PIN, com invalidação de sessões anteriores do participante. O PIN não comprova posse do número nem identidade.
- Código e QR temporários por estande. A equipe precisa estar autenticada e atribuída ao estande.
- Leitura do QR pelo navegador com câmera autorizada; digitação de código e câmera nativa do celular como alternativas. O decodificador local é carregado sob demanda.
- Carimbo único por estande, com intervalo entre registros e validação transacional no PostgreSQL.
- Setor de premiação separado: geração de código e QR de retirada, consulta da equipe e confirmação explícita, uma entrega por passaporte.

Os limites de tentativas estão implementados parcialmente. Leia docs/VALIDACAO.md antes de avaliar qualquer implantação.

## Equipe e dados demonstrativos

O comando seed_demo cria as seis áreas e o grupo Premiação. Não cria senhas nem contas de equipe. Para configurar usuários locais, crie uma conta administrativa de desenvolvimento com:

    .venv/bin/python manage.py createsuperuser

Depois, no /admin/, atribua a cada funcionário a propriedade de equipe e os estandes correspondentes. Funcionários da premiação precisam pertencer ao grupo Premiação. Superusuários têm acesso ampliado. Não compartilhe credenciais.

O cadastro local sintético anterior, ui.smoke@example.invalid, é um registro legado e não foi excluído. Novos cadastros aceitam apenas celular; a recuperação mantém compatibilidade com os contatos anteriores.

O leitor alternativo usa jsQR 1.4.0 (Apache-2.0); o arquivo e a licença ficam em passport/static/passport/vendor. O logotipo incorporado foi extraído do PDF de referência fornecido; seu uso institucional ainda deve ser aprovado.

## Estrutura e pendências

- docs/DECISOES.md: hipóteses de produto e arquitetura.
- docs/VALIDACAO.md: evidências e impedimentos para uso real.
- .claude/skills/: cópias de instruções de UI/UX e validação em escopo do projeto; ambas estão em validação.

Não existe homologação jurídica, de acessibilidade, de segurança, de carga nem de operação de evento.
