"""Integração local sem Gmail/IA: somente dados fictícios criados e removidos pelo teste.

Executar: python -m unittest discover -s tests -v
Requer requirements.txt e o PostgreSQL deste compose em execução.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import psycopg
from psycopg.types.json import Jsonb
import service


def configure():
    env={}
    for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            key,value=line.split('=',1)
            env[key]=value
    os.environ.update(PGHOST='127.0.0.1',PGPORT=env.get('POSTGRES_PORT','55433'),PGDATABASE='atendimento',
                      PGUSER='painel_app',PGPASSWORD=env['APP_DB_PASSWORD'],
                      APP_USERNAME=env['APP_USERNAME'],AUTH_MODE='local')
    return env


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=configure()

    def admin(self):
        return psycopg.connect(host='127.0.0.1',port=self.env.get('POSTGRES_PORT','55433'),dbname='atendimento',
                               user='postgres',password=self.env['POSTGRES_PASSWORD'])

    def automation(self):
        return psycopg.connect(host='127.0.0.1',port=self.env.get('POSTGRES_PORT','55433'),dbname='atendimento',
                               user='automacao_app',password=self.env['AUTOMATION_DB_PASSWORD'],row_factory=psycopg.rows.dict_row)

    def setUp(self):
        self.mailbox=f'test-{uuid4().hex}@example.invalid'
        self.message='TEST-INVALID-GMAIL-ID'
        with self.admin() as conn:
            conn.execute('''INSERT INTO public.qualitcontrol_email_atendimento(mailbox,message_id,owner_execution,status,resultado)
                VALUES(%s,%s,'unit-test','revisao_humana',%s)''',
                (self.mailbox,self.message,Jsonb(dict(assunto_email='Caso de integração',corpo_email='Olá',motivo='Teste',rascunho_html='<p>Sugestão</p>'))))

    def tearDown(self):
        with self.admin() as conn:
            for table in ('atendimento.auditoria','atendimento.fila_envio','atendimento.casos','public.qualitcontrol_email_atendimento'):
                # Identificadores constantes definidos acima; valores continuam parametrizados.
                conn.execute(f'DELETE FROM {table} WHERE mailbox=%s',(self.mailbox,))

    def queue(self):
        service.claim(self.mailbox,self.message,'operador','sessao-a')
        return service.enqueue(self.mailbox,self.message,'operador','sessao-a','Resposta humana de teste')

    def test_concurrent_claim_has_single_winner(self):
        def attempt(token):
            try:
                service.claim(self.mailbox,self.message,'operador',token)
                return True
            except service.Conflict:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt,('sessao-a','sessao-b'))),1)

    def test_draft_persists_and_other_session_cannot_save(self):
        service.claim(self.mailbox,self.message,'operador','sessao-a')
        service.save_draft(self.mailbox,self.message,'operador','sessao-a','Texto persistente')
        self.assertEqual(service.detail(self.mailbox,self.message)['rascunho'],'Texto persistente')
        with self.assertRaises(service.Conflict):
            service.save_draft(self.mailbox,self.message,'outro','sessao-b','Sobrescrever')

    def test_approval_is_unique_and_completion_updates_original(self):
        job=self.queue()
        with self.assertRaises(service.Conflict):
            service.enqueue(self.mailbox,self.message,'operador','sessao-a','Duplicada')
        with self.automation() as conn:
            item=conn.execute('SELECT * FROM atendimento.reservar_envio(%s,%s)',('test-worker',self.mailbox)).fetchone()
            self.assertEqual(str(item['job_id']),job)
            self.assertEqual(conn.execute('SELECT * FROM atendimento.reservar_envio(%s,%s)',('second-worker',self.mailbox)).fetchall(),[])
            self.assertTrue(conn.execute('SELECT atendimento.finalizar_envio(%s,true,%s,%s)',(job,'TEST-SENT-ID','')).fetchone()['finalizar_envio'])
        self.assertEqual(service.detail(self.mailbox,self.message)['status'],'enviado')

    def test_stale_send_is_uncertain_and_never_requeued(self):
        job=self.queue()
        with self.automation() as conn:
            conn.execute('SELECT * FROM atendimento.reservar_envio(%s,%s)',('worker-lost',self.mailbox)).fetchone()
        with self.admin() as conn:
            conn.execute("UPDATE atendimento.fila_envio SET claimed_at=now()-interval '20 minutes' WHERE id=%s",(job,))
        with self.automation() as conn:
            self.assertEqual(conn.execute('SELECT atendimento.expirar_envios()').fetchone()['expirar_envios'],1)
            self.assertEqual(conn.execute('SELECT * FROM atendimento.reservar_envio(%s,%s)',('retry',self.mailbox)).fetchall(),[])
        self.assertEqual(service.detail(self.mailbox,self.message)['status'],'envio_incerto')
        with self.assertRaises(service.Conflict):
            service.claim(self.mailbox,self.message,'operador','sessao-c')

    def test_panel_cannot_change_automation_state(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with service.connect() as conn:
                conn.execute("UPDATE public.qualitcontrol_email_atendimento SET status='enviado' WHERE mailbox=%s",(self.mailbox,))

    def test_reply_ui_in_local_mode(self):
        from streamlit.testing.v1 import AppTest
        # Uma segunda mensagem detecta perda de seleção quando o status muda.
        with self.admin() as conn:
            conn.execute('''INSERT INTO public.qualitcontrol_email_atendimento(mailbox,message_id,owner_execution,status,resultado,created_at)
                VALUES(%s,'TEST-SECOND-MESSAGE','unit-test','revisao_humana',%s,now()-interval '1 day')''',
                (self.mailbox,Jsonb(dict(assunto_email='Outra mensagem',corpo_email='Outro conteúdo',motivo='Teste de seleção'))))
        at=AppTest.from_file(str(ROOT/'app'/'main.py'),default_timeout=15).run()
        self.assertEqual(len(at.exception),0)
        at.session_state['session_token']='ui-test'
        at.run()
        at.selectbox[0].set_value((self.mailbox,self.message)).run()
        self.assertEqual(at.selectbox[0].value,(self.mailbox,self.message))
        next(b for b in at.button if b.label=='Assumir atendimento').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.selectbox[0].value,(self.mailbox,self.message))
        next(t for t in at.text_area if t.label=='Resposta ao remetente').set_value('Resposta escrita pela tela')
        next(b for b in at.button if b.label=='Salvar rascunho').click().run()
        self.assertEqual(service.detail(self.mailbox,self.message)['rascunho'],'Resposta escrita pela tela')
        next(c for c in at.checkbox if 'Conferi a conversa' in c.label).check()
        next(b for b in at.button if b.label=='Aprovar e colocar na fila').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(service.detail(self.mailbox,self.message)['status_fila'],'pendente')
        with self.automation() as conn:
            job=conn.execute('SELECT * FROM atendimento.reservar_envio(%s,%s)',('ui-test-worker',self.mailbox)).fetchone()
            conn.execute('SELECT atendimento.finalizar_envio(%s,true,%s,%s)',(job['job_id'],'TEST-UI-SENT',''))
        at.run()
        self.assertEqual(len(at.exception),0)
        self.assertNotEqual(at.selectbox[0].value,(self.mailbox,self.message))


class Workflows(unittest.TestCase):
    def test_graphs_and_training_guard(self):
        manifest=json.loads((ROOT/'manifest.json').read_text())
        self.assertTrue(manifest['training_preserved'])
        for path in (ROOT/'workflows').glob('*.json'):
            workflow=json.loads(path.read_text(encoding='utf-8'))
            self.assertFalse(workflow['active'])
            if workflow['id']=='QCEmailProcesso02':
                training=next(n['parameters'] for n in workflow['nodes'] if n['name']=='Analisar e redigir')
                sys.path.insert(0,str(ROOT/'scripts'))
                from build_knowledge import original_training
                training=original_training(training)
                self.assertEqual(hashlib.sha256(json.dumps(training,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),manifest['training_sha256'])
            names={n['name'] for n in workflow['nodes']}
            for source,outputs in workflow['connections'].items():
                self.assertIn(source,names)
                for edges in outputs.values():
                    for edge in edges:
                        for target in edge:
                            self.assertIn(target['node'],names)


if __name__=='__main__':
    unittest.main()
