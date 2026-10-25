# Ambiente de testes: Gmail + n8n + PostgreSQL + Gemini + Streamlit

Pacote baseado nos dois exports fornecidos. Cria um projeto Docker independente, com bancos, volumes e rede próprios. Os arquivos originais e os serviços Docker já existentes não são modificados.

O `Dockerfile` constrói o painel Python. O `compose.yaml` organiza todos os serviços: PostgreSQL, migração SQL, importação inicial do n8n, n8n e painel. Gemini é uma API externa; não há contêiner de modelo local neste projeto.

A pasta `ambiente_gpt` é a fonte documental autorizada para as respostas. Cinco materiais distintos e os resumos de 21 vídeos consultados são incorporados ao contexto Gemini pelo nó `Base documental autorizada`. As evidências são duas transcrições e 19 descrições públicas, identificadas em `knowledge/VIDEOS.md`. O serviço local `knowledge-build` prepara o JSON antes do primeiro bootstrap; veja `knowledge/README.md` para atualizar uma instância já importada. Miniaturas e títulos isolados não são usados como conteúdo factual.

Os exports de origem estão em `docker/n8n/n8n_01_receptor_gmail.json` e `docker/n8n/n8n_02_processamento_treinamento_completo.json`. O inicializador lê esses dois arquivos, preserva os originais e gera as três versões de testes em `workflows/`, incluindo a base documental e o envio humano. O n8n importa as versões geradas; os JSONs originais não são importados em duplicidade.

## Início rápido

Requisitos: Docker Desktop com Linux containers e Docker Compose. Na pasta deste README:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Email "sua-conta-de-testes@gmail.com"
```

O script gera segredos aleatórios no `.env`, valida o Compose e inicia o ambiente. Usa Python local quando disponível; caso contrário, usa um contêiner Python temporário. Se `.env` já existir, ele será preservado: altere `AUTOMATION_EMAIL` nele para escolher a conta de testes.

Se o `.env` foi copiado do exemplo e ainda contém `GERAR_COM_CONFIGURE`, ele não está pronto para execução. Ao recuperar este mesmo projeto a partir de uma configuração anterior, use `python scripts/configure.py --reuse-env "CAMINHO_DO_ENV_ANTERIOR"`. O comando só completa os cinco segredos ausentes/de exemplo, exige o mesmo nome de projeto e preserva os demais valores. Reutilize a chave e as senhas correspondentes aos volumes existentes; o texto de exemplo não é uma senha gerada.

Alternativa com Python instalado:

```powershell
python scripts/configure.py --email "sua-conta-de-testes@gmail.com"
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

| Serviço | Acesso local | Uso |
|---|---|---|
| n8n | http://localhost:5679 | Configuração, credenciais e workflows |
| Painel | http://localhost:8501 | Triagem, rascunho e aprovação de respostas |
| PostgreSQL | localhost:55433 | Conexão opcional por cliente SQL |

As portas são vinculadas a `127.0.0.1`. O painel começa em `AUTH_MODE=local`, com identidade **simulada** `operador_teste`, para testes na própria máquina. Este modo não autentica pessoas. O login OIDC opcional é explicado abaixo.

Os serviços `db-migrate` e `n8n-bootstrap` terminam com código 0 após concluir suas tarefas. Isso é esperado. PostgreSQL, n8n e painel continuam em execução.

## O que é automatizado

- Criação de dois bancos: `n8n` para dados internos e `atendimento` para os e-mails.
- Criação de usuários PostgreSQL separados: `n8n_app`, `automacao_app` e `painel_app`.
- Criação da tabela original `public.qualitcontrol_email_atendimento` e das tabelas de atendimento humano.
- Aplicação idempotente do SQL, verificação de saúde e ordem de inicialização.
- Importação dos três workflows, desativados, e vínculo do receptor ao processamento por ID.
- Criação da credencial PostgreSQL do workflow, apontando para `postgres:5432`, banco `atendimento`.
- Criação das credenciais editáveis Gmail/Gemini. A chave Gemini pode ser informada no `.env` **antes do primeiro bootstrap**.
- Persistência do banco e do diretório `.n8n` em volumes próprios do projeto.

O consentimento OAuth da conta Gmail, a criação inicial do usuário administrador do n8n e a autorização de chamadas à API Gemini exigem configuração da sua conta. O pacote não contém tokens nem senhas da automação existente.

## Primeira configuração no n8n

