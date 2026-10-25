# Validação do ambiente de testes

Realizada em 24/10/2026, no fuso America/Sao_Paulo.

## Verificado

- `docker compose config --quiet`: configuração aceita.
- Construção da imagem Python pelo Dockerfile concluída.
- PostgreSQL 18.6, n8n 2.42.5 e painel Streamlit 1.66.0 iniciados no projeto `qualitcontrol-email-teste`.
- Criação dos bancos, usuários e objetos SQL concluída; migração terminou com código 0.
- CLI do n8n importou três credenciais e três workflows desativados; bootstrap terminou com código 0.
- Sete testes automatizados passaram: reserva concorrente com vencedor único, persistência e isolamento do rascunho, aprovação única e confirmação, expiração para envio incerto sem reenvio, permissões do painel, interação com a tela e integridade dos grafos/treinamento.
- Os três grafos foram validados e os 11 nós JavaScript Code compilaram. A conversão de resposta automática em rascunho no modo de testes também foi exercitada sem APIs externas.
- O workflow 03 foi executado uma vez pelo próprio n8n com envio desabilitado: terminou com sucesso em `Envio habilitado?`, pelo ramo falso, sem chegar ao Gmail.

## Não exercitado com contas externas

- Consentimento OAuth Gmail, recebimento de e-mail real e entrega de resposta.
- Acesso, cota e resposta do Gemini.
- Login OIDC por um provedor externo.
- Recuperação de backups ou migração da instância atual.

O ambiente foi criado separadamente. Não foram ativados os fluxos de recepção/envio, nem usados tokens da automação existente. A demonstração utiliza dados fictícios.

O pacote ZIP exclui `.env`, credenciais OIDC locais, caches e arquivos temporários. Ao extrair em outra pasta, execute o configurador para gerar novos segredos.

## Atualização: base documental autorizada

Após autorização explícita do responsável, a cópia do fluxo 02 no projeto passou a incluir os cinco materiais de `ambiente_gpt`, com 28.019 caracteres de contexto documental. O treinamento anterior permanece verificável pelo hash original; as regras e os nós de envio foram preservados.

Foram aprovados seis testes locais adicionais: seleção das cinco fontes com conferência de integridade, preservação do treinamento e dos controles, idempotência da compilação, recusa de fonte ausente/vazia/fora da pasta, remoção de ruído XML/créditos de imagens e exclusão de miniaturas sem conteúdo verificável. O teste anterior de integridade dos workflows também passou. Os 11 nós JavaScript continuaram compilando e o Compose passou em `config --quiet`.

Nesta atualização o Docker Engine estava desligado/indisponível. O novo serviço `knowledge-build` e a atualização do workflow dentro do n8n ainda precisam de execução no Docker. Não foram repetidos os testes de banco nem feitas chamadas Gemini/Gmail. O ZIP gerado na pasta antiga não inclui esta atualização; o projeto nesta pasta é a versão atual.

## Complemento dos 21 vídeos indicados

As 21 páginas individuais foram abertas no navegador. As transcrições públicas de `DdDr88m2nzI` (37 trechos) e `YhvjvzbZlzE` (11 trechos) foram lidas. Nos outros 19 vídeos foram consultadas as descrições publicadas, pois os painéis de transcrição não apresentaram conteúdo durante a consulta. Não houve análise visual integral das demonstrações nem transcrição de áudio por serviço externo.

Foram registrados 21 resumos em palavras próprias, com identificação da fonte, tipo de evidência, data e limites. As descrições de V19 e V20 são equivalentes e não foram tratadas como comprovações independentes. A playlist não foi resolvida; os links individuais permitiram a consulta dos materiais.

A base recompilada possui cinco documentos mais 21 resumos, totalizando 40.896 caracteres de contexto documental. O treinamento anterior continua preservado pelo hash original. Foram aprovadas oito verificações da base e o teste de integridade dos workflows; os 11 nós Code também compilaram e os controles de revisão/envio passaram na validação JavaScript. O Compose continuou válido. A instalação no n8n e a chamada real ao Gemini permanecem pendentes de Docker/credenciais.

## Localização dos exports de origem

Os dois exports foram confirmados em `docker/n8n/n8n_01_receptor_gmail.json` e `docker/n8n/n8n_02_processamento_treinamento_completo.json`. O preparador passou a usar esses caminhos por padrão, inclusive no serviço Docker, preservando os arquivos de origem e gerando os três workflows prontos em `workflows/`.

Após regeneração, os hashes dos dois originais permaneceram iguais, as nove verificações locais passaram e a validação JavaScript foi concluída. A configuração Compose foi conferida usando `.env.example`: a configuração local não possuía os valores obrigatórios necessários à execução. Nenhuma credencial local foi alterada.

## Ambiente retomado após criação do .env

O `.env` criado a partir do modelo ainda tinha os cinco marcadores `GERAR_COM_CONFIGURE`. Foram recuperadas somente as senhas e a chave de criptografia da configuração previamente gerada para o mesmo projeto Docker, mantendo compatibilidade com os volumes existentes. Os demais valores locais foram preservados e nenhum segredo foi exibido.

Docker Desktop e o projeto de testes foram iniciados. A geração dos workflows e a compilação documental pelo serviço `knowledge-build`, sem rede, terminaram com código 0, assim como a migração e o bootstrap. PostgreSQL, n8n e painel ficaram disponíveis.

O fluxo 02 já instalado no n8n recebeu a base de 26 referências, com backup local anterior em `work/n8n-backups`. A verificação posterior confirmou o hash documental e a preservação das referências de credenciais. Os fluxos continuaram desativados e o envio de e-mails permaneceu bloqueado.

A execução dos testes completos identificou perda da seleção de mensagem após a mudança do status de atendimento. A seleção recebeu uma chave estável e passou a escolher uma opção válida quando a mensagem sai da fila. O teste cobre duas mensagens, salvar rascunho, aprovar e a retirada da mensagem após confirmação fictícia. Os 15 testes completos passaram após a correção, sem chamadas Gmail/Gemini.
