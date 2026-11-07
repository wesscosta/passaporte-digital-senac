# Decisões e hipóteses

## Produto confirmado

Seis áreas: Tecnologia da Informação; Artes e Design; Gastronomia e Turismo; Moda e Beleza; Gestão e Comércio (GESCOM); Saúde. A premiação tem um setor próprio. O intervalo proposto é de cinco minutos entre carimbos concluídos, não uma medição de permanência. O acesso exige celular e conexão.

## Configurações provisórias

Os dados de demonstração usam um estande obrigatório por área: isso NÃO confirma se a operação terá seis ou sete estandes, quantos carimbos serão necessários, nem se todos serão obrigatórios. As regras de elegibilidade são configuráveis. Critérios do prêmio e estoque ainda não foram definidos. A sessão anterior do participante é invalidada quando ocorre recuperação.

Nome e contato podem ser usados para marketing apenas mediante escolha separada e opcional nesta implementação inicial. Texto institucional, base legal aplicável, retenção, tratamento de menores e outras obrigações devem ser validados pela instituição. A interface atual contém um aviso provisório e não pode ser usada para coleta real.

Decisão de 05/11: novos cadastros usam exclusivamente celular brasileiro com DDD; o prefixo +55 é normalizado. Registros legados com e-mail ou com prefixo 55 não são removidos e continuam elegíveis à recuperação. Isso não comprova posse do número. O texto opcional de marketing por celular tem uma nova versão de consentimento, distinta dos registros anteriores; permanece provisório e sujeito à revisão institucional. A marca, as cores e o motivo radial da referência visual foram incorporados para avaliação; a aplicação institucional ainda depende de aprovação.

Implementação provisória de 06/11: o cadastro pede um segmento de interesse, independente das áreas e regras dos estandes. As escolhas de imagem e de comunicação são separadas e opcionais; a escolha de imagem tem versão e horário próprios. Registros anteriores permanecem sem segmento e com imagem não informada. A referência de autorização não comprova identidade, posse do telefone ou autorização válida de responsáveis; o texto e a operação dependem de aprovação institucional e não há fluxo de revogação implementado.

Códigos de estande mudam a cada minuto. Aceita-se a janela anterior para evitar falha na virada: um código pode valer por até aproximadamente 120 segundos. QR e código não provam presença física: podem ser compartilhados. O código de retirada vale cinco minutos e pode ser regenerado, invalidando o anterior.

Decisões de 06/11 (área da equipe, gestão e insígnias):

- Gestor é quem tem a permissão passport.manage_event; o superusuário a tem implicitamente. A premiação continua restrita ao superusuário e ao grupo Premiação.
- O intervalo é configurado na tela de gestão em minutos inteiros, de 1 a 60, gravado em Event.gap_seconds (única fonte). Zerar o intervalo não é oferecido na tela, porque o intervalo é regra confirmada; o administrativo ainda permite outros valores. A mudança vale imediatamente para quem aguarda: o próximo carimbo é liberado em último carimbo + novo intervalo. Carimbos já registrados não mudam.
- O identificador do passaporte tem 8 caracteres de um alfabeto sem caracteres ambíguos, gerado com secrets e protegido por restrição única. A migração 0002 preenche os passaportes existentes sem alterar outros campos.
- A área de cada estande é deduzida do nome (sem acento e sem diferença de maiúsculas; GESCOM é aceito). Estandes com outro nome recebem insígnia neutra e aparecem sinalizados na gestão. Um campo explícito de área exigiria decisão e migração; não foi criado.
- Celular e identificador só são encontrados com valor completo, para não permitir listar visitantes por trechos de número. Nome exige ao menos 3 caracteres.

Decisões de 07/11 (correções da auditoria de UX):

- Evento desativado não encerra a sessão do visitante: o passaporte mostra "evento pausado" e volta a funcionar quando o mesmo evento é reativado. Se outro evento estiver ativo, a sessão do passaporte antigo é encerrada.
- Sessão invalidada (entrada em outro aparelho ou PIN redefinido) leva à tela de entrada com a explicação do motivo.
- A mensagem de espera usa o mesmo horário do passaporte: último carimbo + intervalo atual, arredondado para o minuto seguinte. Não exibe mais segundos.
- Sem estande obrigatório ativo, o visitante é informado de que a retirada ainda não foi liberada e a gestão recebe alerta. A regra de elegibilidade não mudou.
- Páginas 403 da equipe passam a ter explicação e navegação; a gestão não indica o /admin/ a quem não tem permissão nele.

Decisões de 07/11 (A3 e A4):

- QR lido sem sessão: o código é validado na leitura e vira um comprovante de 5 minutos no servidor. A confirmação continua explícita (um toque) depois do cadastro ou da entrada. QR não prova presença; o comprovante só estende o prazo da leitura válida.
- Comprovante em espera não é consumido; duplicidade encerra o comprovante sem novo carimbo. Visitante já conectado mantém o fluxo anterior, com o código do QR.
- O primeiro passaporte que tenta usar o comprovante o reivindica; outro visitante que entre depois no mesmo navegador não o aproveita.
- PIN perdido na resposta não é recuperável: exige nova redefinição após 1 minuto. O PIN é um tipo de texto com representação mascarada, para não aparecer em relatórios de erro.
- Redefinição de PIN pela equipe com permissão própria (passport.reset_pin), busca exata por celular ou identificador, conferência presencial declarada pelo operador e exceção restrita a gestor autorizado com justificativa. A busca usa POST para que o celular não vá para URL e logs de acesso. A ação equivalente do /admin/, que exibia o PIN em mensagem, foi retirada.

## Arquitetura em avaliação

Monólito Django com HTML renderizado no servidor, PostgreSQL, CSS local e código JavaScript mínimo. A escolha busca simplicidade operacional e páginas pequenas, mas **não significa que Python ou Django sejam intrinsecamente a melhor opção para qualquer carga**. A capacidade ainda precisa ser medida em infraestrutura semelhante à produção, com carga e critérios acordados. Não foi feita comparação experimental com Node.js, Go ou outras alternativas.

Redis, CDN e arquitetura distribuída não são pressupostos; avaliar conforme medições e implantação. Estáticos precisam de cache e compressão, sem armazenar dados pessoais em cache compartilhado. WSGI e ASGI são alternativas de implantação; trocar para ASGI não torna automaticamente assíncronas as views ou as operações de banco já escritas.

Decisão de 06/11 (endereço do cliente): X-Forwarded-For só é considerado quando a conexão vem de um proxy listado em DJANGO_TRUSTED_PROXIES; a lista vem vazia e não há presunção sobre as redes de produção. Em inconsistência, vale o endereço do proxy.

## Questões em aberto

- Quantidade de estandes e regra final de conclusão.
- Data, duração, distribuição de chegada, pico simultâneo e infraestrutura de internet do evento.
- Política de privacidade, suporte ao esquecimento do PIN, autenticação da equipe e procedimentos para menores.
- Forma de entrega, conferência de estoque, prevenção de fraude e tratamento de incidentes.
- Aprovação institucional de conteúdo, identidade visual e textos, inclusive do desenho das insígnias derivado dos selos do PDF.
- Associação definitiva entre estandes e áreas, caso os nomes não coincidam com as seis áreas de referência.
- Limites aceitáveis do intervalo entre carimbos e quem pode ser gestor.
- Endereços dos proxies de produção, bloqueio de acesso direto e limites por endereço adequados ao NAT da rede do evento.