1. Abra http://localhost:5679 e conclua o cadastro do proprietário desta instância de testes.
2. Abra a credencial **Gmail - Conta de Testes**. Informe Client ID e Client Secret do Google OAuth, registre no Google a URL de retorno mostrada pelo n8n e autorize a conta de testes. Em uma aplicação Google em modo Testing, inclua essa conta entre os test users.
3. A URL esperada de retorno do n8n neste ambiente é `http://localhost:5679/rest/oauth2-credential/callback`. Confirme o valor mostrado na credencial.
4. Abra **Gemini - Testes** e informe uma API key válida. O modelo está em `GEMINI_MODEL`; verifique se está disponível e tem cota na sua conta. O valor inicial é configurável, não representa garantia de disponibilidade.
5. Teste **PostgreSQL - Atendimento Teste**. Não use `localhost` dentro do contêiner: o host interno é `postgres`.
6. Confirme que `AUTOMATION_EMAIL` corresponde exatamente à conta Gmail autorizada. Após mudar `.env`, execute `docker compose up -d`.
7. Abra o fluxo 02, confira o modelo e as credenciais e publique-o conforme exigido pela versão do n8n. Publique o fluxo 01 para receber mensagens. O fluxo 03 só precisa ser publicado para o envio humano agendado.

Os dois fluxos recebidos são exports com `active=false` e campos de configuração não preenchidos, embora você tenha informado que a instância atual funciona. Isso significa que o export não carrega toda a configuração da instância. Aqui, ela é refeita de forma isolada.

## Testar sem Gmail nem IA

```powershell
Get-Content -Raw -Encoding UTF8 .\sql\demo.sql | docker compose exec -T postgres psql -U postgres -d atendimento -v ON_ERROR_STOP=1
```

Abra o painel, selecione a demonstração, assuma o atendimento, edite e salve o rascunho. Confirme a revisão e aprove a resposta para a fila. O dado fictício usa `example.invalid` e um ID Gmail inválido; serve apenas para validar a tela e o banco.

Com `ENABLE_EMAIL_SEND=false`, nenhuma resposta dessa fila é enviada pelo workflow 03. Não publique o remetente nem habilite envio durante o teste demonstrativo.

## Habilitar envio real pela tela

Depois de configurar uma caixa de testes e revisar a conversa:

```dotenv
AUTOMATION_EMAIL=sua-conta-de-testes@gmail.com
ENABLE_EMAIL_SEND=true
ENABLE_AUTO_REPLY=false
```

```powershell
docker compose up -d
```

Publique **TESTE | 03 - Envio de respostas humanas**. A cada minuto, ele reserva até uma resposta pendente da conta configurada e usa Gmail **Reply** sobre o ID original. Também existe entrada manual para processar um item durante testes.

Com essa combinação, a IA continua classificando e sugerindo, mas respostas que ela enviaria automaticamente são encaminhadas para aprovação humana. Para restaurar também os envios automáticos do fluxo 02, configure **ambas** as flags como `true` e recrie o serviço.

`ENABLE_EMAIL_SEND=false` bloqueia novos envios pelos caminhos implementados; não cancela uma chamada ao Gmail que já esteja em andamento. Os fluxos importados ficam inicialmente desativados.

## Comportamento do atendimento

- A fila apresenta revisões, envios incertos e registros ainda em processamento. Há opção para incluir `nao_responder`, que normalmente corresponde a descartes intencionais da automação.
- Somente registros `revisao_humana` ou `nao_responder`, sem envio humano registrado, podem ser assumidos para nova resposta.
- Cada sessão tem uma reserva exclusiva de 20 minutos. Salvar o rascunho renova a reserva. O texto só é persistido ao clicar em salvar ou aprovar.
- A aprovação grava texto e item da fila na mesma transação. Há restrição única por conta/mensagem contra cliques repetidos.
- O workflow 03 usa reserva transacional com `SKIP LOCKED`, muda o registro original para `envio_iniciado` e registra a autoria humana.
- Confirmação Gmail + gravação no PostgreSQL mudam o status para `enviado`. Só depois há tentativa de marcar o original como lido.
- Erro ou resposta sem ID confiável resulta em `envio_incerto`. Não há repetição automática. Envios reservados há mais de 15 minutos sem confirmação também viram incertos na próxima execução habilitada do remetente.
- Registros `reservado` do processamento original ficam visíveis para diagnóstico, sem liberação/reprocessamento automático.
- A auditoria registra assumir, salvar, liberar, aprovar, iniciar envio e resultado.

Uma API de e-mail pode aceitar o envio e a conexão cair antes da resposta. O banco não consegue tornar essa operação externa exatamente única. Por isso, o pacote interrompe os envios incertos para conferência no Gmail.

## Alterações feitas nos exports

