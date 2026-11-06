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
- Identificador de passaporte (ex.: ABCD-2345), único no banco, exibido ao visitante e usado no atendimento. Não é senha nem prova de identidade.
- Insígnias por estande: selo "a conquistar" até o servidor confirmar o carimbo; depois, "conquistada", com horário.
- Área da equipe em dois níveis: staff (estandes atribuídos e consulta de passaportes) e gestão (intervalo entre carimbos do evento ativo).
- Pesquisa de passaportes por nome, celular completo ou identificador, paginada, com celular mascarado e registro de auditoria sem o termo pesquisado.
- Limite de tentativas no login da equipe e do /admin/, com desbloqueio manual no /admin/ e log de bloqueios sem dados pessoais.

Os limites de tentativas estão implementados parcialmente. Leia docs/VALIDACAO.md antes de avaliar qualquer implantação.

## Implantação atrás de proxy

Os limites de tentativas por endereço usam REMOTE_ADDR. Atrás de um proxy reverso, sem configuração, todos os visitantes aparecem com o endereço do proxy e dividem o mesmo contador.

DJANGO_TRUSTED_PROXIES recebe os IPs ou redes (CIDR) exatos dos proxies, separados por vírgula, por exemplo (fictício) `192.0.2.10,2001:db8::10`. Condições para que o endereço do visitante seja confiável:

- A aplicação não pode ser acessível diretamente, só pelos proxies listados (firewall, rede privada ou bind em interface interna). Se um proxy listado também aceitar conexões de fora, ele precisa ser a borda ou estar protegido da mesma forma.
- Cada proxy listado deve acrescentar o endereço de quem o conectou ao X-Forwarded-For (no nginx, `$proxy_add_x_forwarded_for`). Proxies que substituem o cabeçalho também funcionam; proxies que repassam o valor do cliente sem acrescentar nada não podem ser listados.
- Liste todos os proxies da cadeia. Se faltar o de borda, todos os visitantes contarão com o endereço dele; se sobrar uma rede ampla, máquinas dentro dela poderão escolher o endereço contado.
- Forwarded (RFC 7239) e X-Real-IP não são lidos.

Comportamento seguro em caso de inconsistência: sem a lista, ou com conexão de fora dela, o cabeçalho é ignorado. Cabeçalho ausente, entrada inválida ou com porta, ou cadeia com mais de 20 entradas fazem valer o endereço do proxy. Configuração inválida impede a inicialização.

Visitantes atrás do mesmo NAT (Wi-Fi do evento, operadora móvel com CGNAT) compartilham um endereço e somam tentativas no mesmo contador por endereço. Os limites por endereço precisam ser dimensionados para a rede do local antes do evento; os limites por conta e por contato não são afetados.

## Equipe e dados demonstrativos

O comando seed_demo cria as seis áreas e o grupo Premiação. Não cria senhas nem contas de equipe. Para configurar usuários locais, crie uma conta administrativa de desenvolvimento com:

    .venv/bin/python manage.py createsuperuser

Depois, no /admin/, atribua a cada funcionário a propriedade de equipe e os estandes correspondentes. Funcionários da premiação precisam pertencer ao grupo Premiação. Não compartilhe credenciais.

Níveis de acesso (todos exigem a propriedade de equipe, is_staff):

- Staff de estande: exibe QR e código dos estandes atribuídos e consulta passaportes.
- Premiação: grupo Premiação; consulta passaportes e confirma entregas pelo código de retirada.
- Gestão: permissão "Pode gerenciar o evento ativo e o intervalo entre carimbos" (passport.manage_event). O superusuário a recebe implicitamente. Como is_superuser concede todas as permissões do Django, inclusive no /admin/, é mais seguro criar um grupo de gestão só com essa permissão e conceder superusuário apenas a quem administra o sistema. A permissão de gestão sozinha não libera a premiação. Nenhuma conta é promovida automaticamente.

O cadastro local sintético anterior, ui.smoke@example.invalid, é um registro legado e não foi excluído. Novos cadastros aceitam apenas celular; a recuperação mantém compatibilidade com os contatos anteriores.

O leitor alternativo usa jsQR 1.4.0 (Apache-2.0); o arquivo e a licença ficam em passport/static/passport/vendor. O logotipo incorporado foi extraído do PDF de referência fornecido; seu uso institucional ainda deve ser aprovado.

## Estrutura e pendências

- docs/DECISOES.md: hipóteses de produto e arquitetura.
- docs/VALIDACAO.md: evidências e impedimentos para uso real.
- .claude/skills/: cópias de instruções de UI/UX e validação em escopo do projeto; ambas estão em validação.

Não existe homologação jurídica, de acessibilidade, de segurança, de carga nem de operação de evento.
