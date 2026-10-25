"""Operações de atendimento persistentes, independentes da interface Streamlit."""

from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


class Conflict(Exception):
    pass


def connect():
    return psycopg.connect(row_factory=dict_row, connect_timeout=5)


def list_messages(show_ignored=False):
    with connect() as conn:
        return conn.execute(
            """
            SELECT e.mailbox,e.message_id,e.status,e.created_at,e.updated_at,e.resultado,
                   c.status AS status_humano,c.responsavel,c.reservado_ate,
                   o.status AS status_fila,o.erro
            FROM public.qualitcontrol_email_atendimento e
            LEFT JOIN atendimento.casos c USING(mailbox,message_id)
            LEFT JOIN atendimento.fila_envio o USING(mailbox,message_id)
            WHERE e.status <> 'enviado' AND (%s OR e.status <> 'nao_responder')
            ORDER BY e.created_at LIMIT 200
        """,
            (show_ignored,),
        ).fetchall()


def detail(mailbox, message_id):
    with connect() as conn:
        item = conn.execute(
            """
            SELECT e.*,c.status AS status_humano,c.rascunho,c.responsavel,c.session_token,
                   c.reservado_ate,(c.reservado_ate>now()) AS reserva_valida,
                   o.status AS status_fila,o.erro,o.sent_message_id AS id_envio_humano
            FROM public.qualitcontrol_email_atendimento e
            LEFT JOIN atendimento.casos c USING(mailbox,message_id)
            LEFT JOIN atendimento.fila_envio o USING(mailbox,message_id)
            WHERE e.mailbox=%s AND e.message_id=%s
        """,
            (mailbox, message_id),
        ).fetchone()
        return item


def audit(conn, mailbox, message_id, actor, action):
    conn.execute(
        "INSERT INTO atendimento.auditoria(mailbox,message_id,ator,acao) VALUES(%s,%s,%s,%s)",
        (mailbox, message_id, actor, action),
    )


def claim(mailbox, message_id, actor, token):
    with connect() as conn:
        # FOR UPDATE exige permissão UPDATE: o painel usa um lock consultivo de transação
        # para serializar suas reservas sem receber UPDATE na tabela da automação.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (mailbox + "\x1f" + message_id,))
        original = conn.execute(
            "SELECT status FROM public.qualitcontrol_email_atendimento WHERE mailbox=%s AND message_id=%s",
            (mailbox, message_id),
        ).fetchone()
        if not original or original["status"] not in ("revisao_humana", "nao_responder"):
            raise Conflict("Mensagem indisponível para nova resposta. Atualize a fila.")
        pending = conn.execute(
            "SELECT 1 FROM atendimento.fila_envio WHERE mailbox=%s AND message_id=%s", (mailbox, message_id)
        ).fetchone()
        if pending:
            raise Conflict("Já existe uma solicitação de envio para esta mensagem.")
        row = conn.execute(
            """
            INSERT INTO atendimento.casos(mailbox,message_id,status,responsavel,session_token,reservado_ate)
            VALUES(%s,%s,'em_atendimento',%s,%s,now()+interval '20 minutes')
            ON CONFLICT(mailbox,message_id) DO UPDATE SET status='em_atendimento',responsavel=excluded.responsavel,
                session_token=excluded.session_token,reservado_ate=excluded.reservado_ate,updated_at=now()
            WHERE atendimento.casos.reservado_ate IS NULL OR atendimento.casos.reservado_ate<now()
                OR atendimento.casos.session_token=excluded.session_token
            RETURNING message_id
        """,
            (mailbox, message_id, actor, token),
        ).fetchone()
        if not row:
            raise Conflict("Outra sessão está atendendo esta mensagem. Aguarde a liberação da reserva.")
        audit(conn, mailbox, message_id, actor, "assumir_atendimento")


def save_draft(mailbox, message_id, actor, token, text):
    with connect() as conn:
        row = conn.execute(
            """UPDATE atendimento.casos SET rascunho=%s,reservado_ate=now()+interval '20 minutes',updated_at=now()
            WHERE mailbox=%s AND message_id=%s AND session_token=%s AND reservado_ate>now()
                AND status='em_atendimento' RETURNING message_id""",
            (text, mailbox, message_id, token),
        ).fetchone()
        if not row:
            raise Conflict("Reserva expirada. Assuma o atendimento novamente antes de salvar.")
        audit(conn, mailbox, message_id, actor, "salvar_rascunho")


def enqueue(mailbox, message_id, actor, token, text):
    if not text.strip() or len(text) > 20000:
        raise Conflict("A resposta deve conter entre 1 e 20.000 caracteres.")
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (mailbox + "\x1f" + message_id,))
        case = conn.execute(
            "SELECT * FROM atendimento.casos WHERE mailbox=%s AND message_id=%s FOR UPDATE",
            (mailbox, message_id),
        ).fetchone()
        original = conn.execute(
            "SELECT status FROM public.qualitcontrol_email_atendimento WHERE mailbox=%s AND message_id=%s",
            (mailbox, message_id),
        ).fetchone()
        valid = conn.execute(
            "SELECT reservado_ate>now() AS ok FROM atendimento.casos WHERE mailbox=%s AND message_id=%s",
            (mailbox, message_id),
        ).fetchone()
        if (
            not case
            or case["session_token"] != token
            or not valid["ok"]
            or case["status"] != "em_atendimento"
        ):
            raise Conflict("Reserva expirada ou atendimento alterado. Atualize e assuma novamente.")
        if not original or original["status"] not in ("revisao_humana", "nao_responder"):
            raise Conflict("O estado da mensagem mudou. Atualize a fila.")
        job_id = uuid4()
        inserted = conn.execute(
            """INSERT INTO atendimento.fila_envio(id,mailbox,message_id,corpo_texto,aprovado_por)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(mailbox,message_id) DO NOTHING RETURNING id""",
            (job_id, mailbox, message_id, text.strip(), actor),
        ).fetchone()
        if not inserted:
            raise Conflict("Já existe um envio registrado para esta mensagem; nenhum novo envio foi criado.")
        conn.execute(
            """UPDATE atendimento.casos SET status='na_fila',rascunho=%s,updated_at=now()
            WHERE mailbox=%s AND message_id=%s""",
            (text, mailbox, message_id),
        )
        audit(conn, mailbox, message_id, actor, "resposta_aprovada_na_fila")
        return str(job_id)


def release(mailbox, message_id, actor, token):
    with connect() as conn:
        changed = conn.execute(
            """UPDATE atendimento.casos SET reservado_ate=NULL,session_token=NULL,status='aberto',updated_at=now()
            WHERE mailbox=%s AND message_id=%s AND session_token=%s AND status='em_atendimento' RETURNING message_id""",
            (mailbox, message_id, token),
        ).fetchone()
        if changed:
            audit(conn, mailbox, message_id, actor, "liberar_atendimento")


def history(mailbox, message_id):
    with connect() as conn:
        return conn.execute(
            """SELECT ator,acao,created_at FROM atendimento.auditoria
            WHERE mailbox=%s AND message_id=%s ORDER BY created_at DESC LIMIT 30""",
            (mailbox, message_id),
        ).fetchall()
