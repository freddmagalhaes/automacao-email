BEGIN;
CREATE SCHEMA IF NOT EXISTS atendimento;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Compatível com os seis estados dos workflows fornecidos.
CREATE TABLE IF NOT EXISTS public.qualitcontrol_email_atendimento (
    mailbox text NOT NULL,
    message_id text NOT NULL,
    owner_execution text NOT NULL,
    status text NOT NULL CHECK (status IN ('reservado','envio_iniciado','enviado','envio_incerto','nao_responder','revisao_humana')),
    sent_message_id text,
    resultado jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (mailbox, message_id)
);
CREATE INDEX IF NOT EXISTS email_atendimento_status ON public.qualitcontrol_email_atendimento(status, created_at);

CREATE TABLE IF NOT EXISTS atendimento.casos (
    mailbox text NOT NULL,
    message_id text NOT NULL,
    status text NOT NULL DEFAULT 'aberto',
    responsavel text,
    session_token text,
    reservado_ate timestamptz,
    rascunho text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (mailbox, message_id),
    FOREIGN KEY (mailbox, message_id) REFERENCES public.qualitcontrol_email_atendimento
);
CREATE TABLE IF NOT EXISTS atendimento.fila_envio (
    id uuid PRIMARY KEY,
    mailbox text NOT NULL,
    message_id text NOT NULL,
    corpo_texto text NOT NULL CHECK (length(trim(corpo_texto)) BETWEEN 1 AND 20000),
    aprovado_por text NOT NULL,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','enviando','enviado','envio_incerto','bloqueado')),
    owner_execution text,
    sent_message_id text,
    erro text,
    created_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (mailbox, message_id),
    FOREIGN KEY (mailbox, message_id) REFERENCES public.qualitcontrol_email_atendimento
);
CREATE INDEX IF NOT EXISTS fila_envio_pendentes ON atendimento.fila_envio(created_at) WHERE status='pendente';
CREATE TABLE IF NOT EXISTS atendimento.auditoria (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mailbox text NOT NULL,
    message_id text NOT NULL,
    ator text NOT NULL,
    acao text NOT NULL,
    detalhe jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Sem repetição automática: perda do worker após reservar um envio exige conferência.
CREATE OR REPLACE FUNCTION atendimento.expirar_envios() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE item atendimento.fila_envio%ROWTYPE; total integer := 0;
BEGIN
    FOR item IN SELECT * FROM atendimento.fila_envio
        WHERE status='enviando' AND claimed_at < now()-interval '15 minutes'
        FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE atendimento.fila_envio SET status='envio_incerto',
            erro='Worker sem confirmação há mais de 15 minutos. Conferir Gmail antes de qualquer reenvio.', updated_at=now()
            WHERE id=item.id;
        UPDATE public.qualitcontrol_email_atendimento SET status='envio_incerto', updated_at=now()
            WHERE mailbox=item.mailbox AND message_id=item.message_id
              AND owner_execution='humano:'||item.id::text AND status='envio_iniciado';
        UPDATE atendimento.casos SET status='envio_incerto', updated_at=now()
            WHERE mailbox=item.mailbox AND message_id=item.message_id;
        INSERT INTO atendimento.auditoria(mailbox,message_id,ator,acao)
            VALUES(item.mailbox,item.message_id,'n8n','envio_expirado_sem_confirmacao');
        total := total+1;
    END LOOP;
    RETURN total;
END $$;

CREATE OR REPLACE FUNCTION atendimento.reservar_envio(p_execution text,p_mailbox text)
RETURNS TABLE(job_id uuid, mailbox_email text, gmail_message_id text, reply_body text)
LANGUAGE plpgsql AS $$
DECLARE item atendimento.fila_envio%ROWTYPE; original public.qualitcontrol_email_atendimento%ROWTYPE;
BEGIN
    PERFORM atendimento.expirar_envios();
    SELECT * INTO item FROM atendimento.fila_envio
        WHERE status='pendente' AND mailbox=p_mailbox ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT * INTO original FROM public.qualitcontrol_email_atendimento
        WHERE mailbox=item.mailbox AND message_id=item.message_id FOR UPDATE;
    IF original.status NOT IN ('revisao_humana','nao_responder') THEN
        UPDATE atendimento.fila_envio SET status='bloqueado', erro='Estado da mensagem mudou; envio bloqueado.', updated_at=now()
            WHERE id=item.id;
        RETURN;
    END IF;
    UPDATE public.qualitcontrol_email_atendimento SET status='envio_iniciado',
        owner_execution='humano:'||item.id::text, updated_at=now()
        WHERE mailbox=item.mailbox AND message_id=item.message_id;
    UPDATE atendimento.fila_envio SET status='enviando', owner_execution=p_execution,
        claimed_at=now(), updated_at=now() WHERE id=item.id;
    INSERT INTO atendimento.auditoria(mailbox,message_id,ator,acao)
        VALUES(item.mailbox,item.message_id,'n8n','envio_humano_iniciado');
    RETURN QUERY SELECT item.id,item.mailbox,item.message_id,item.corpo_texto;
END $$;

CREATE OR REPLACE FUNCTION atendimento.finalizar_envio(p_id uuid,p_confirmado boolean,p_sent_id text,p_erro text)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE item atendimento.fila_envio%ROWTYPE; estado text;
BEGIN
    SELECT * INTO item FROM atendimento.fila_envio WHERE id=p_id FOR UPDATE;
    IF NOT FOUND OR item.status <> 'enviando' THEN RETURN false; END IF;
    estado := CASE WHEN p_confirmado AND length(coalesce(p_sent_id,''))>0 THEN 'enviado' ELSE 'envio_incerto' END;
    UPDATE atendimento.fila_envio SET status=estado, sent_message_id=nullif(p_sent_id,''),
        erro=nullif(p_erro,''),updated_at=now() WHERE id=p_id;
    UPDATE public.qualitcontrol_email_atendimento SET status=estado,
        sent_message_id=nullif(p_sent_id,''),
        resultado=coalesce(resultado,'{}'::jsonb)||jsonb_build_object(
            'resposta_humana',item.corpo_texto,'respondido_por',item.aprovado_por,
            'status_envio',estado,'id_resposta',p_sent_id), updated_at=now()
        WHERE mailbox=item.mailbox AND message_id=item.message_id
          AND owner_execution='humano:'||item.id::text AND status='envio_iniciado';
    IF NOT FOUND THEN RAISE EXCEPTION 'Estado original incompatível com a confirmação do envio'; END IF;
    UPDATE atendimento.casos SET status=estado,updated_at=now()
        WHERE mailbox=item.mailbox AND message_id=item.message_id;
    INSERT INTO atendimento.auditoria(mailbox,message_id,ator,acao,detalhe)
        VALUES(item.mailbox,item.message_id,'n8n',estado,jsonb_build_object('job_id',p_id,'sent_message_id',p_sent_id));
    RETURN true;
END $$;

GRANT USAGE ON SCHEMA public,atendimento TO automacao_app,painel_app;
GRANT SELECT,INSERT,UPDATE ON public.qualitcontrol_email_atendimento TO automacao_app;
GRANT SELECT ON public.qualitcontrol_email_atendimento TO painel_app;
GRANT SELECT,INSERT,UPDATE ON atendimento.casos TO automacao_app,painel_app;
GRANT SELECT,INSERT,UPDATE ON atendimento.fila_envio TO automacao_app;
GRANT SELECT,INSERT ON atendimento.fila_envio TO painel_app;
GRANT SELECT,INSERT ON atendimento.auditoria TO automacao_app,painel_app;
GRANT USAGE,SELECT ON SEQUENCE atendimento.auditoria_id_seq TO automacao_app,painel_app;
REVOKE ALL ON FUNCTION atendimento.expirar_envios() FROM PUBLIC;
REVOKE ALL ON FUNCTION atendimento.reservar_envio(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION atendimento.finalizar_envio(uuid,boolean,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atendimento.expirar_envios(),atendimento.reservar_envio(text,text),
    atendimento.finalizar_envio(uuid,boolean,text,text) TO automacao_app;
COMMIT;
