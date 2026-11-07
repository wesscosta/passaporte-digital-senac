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

- Cadastro com nome completo, celular brasileiro com DDD, um segmento de interesse e PIN. As escolhas de autorização de imagem e de comunicações são separadas, opcionais e registradas com versão provisória e horário.
- Recuperação por contato + PIN, com invalidação de sessões anteriores do participante. O PIN não comprova posse do número nem identidade.
- Código e QR temporários por estande. A equipe precisa estar autenticada e atribuída ao estande.
- Leitura do QR pelo navegador com câmera autorizada; digitação de código e câmera nativa do celular como alternativas. O decodificador local é carregado sob demanda.
- QR lido antes do cadastro ou da entrada: o servidor valida o código na leitura e guarda um comprovante de 5 minutos, vinculado à sessão (o valor fica só na sessão; o banco guarda o digest), ao evento e ao estande. Ele sobrevive à troca da chave de sessão no cadastro ou entrada e é consumido uma única vez, na mesma transação do carimbo, que revalida evento, estande, intervalo e duplicidade. Em espera, o comprovante continua válido até expirar. QR inválido ou vencido não gera comprovante.
- Redefinição de PIN na Área da Equipe (/equipe/pin/), com permissão própria e conferência presencial; ver abaixo.
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

## Estáticos e versão publicada

Em produção (config.settings_production), os estáticos usam nomes com hash do conteúdo (CompressedManifestStaticFilesStorage do WhiteNoise), gerados pelo collectstatic do Dockerfile. Um arquivo novo nunca é servido com o endereço de um antigo. Informe o commit no build para que a resposta traga o cabeçalho X-App-Version:

    APP_COMMIT=$(git rev-parse --short HEAD) docker compose -f compose.prod.yaml build

O valor só é aceito se for um hash hexadecimal de 7 a 40 caracteres. Ele identifica o commit informado, não detecta alterações locais não commitadas.

## Equipe e dados demonstrativos

O comando seed_demo cria as seis áreas e o grupo Premiação. Não cria senhas nem contas de equipe. Para configurar usuários locais, crie uma conta administrativa de desenvolvimento com:

    .venv/bin/python manage.py createsuperuser

Depois, no /admin/, atribua a cada funcionário a propriedade de equipe e os estandes correspondentes. Funcionários da premiação precisam pertencer ao grupo Premiação. Não compartilhe credenciais.

Níveis de acesso (todos exigem a propriedade de equipe, is_staff):

- Staff de estande: exibe QR e código dos estandes atribuídos e consulta passaportes.
- Premiação: grupo Premiação; consulta passaportes e confirma entregas pelo código de retirada.
- Gestão: permissão "Pode gerenciar o evento ativo e o intervalo entre carimbos" (passport.manage_event). O superusuário a recebe implicitamente. Como is_superuser concede todas as permissões do Django, inclusive no /admin/, é mais seguro criar um grupo de gestão só com essa permissão e conceder superusuário apenas a quem administra o sistema. A permissão de gestão sozinha não libera a premiação. Nenhuma conta é promovida automaticamente.
- Redefinição de PIN: permissão "Pode redefinir o PIN de visitantes após conferência presencial" (passport.reset_pin). Não decorre de is_staff nem da gestão; o superusuário a tem implicitamente.

### Como conceder a redefinição de PIN

1. No /admin/, em Grupos, crie um grupo (por exemplo, "Redefinição de PIN") com somente a permissão passport | evento | "Pode redefinir o PIN de visitantes após conferência presencial".
2. Adicione ao grupo apenas as pessoas do atendimento que farão essa conferência. A conta precisa ter a propriedade de equipe (is_staff); não precisa de nenhuma outra permissão no /admin/.
3. A opção "Redefinir PIN" aparece no painel da equipe. A busca aceita só o celular completo ou o identificador do passaporte (com ou sem hífen) do evento ativo, nunca o nome.
4. O operador registra como conferiu, com o visitante presente, o acesso ao número cadastrado (número exibido no próprio aparelho, ou ligação ou mensagem de teste recebida nele). Nome e número conhecidos não comprovam identidade. Não há SMS nem WhatsApp automáticos.
5. Exceção sem essa conferência: só para quem é gestor (passport.manage_event) e também tem passport.reset_pin, com justificativa de pelo menos 20 caracteres.
6. O PIN de 6 dígitos é aleatório, gravado só como hash, e mostrado uma única vez numa página sem cache. Não vai para URL, mensagem, log nem auditoria. As sessões do visitante em outros aparelhos são encerradas. A auditoria guarda operador, passaporte, horário, método e, na exceção, a justificativa.
7. Limites: 30 buscas por operador e 20 redefinições por operador a cada 10 minutos; 3 redefinições por passaporte por hora; uma segunda redefinição do mesmo passaporte em menos de 1 minuto é recusada (proteção contra reenvio). A ação de redefinir PIN no /admin/ foi retirada.
8. Se a resposta com o novo PIN se perder (rede caiu, aba fechada, erro ao montar a página): o PIN já foi trocado e as sessões do visitante já foram encerradas, mas ninguém conhece o novo valor, e ele não pode ser recuperado (só o hash é gravado). Recarregar ou reenviar o formulário não mostra nem gera PIN. Aguarde 1 minuto e faça uma nova redefinição, com nova conferência; ela conta no limite de 3 por hora. Em relatórios de erro (página de depuração ou e-mail de erro), o PIN aparece como [PIN oculto].

