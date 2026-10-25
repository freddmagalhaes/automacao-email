# Plano de ação adaptado à automação existente

## Decisão de arquitetura

Manter os dois fluxos de recebimento/processamento, Gmail, Gemini e o contrato da tabela `public.qualitcontrol_email_atendimento`. Acrescentar Streamlit para o piloto e um terceiro workflow n8n para enviar as respostas aprovadas por pessoas. Usar PostgreSQL como fonte oficial de status, rascunhos, reservas, fila e auditoria.

O pacote implementa a infraestrutura e um piloto funcional. A homologação com suas contas depende da configuração das credenciais e dos testes externos descritos abaixo.

## Situação identificada nos arquivos

| Componente | Situação no export | Tratamento no pacote |
|---|---|---|
| Receptor Gmail | Consulta não lidos a cada minuto e chama o fluxo 02 por mensagem | Preservado, com ID do subfluxo já vinculado |
| Treinamento Gemini | Conteúdo integral dentro do nó Analisar e redigir | Preservado e verificado por hash |
| Duplicidade | Chave mailbox/message_id e controle por execução | Preservados |
| Revisão pela IA | Decisão e rascunho salvos em resultado JSONB | Lidos pelo painel |
| Revisão antes da IA | Ramo de não elegíveis encerrava sem persistir | Passa a registrar a mensagem |
| Resultado incerto | Bloqueio de reenvio na automação | Mantido também na interface/fila humana |
| Resposta humana | Ausente nos dois exports | Painel, reserva, rascunho, aprovação e fluxo 03 |
| Inicialização | Criação manual da tabela e seleção de credenciais | Compose cria bancos, aplica SQL e importa fluxos/credenciais |

## Etapa 1 — Validar o ambiente isolado

**Entregue:** Dockerfile, Compose, inicialização, sete testes automatizados e mensagem fictícia no painel.

**Aceite:** serviços saudáveis, fluxos desativados e envios bloqueados; assumir e salvar rascunho funciona; uma segunda sessão não assume a mesma mensagem durante a reserva.

## Etapa 2 — Conectar uma conta de testes

Configurar OAuth Gmail e chave/modelo Gemini. Manter `ENABLE_EMAIL_SEND=false` e `ENABLE_AUTO_REPLY=false`. Confirmar o endereço em `AUTOMATION_EMAIL` e publicar apenas os fluxos necessários ao recebimento/processamento.

**Aceite:** um e-mail real de teste é persistido com remetente, assunto e corpo; uma resposta proposta pela IA aparece como rascunho de revisão; conteúdo indisponível ou falha da IA aparece para diagnóstico sem disparo de mensagem.

## Etapa 3 — Homologar a resposta humana

Definir `ENABLE_EMAIL_SEND=true` e manter `ENABLE_AUTO_REPLY=false`. Publicar o fluxo 03. Conferir a conversa no Gmail, assumir a mensagem, editar, salvar e aprovar pela tela.

**Aceite:** uma única resposta na thread correta, status enviado no banco, ID retornado pelo Gmail persistido e autoria humana na auditoria. Testar também falha simulada controlada e confirmar que não há reenvio automático.

## Etapa 4 — Definir as regras de operação

Decidir quem pode atender, o que aparece na fila, prazos, prioridades, política para casos `nao_responder`, tratamento de anexos e rotina de conferência de envios incertos. Definir se respostas automáticas continuam habilitadas e para quais categorias. Não usar somente uma nota de confiança declarada pela IA como autorização de envio.

**Aceite:** responsáveis e critérios documentados; nenhuma pendência depende apenas de consultar logs de execução; existe procedimento para indisponibilidade do modelo/provedor e para reservas paradas.

## Etapa 5 — Preparar uma versão operacional

Antes de conectar a caixa definitiva: consultar histórico completo da thread, detectar novas respostas antes de enviar, sincronizar intervenções feitas diretamente no Gmail, implementar métricas e SLA, monitorar pendências, definir retenção e validar restauração de backups. Habilitar OIDC/perfis e HTTPS na implantação compartilhada.

Se houver equipes, distribuição de trabalho, permissões detalhadas e uma experiência de atendimento permanente, implementar a interface e a camada de aplicação em Django. O n8n pode continuar responsável pelos conectores e a estrutura da fila pode ser reaproveitada mediante migrações versionadas.

**Aceite:** teste de carga compatível com o volume real, restauração validada, controle de acesso por usuário e fluxo completo homologado pela equipe.

## Dados para dimensionar a próxima versão

- Quantidade de caixas e volume diário/pico de e-mails.
- Número de atendentes simultâneos e necessidade de equipes/perfis.
- Tipos/tamanhos de anexos e regras para CC/BCC e responder a todos.
- Prazo de atendimento, retenção e integrações com CRM/ERP.
- Versões, backup e estrutura do Compose atual, somente quando for planejar a migração.

Não é necessário fornecer senhas ou tokens em chat. As credenciais devem ser configuradas diretamente no ambiente.