1. Treinamento e parâmetros do nó **Analisar e redigir** preservados integralmente. O SHA-256 é registrado no `manifest.json` e conferido pelos testes.
2. IDs estáveis e credenciais do ambiente de testes vinculados automaticamente.
3. Endereço e modelo passam a vir das variáveis de ambiente.
4. Controle de envio automático pelas duas flags, com conversão para revisão humana em modo de testes.
5. O nó **Reservar mensagem uma vez** também persiste os dados recebidos, para diagnóstico se o processamento parar.
6. O ramo falso de **Email elegivel?** agora registra a mensagem. No export, ele terminava em um NoOp, incluindo casos marcados como revisão antes da IA.
7. Preparação manual do banco substituída pelo serviço de migração do Compose.
8. Novo fluxo 03 para consumir a fila humana.

Os originais foram somente lidos. Execute `python scripts/prepare_workflows.py` para gerar novamente as cópias a partir dos dois exports em `docker/n8n`. Também é possível informar dois caminhos personalizados como argumentos. O bootstrap importa apenas os arquivos dentro de `workflows/` e executa uma única vez por volume n8n; reinícios não sobrescrevem suas edições ou credenciais no n8n. O serviço `knowledge-build` regenera os JSONs locais na preparação; alterações manuais em `workflows/` devem ser reaplicadas na origem ou no gerador. Alterar exports no disco após o primeiro bootstrap não atualiza automaticamente os workflows já importados.

Para atualizar somente a base do fluxo 02 já instalado no ambiente de testes, execute `python scripts/update_knowledge_n8n.py`. Ele faz backup, exige fluxos desativados/envios bloqueados, preserva as credenciais e verifica a importação. Veja `knowledge/README.md`.

## Autenticação OIDC opcional

Para testar identidade real, copie `config/secrets.example.toml` para `config/secrets.toml`, configure seu provedor OIDC e cadastre o retorno do **painel**: `http://localhost:8501/oauth2callback`.

No `.env`:

```dotenv
AUTH_MODE=oidc
ALLOWED_EMAILS=atendente1@suaempresa.com,atendente2@suaempresa.com
```

Execute `docker compose up -d`. O painel usa `st.login()`, verifica o e-mail na lista permitida e registra a identidade retornada pelo provedor. O login do painel é independente do OAuth Gmail do n8n.

## Verificação e operação

```powershell
docker compose ps -a
docker compose logs --tail 80 n8n-bootstrap db-migrate
docker compose logs --tail 80 n8n painel
```

Para testes automatizados, instale `requirements.txt` em um ambiente Python e execute, nesta pasta:

```powershell
python -m unittest discover -s tests -v
```

Os testes usam apenas o banco local deste Compose e identificadores fictícios próprios. Verificam reserva concorrente, rascunho, aprovação única, confirmação, expiração sem reenvio, permissões, tela e integridade dos workflows. Não chamam Gmail nem Gemini.

Para interromper preservando dados:

```powershell
docker compose stop
```

Para reiniciar:

```powershell
docker compose up -d
```

Mantenha `.env` e os volumes em backup, principalmente a chave `N8N_ENCRYPTION_KEY`, necessária às credenciais. O inicializador de usuários/bancos só roda na primeira criação do volume PostgreSQL. Alterar senhas no `.env` depois disso não troca as senhas já gravadas no PostgreSQL: uma rotação exige `ALTER ROLE` e atualização da credencial correspondente no n8n.

## Limites do piloto e evolução

Esta é uma base funcional de testes para triagem e resposta de uma caixa Gmail. O painel mostra o conteúdo e a auditoria da mensagem selecionada, não baixa anexos nem carrega todo o histórico da thread no Gmail. Antes de aprovar, o atendente precisa conferir a conversa no Gmail; não há consulta automática de novas respostas externas imediatamente antes do envio. Alterações feitas diretamente no Gmail não são sincronizadas integralmente com o banco.

O painel usa texto simples para as respostas humanas. Não oferece CC/BCC, anexos de saída, múltiplas equipes, SLA completo, paginação além das 200 primeiras pendências ou reconciliação automática de envios incertos. O registro original e o worker não autorizam a interface a reenviar um caso incerto.

Para produção permanente: definir autenticação e perfis, buscar histórico completo e anexos, verificar atualização da thread antes do envio, implementar reconciliação, métricas, backup/restore, HTTPS e regras de retenção. Se esses requisitos forem imediatos, manter PostgreSQL/n8n e implementar a camada de atendimento em Django é uma evolução coerente. O `app/service.py` já separa as operações da interface para facilitar essa mudança.

## Referências oficiais

- [n8n com Docker Compose](https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md)
- [Configuração PostgreSQL do n8n](https://docs.n8n.io/hosting/configuration/environment-variables/database/)
- [Gmail Reply no n8n](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/message-operations#reply-to-a-message)
- [Imagem oficial PostgreSQL e inicialização de banco](https://hub.docker.com/_/postgres)
- [Autenticação OIDC no Streamlit](https://docs.streamlit.io/develop/concepts/connections/authentication)
