"""Gera cópias para testes dos dois exports. Não conecta ao n8n nem altera os originais."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
PROCESS_ID='QCEmailProcesso02'
RECEIVER_ID='QCEmailReceptor01'
SENDER_ID='QCEmailHumano003'


def node(name,node_type,parameters,position,**kwargs):
    return dict(id=str(uuid4()),name=name,type=node_type,typeVersion=2.6 if node_type=='n8n-nodes-base.postgres' else 2,
                parameters=parameters,position=position,**kwargs)


def postgres(name,query,replacement,position):
    return node(name,'n8n-nodes-base.postgres',dict(operation='executeQuery',query=query,
        options=dict(queryReplacement=replacement,queryBatching='independently')),position)


def link(target):
    return dict(node=target,type='main',index=0)


def bind_credentials(workflow):
    for item in workflow['nodes']:
        item.pop('credentials',None)
        kind=item['type']
        if kind in ('n8n-nodes-base.gmail','n8n-nodes-base.gmailTrigger'):
            item['credentials']={'gmailOAuth2':dict(id='EmailTesteGmail01',name='Gmail - Conta de Testes')}
        elif kind=='n8n-nodes-base.postgres':
            item['credentials']={'postgres':dict(id='EmailTestePostgres01',name='PostgreSQL - Atendimento Teste')}
        elif kind=='@n8n/n8n-nodes-langchain.lmChatGoogleGemini':
            item['credentials']={'googlePalmApi':dict(id='EmailTesteGemini01',name='Gemini - Testes')}
    workflow['active']=False
    workflow.pop('pinData',None)


def prepare(receiver,processor):
    receiver=deepcopy(receiver)
    processor=deepcopy(processor)
    receiver.update(id=RECEIVER_ID,name='TESTE | 01 - Receptor Gmail')
    processor.update(id=PROCESS_ID,name='TESTE | 02 - Processamento e treinamento integral')
    lookup={n['name']:n for n in processor['nodes']}
    training=deepcopy(lookup['Analisar e redigir']['parameters'])
    for item in receiver['nodes']:
        if item['type']=='n8n-nodes-base.executeWorkflow':
            item['parameters']['workflowId']['value']=PROCESS_ID
        if item['type']=='n8n-nodes-base.stickyNote':
            item['parameters']['content']='Ambiente separado de testes. Configurar Gmail e AUTOMATION_EMAIL antes de publicar. O fluxo 02 já está vinculado por ID fixo.'
    config=lookup['Configuracao']['parameters']['assignments']['assignments']
    config[0]['value']='={{ $env.AUTOMATION_EMAIL }}'
    config.append(dict(id=str(uuid4()),name='envio_automatico_habilitado',type='boolean',
                       value="={{ $env.ENABLE_EMAIL_SEND === 'true' && $env.ENABLE_AUTO_REPLY === 'true' }}"))
    lookup['Google Gemini Chat Model']['parameters']['modelName']='={{ $env.GEMINI_MODEL }}'
    code=lookup['Dados necessarios']['parameters']['jsCode']
    code=code.replace('return {json:{email_automacao:account,',
        "return {json:{envio_automatico_habilitado:$('Validar configuracao').item.json.envio_automatico_habilitado === true,email_automacao:account,")
    lookup['Dados necessarios']['parameters']['jsCode']=code
    reserve=lookup['Reservar mensagem uma vez']['parameters']
    reserve['query']=reserve['query'].replace('(mailbox, message_id, owner_execution, status)',
        '(mailbox, message_id, owner_execution, status, resultado)').replace("VALUES ($2, $1, $3, 'reservado')", "VALUES ($2, $1, $3, 'reservado', $4::jsonb)")
    reserve['options']['queryReplacement']='={{ [$json.id_email, $json.email_automacao, $execution.id, JSON.stringify($json)] }}'
    code=lookup['Validar decisao']['parameters']['jsCode']
    head,tail=code.rsplit('return {json:',1)
    code=head+'const result = {json:'+tail+'''
if (result.json.decisao === 'responder' && source.envio_automatico_habilitado !== true) {
  result.json.rascunho_html = result.json.resposta_html;
  result.json.resposta_html = '';
  result.json.decisao = 'revisao_humana';
  result.json.motivo = 'Modo de teste: resposta automática encaminhada para aprovação humana. ' + result.json.motivo;
}
return result;
'''
    lookup['Validar decisao']['parameters']['jsCode']=code
    query='''INSERT INTO public.qualitcontrol_email_atendimento(mailbox,message_id,owner_execution,status,resultado)
SELECT $2,$1,$3,$4,$5::jsonb WHERE nullif($1,'') IS NOT NULL
ON CONFLICT(mailbox,message_id) DO NOTHING RETURNING message_id;'''
    processor['nodes'].append(postgres('Registrar mensagem nao elegivel',query,
        '={{ [$json.id_email,$json.email_automacao,$execution.id,$json.decisao,JSON.stringify($json)] }}',[1200,700]))
    processor['connections']['Email elegivel?']['main'][1]=[link('Registrar mensagem nao elegivel')]
    # Inicialização passa a ser responsabilidade do serviço db-migrate.
    removed={'Preparar banco - executar uma vez','Criar tabela de controle','Nao elegivel - manter leitura'}
    processor['nodes']=[n for n in processor['nodes'] if n['name'] not in removed]
    for name in removed:
        processor['connections'].pop(name,None)
    lookup['Instrucoes']['parameters']['content']='''Cópia para ambiente de testes. Treinamento integral preservado no nó Analisar e redigir.
Credenciais centralizadas: Gmail - Conta de Testes; Gemini - Testes; PostgreSQL - Atendimento Teste.
O Docker Compose cria o banco. Não é preciso executar CREATE TABLE manualmente.
ENABLE_EMAIL_SEND=false impede envios; ENABLE_AUTO_REPLY=false encaminha respostas da IA para revisão.
Mensagens não elegíveis também são registradas para triagem. Os originais permanecem intactos.'''
    assert lookup['Analisar e redigir']['parameters']==training
    return receiver,processor


def sender(processor):
    source={n['name']:n for n in processor['nodes']}
    enabled=deepcopy(source['Responder?'])
    enabled.update(id=str(uuid4()),name='Envio habilitado?',position=[250,0])
    enabled['parameters']['conditions']['conditions'][0]['leftValue']="={{ $env.ENABLE_EMAIL_SEND === 'true' }}"
    confirmed=deepcopy(source['Envio confirmado?'])
    confirmed.update(id=str(uuid4()),name='Gmail confirmou envio?',position=[1100,0])
    saved=deepcopy(enabled)
    saved.update(id=str(uuid4()),name='Confirmacao persistida?',position=[1550,-100])
    saved['parameters']['conditions']['conditions'][0]['leftValue']='={{ $json.salvo === true }}'
    reply=deepcopy(source['Responder no Gmail'])
    reply.update(id=str(uuid4()),name='Enviar resposta humana no Gmail',position=[850,0])
    reply['parameters'].update(messageId='={{ $json.gmail_message_id }}',emailType='text',message='={{ $json.reply_body }}')
    mark=deepcopy(source['Marcar original como lido'])
    mark.update(id=str(uuid4()),name='Marcar original humano como lido',position=[1800,-100])
    mark['parameters']['messageId']="={{ $('Reservar envio humano').item.json.gmail_message_id }}"
    mark['onError']='continueRegularOutput'
    nodes=[
        node('A cada minuto','n8n-nodes-base.scheduleTrigger',{'rule':{'interval':[{'field':'minutes','minutesInterval':1}]}},[0,0]),
        node('Testar fila manualmente','n8n-nodes-base.manualTrigger',{},[0,200]),enabled,
        postgres('Reservar envio humano','SELECT * FROM atendimento.reservar_envio($1,$2);','={{ [$execution.id,$env.AUTOMATION_EMAIL] }}',[550,0]),
        reply,confirmed,
        postgres('Registrar sucesso humano','SELECT atendimento.finalizar_envio($1::uuid,true,$2,\'\') AS salvo;',
            "={{ [$('Reservar envio humano').item.json.job_id,$json.id] }}",[1350,-100]),saved,mark,
        postgres('Registrar incerteza humana','SELECT atendimento.finalizar_envio($1::uuid,false,\'\',$2) AS salvo;',
            "={{ [$('Reservar envio humano').item.json.job_id,JSON.stringify($json).slice(0,2000)] }}",[1350,200]),
    ]
    nodes[0]['typeVersion']=1.2
    nodes[1]['typeVersion']=1
    return dict(id=SENDER_ID,name='TESTE | 03 - Envio de respostas humanas',active=False,nodes=nodes,
        settings=dict(executionOrder='v1',timezone='America/Sao_Paulo'),connections={
            'A cada minuto':{'main':[[link('Envio habilitado?')]]},
            'Testar fila manualmente':{'main':[[link('Envio habilitado?')]]},
            'Envio habilitado?':{'main':[[link('Reservar envio humano')],[]]},
            'Reservar envio humano':{'main':[[link('Enviar resposta humana no Gmail')]]},
            'Enviar resposta humana no Gmail':{'main':[[link('Gmail confirmou envio?')],[link('Registrar incerteza humana')]]},
            'Gmail confirmou envio?':{'main':[[link('Registrar sucesso humano')],[link('Registrar incerteza humana')]]},
            'Registrar sucesso humano':{'main':[[link('Confirmacao persistida?')]]},
            'Confirmacao persistida?':{'main':[[link('Marcar original humano como lido')],[]]},
        })


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('receptor',type=Path,nargs='?',default=ROOT/'docker'/'n8n'/'n8n_01_receptor_gmail.json')
    parser.add_argument('processamento',type=Path,nargs='?',default=ROOT/'docker'/'n8n'/'n8n_02_processamento_treinamento_completo.json')
    args=parser.parse_args()
    original=[json.loads(p.read_text(encoding='utf-8-sig')) for p in (args.receptor,args.processamento)]
    receiver,processor=prepare(*original)
    workflows=[receiver,processor,sender(processor)]
    (ROOT/'workflows').mkdir(exist_ok=True)
    for name,workflow in zip(('01-receptor.json','02-processamento.json','03-envio-humano.json'),workflows):
        bind_credentials(workflow)
        (ROOT/'workflows'/name).write_text(json.dumps(workflow,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    original_training=next(n['parameters'] for n in original[1]['nodes'] if n['name']=='Analisar e redigir')
    training_sha256=hashlib.sha256(json.dumps(original_training,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    manifest=dict(source_directory='docker/n8n' if args.receptor.parent.resolve()==(ROOT/'docker'/'n8n').resolve() and args.processamento.parent.resolve()==(ROOT/'docker'/'n8n').resolve() else 'argumentos personalizados',
        originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.receptor,args.processamento)},
        training_preserved=True,training_sha256=training_sha256,workflow_ids=[w['id'] for w in workflows])
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    from build_knowledge import build
    build(ROOT)
    print('Três workflows de testes gerados em workflows/; treinamento preservado; fontes originais somente lidas.')


if __name__=='__main__':
    main()
