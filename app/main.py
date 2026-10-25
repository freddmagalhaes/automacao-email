import os
import re
from html import unescape
from uuid import uuid4

import psycopg
import streamlit as st

import service

st.set_page_config(page_title='Atendimento de e-mails',page_icon=':material/mail:',layout='wide')


def plain(html):
    html=re.sub(r'<(script|style)\b[^>]*>[\s\S]*?</\1>','',html or '',flags=re.I)
    html=re.sub(r'<\s*(?:br\s*/?|/p|/li)\s*>','\n',html,flags=re.I)
    return unescape(re.sub(r'<[^>]+>','',html)).strip()


auth_mode=os.environ.get('AUTH_MODE','local')
if auth_mode=='oidc':
    if not st.user.is_logged_in:
        st.title('Central de atendimento')
        if st.button('Entrar com sua conta'):
            st.login()
        st.stop()
    allowed={email.strip().lower() for email in os.environ.get('ALLOWED_EMAILS','').split(',') if email.strip()}
    email=str(st.user.get('email','')).lower()
    if email not in allowed:
        st.error('Sua conta não possui acesso a este painel.')
        if st.button('Sair'):
            st.logout()
        st.stop()
    st.session_state.actor=email
elif auth_mode=='local':
    st.session_state.actor=os.environ.get('APP_USERNAME','operador_teste')
    st.caption('Teste local: identidade simulada. Esta configuração não autentica usuários.')
else:
    st.error('AUTH_MODE inválido. Use local para testes ou oidc para autenticação.')
    st.stop()
st.session_state.setdefault('session_token',str(uuid4()))

with st.sidebar:
    st.write(f"Atendente: {st.session_state.actor}")
    show_ignored=st.checkbox('Incluir descartados pela automação')
    if st.button('Atualizar fila'):
        st.rerun()
    if st.button('Sair'):
        st.session_state.clear()
        if auth_mode=='oidc':
            st.logout()
        st.rerun()
    st.caption('Reserva de 20 minutos. Salvar rascunho renova a reserva. A fila mostra até 200 mensagens.')

st.title('E-mails que precisam de atenção')
if os.environ.get('ENABLE_EMAIL_SEND','false').lower()!='true':
    st.info('Modo de teste: o n8n não enviará e-mails. Respostas aprovadas ficam na fila até a habilitação do envio.')
if flash:=st.session_state.pop('flash',None):
    st.success(flash)

try:
    items=service.list_messages(show_ignored)
    if not items:
        st.info('Nenhuma pendência. Use os dados demonstrativos do README ou configure e execute a automação.')
        st.stop()
    labels={}
    for row in items:
        payload=row['resultado'] or {}
        labels[(row['mailbox'],row['message_id'])]=f"{row['status_fila'] or row['status_humano'] or row['status']} · {payload.get('assunto_email') or row['message_id']} · {payload.get('remetente','')}"
    if st.session_state.get('selected_message') not in labels:
        st.session_state.selected_message=next(iter(labels))
    key=st.selectbox('Selecione a mensagem',list(labels),format_func=labels.get,key='selected_message')
    mailbox,message_id=key
    item=service.detail(mailbox,message_id)
    payload=item['resultado'] or {}
    left,right=st.columns([1,1],gap='large')
    with left:
        st.subheader(payload.get('assunto_email') or 'Mensagem sem assunto')
        st.write('**Remetente:**',payload.get('remetente','Indisponível'))
        st.write('**Conta:**',mailbox)
        st.write('**Status:**',item['status_fila'] or item['status_humano'] or item['status'])
        st.write('**Motivo:**',payload.get('motivo','Sem motivo registrado'))
        st.text_area('Mensagem recebida',value=payload.get('corpo_email','Corpo não disponível neste registro.'),height=300,disabled=True,key=f'original:{mailbox}:{message_id}')
        if payload.get('tem_anexos'):
            st.warning('A mensagem contém anexos. Consulte-os no Gmail antes de responder; este piloto não os baixa.')
        if item.get('erro'):
            st.warning(item['erro'])
        if re.fullmatch(r'[0-9a-fA-F]+',message_id):
            st.link_button('Conferir no Gmail',f'https://mail.google.com/mail/u/0/#all/{message_id}')
    with right:
        st.subheader('Preparar resposta')
        if item['status']=='envio_incerto' or item['status_fila']=='envio_incerto':
            st.warning('Envio incerto: confira a conversa no Gmail. Um novo envio está bloqueado neste piloto.')
        elif item['status_fila'] or item['status'] not in ('revisao_humana','nao_responder'):
            st.info('Esta mensagem está em processamento ou já possui uma solicitação de envio. Atualize para acompanhar.')
        else:
            owns=item['session_token']==st.session_state.session_token and item['reserva_valida']
            if not owns:
                if item['responsavel'] and item['reserva_valida']:
                    st.info(f"Em atendimento por {item['responsavel']} até {item['reservado_ate']}.")
                if st.button('Assumir atendimento'):
                    service.claim(mailbox,message_id,st.session_state.actor,st.session_state.session_token)
                    st.rerun()
            else:
                draft_key=f'draft:{mailbox}:{message_id}'
                with st.form(f'reply:{mailbox}:{message_id}',enter_to_submit=False):
                    text=st.text_area('Resposta ao remetente',value=item['rascunho'] or plain(payload.get('rascunho_html','')),height=300,max_chars=20000,key=draft_key)
                    confirmed=st.checkbox('Conferi a conversa no Gmail e revisei o texto e o destinatário.')
                    save=st.form_submit_button('Salvar rascunho')
                    send=st.form_submit_button('Aprovar e colocar na fila',type='primary')
                if save:
                    service.save_draft(mailbox,message_id,st.session_state.actor,st.session_state.session_token,text)
                    st.session_state.flash='Rascunho salvo no PostgreSQL.'
                    st.rerun()
                if send:
                    if not confirmed:
                        st.error('Confirme a revisão antes de aprovar a resposta.')
                    else:
                        job=service.enqueue(mailbox,message_id,st.session_state.actor,st.session_state.session_token,text)
                        st.session_state.flash=f'Resposta aprovada e registrada na fila. Protocolo: {job}. Atualize para acompanhar o envio.'
                        st.rerun()
                if st.button('Liberar atendimento'):
                    service.release(mailbox,message_id,st.session_state.actor,st.session_state.session_token)
                    st.rerun()
        with st.expander('Histórico de ações',on_change='rerun') as events:
            if events.open:
                st.dataframe(service.history(mailbox,message_id),hide_index=True,width='stretch',alt='Ações realizadas nesta mensagem')
except service.Conflict as exc:
    st.warning(str(exc))
except psycopg.Error:
    st.error('Não foi possível concluir a operação no banco. Atualize a fila; se persistir, consulte os logs do serviço.')
