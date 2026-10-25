-- Somente dados fictícios; nunca contém um ID Gmail válido.
INSERT INTO public.qualitcontrol_email_atendimento(mailbox,message_id,owner_execution,status,resultado)
VALUES('teste@example.invalid','DEMO-SEM-ENVIO','demo','revisao_humana',
    '{"email_automacao":"teste@example.invalid","id_email":"DEMO-SEM-ENVIO","remetente":"Cliente Demonstrativo <cliente@example.invalid>","assunto_email":"Demonstração: solicitação de proposta","corpo_email":"Olá! Gostaria de conhecer os módulos do QualitControl e receber uma proposta.","motivo":"Proposta comercial exige atendimento humano.","rascunho_html":"<p>Olá! Obrigado pelo contato. Para preparar uma proposta, poderia informar o segmento e o tamanho da sua equipe?</p>","tem_anexos":false}'::jsonb)
ON CONFLICT(mailbox,message_id) DO NOTHING;