### Comprovantes de leitura do QR

O comprovante criado quando um QR é lido sem sessão vale 5 minutos. O valor fica só na sessão (gravada no banco; o cookie leva apenas a chave da sessão) e o banco guarda o digest. O primeiro passaporte que tenta usá-lo o reivindica: se outra pessoa entrar depois no mesmo navegador, a leitura não serve para ela.

Limpeza: a cada novo comprovante, os vencidos há mais de um dia (usados ou não) são apagados. Não há tarefa agendada; num período sem leituras, os vencidos ficam na tabela até a próxima leitura. Eles não têm dado pessoal, só evento, estande, horários e, se usados, o passaporte. Para apagar manualmente os vencidos: `python manage.py shell -c "from django.utils import timezone; from passport.models import ScanVoucher; print(ScanVoucher.objects.filter(expires_at__lt=timezone.now()).delete())"`.

### Migração 0004 (comprovante do QR e permissão de redefinição)

- Aditiva: cria a tabela passport_scanvoucher e a permissão passport.reset_pin. Não altera nem lê tabelas existentes; o tempo de execução independe do volume de passaportes.
- Ordem: backup do banco, build da imagem nova, `docker compose -f compose.prod.yaml run --rm web python manage.py migrate`, `up -d web`. Conceda a permissão (seção anterior) depois do deploy.
- Rollback só de código (recomendado): suba a imagem anterior sem reverter a migração. A versão anterior funciona com o banco em 0004 (testado): ignora a tabela e a permissão. Comprovantes em andamento se perdem e o visitante lê o QR de novo; o grupo com reset_pin fica sem efeito e a ação de PIN do /admin/ da versão anterior volta para o superusuário.
- Reverter o esquema, se necessário, com a imagem nova antes de trocar: `python manage.py migrate passport 0003`. Remove só a tabela de comprovantes; passaportes, carimbos e entregas não mudam. A permissão continua cadastrada, sem efeito.

O cadastro local sintético anterior, ui.smoke@example.invalid, é um registro legado e não foi excluído. Novos cadastros aceitam apenas celular; a recuperação mantém compatibilidade com os contatos anteriores.

O leitor alternativo usa jsQR 1.4.0 (Apache-2.0); o arquivo e a licença ficam em passport/static/passport/vendor. O logotipo incorporado foi extraído do PDF de referência fornecido; seu uso institucional ainda deve ser aprovado.

## Estrutura e pendências

- docs/DECISOES.md: hipóteses de produto e arquitetura.
- docs/VALIDACAO.md: evidências e impedimentos para uso real.
- .claude/skills/: cópias de instruções de UI/UX e validação em escopo do projeto; ambas estão em validação.

Não existe homologação jurídica, de acessibilidade, de segurança, de carga nem de operação de evento.

## Perfis operacionais e exportação detalhada — 07/11/2026

O comando `python manage.py configure_event_team` configura as contas dedicadas staff_local, premiacao_suporte e gestor_local. Exige exatamente um evento ativo e a migração de reset_pin. Staff recebe os estandes ativos; premiação/suporte recebe o grupo Premiação e reset_pin; gestor recebe manage_event. Não concede superusuário. Substitui grupos/permissões das três contas operacionais; recusa contas já superusuárias e grupo Premiação com permissões adicionais para permitir revisão. Não altera outras contas.

Senhas aleatórias são exibidas apenas para contas novas. Para redefini-las explicitamente, use --reset-passwords. Execute em terminal privado, sem gravação de saída. Visitantes usam cadastro individual e PIN, não conta de equipe compartilhada.

A gestão exporta CSVs de participantes e visitas do evento ativo. Inclui dados cadastrais, escolhas de autorização com versão/data, carimbos e situação da retirada. Os CSVs contêm evento, data de geração com fuso e proteção contra fórmulas; não incluem PIN, hashes, tokens ou sessões. Cada download gera report.export na auditoria. Guardar o arquivo com acesso restrito. O relatório agregado permanece disponível.
