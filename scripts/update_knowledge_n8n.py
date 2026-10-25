"""Atualiza somente a base do fluxo 02 de testes, com backup e sem ativar fluxos."""
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from build_knowledge import ROOT,NODE_NAME,augment,compile_base

PROCESS_ID='QCEmailProcesso02'
RECEIVER_ID='QCEmailReceptor01'


def docker(*args):
    result=subprocess.run(['docker','compose',*map(str,args)],cwd=ROOT,
                          capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:
        raise RuntimeError('Falha no comando Docker. Consulte os logs do ambiente; nenhum segredo foi exibido.')
    return result


def export_workflow(workflow_id,directory,label):
    remote=f'/tmp/{directory.name}-{label}.json'
    local=directory/f'{label}.json'
    docker('exec','-T','n8n','n8n','export:workflow',f'--id={workflow_id}',f'--output={remote}')
    docker('cp',f'n8n:{remote}',local)
    payload=json.loads(local.read_text(encoding='utf-8-sig'))
    items=payload if isinstance(payload,list) else [payload]
    if len(items)!=1 or items[0].get('id')!=workflow_id:
        raise RuntimeError('O export não corresponde ao fluxo esperado; atualização interrompida.')
    return items[0],remote


def main():
    corpus,metadata=compile_base(ROOT)
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    directory=ROOT/'work'/'n8n-backups'/uuid4().hex
    directory.mkdir(parents=True)
    # Não altera variáveis nem desativa fluxos ativos para forçar a atualização.
    docker('exec','-T','n8n','node','-e',
           "process.exit(process.env.ENABLE_EMAIL_SEND==='false'?0:1)")
    receiver,_=export_workflow(RECEIVER_ID,directory,'receptor-before')
    current,original_remote=export_workflow(PROCESS_ID,directory,'processamento-before')
    if any(w.get('active') or w.get('activeVersionId') for w in (receiver,current)):
        raise RuntimeError('Receptor ou processamento está ativo/publicado. Atualização interrompida, sem alterar os fluxos.')
    updated=augment(current,corpus,metadata,manifest['training_sha256'])
    updated['active']=False
    updated['versionId']=str(uuid4())
    candidate=directory/'processamento-updated.json'
    candidate.write_text(json.dumps([updated],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    remote_candidate=f'/tmp/{directory.name}-updated.json'
    docker('cp',candidate,f'n8n:{remote_candidate}')
    try:
        docker('exec','-T','n8n','n8n','import:workflow',f'--input={remote_candidate}')
        verified,_=export_workflow(PROCESS_ID,directory,'processamento-after')
        base=next(n for n in verified['nodes'] if n['name']==NODE_NAME)
        fields={f['name']:f['value'] for f in base['parameters']['assignments']['assignments']}
        if verified.get('active') or fields.get('base_documental_hash')!=metadata['context_sha256']:
            raise RuntimeError('A verificação da versão documental falhou.')
        old_credentials={n['name']:n['credentials'] for n in current['nodes'] if n.get('credentials')}
        new_credentials={n['name']:n['credentials'] for n in verified['nodes'] if n.get('credentials')}
        if old_credentials!=new_credentials:
            raise RuntimeError('A verificação das referências de credenciais falhou.')
    except Exception:
        docker('exec','-T','n8n','n8n','import:workflow',f'--input={original_remote}')
        raise RuntimeError('Atualização não confirmada. A versão anterior foi restaurada a partir do backup.') from None
    print(f'Fluxo 02 atualizado com {len(metadata["documents"])} referências, sem ativação.')
    print('Referências de credenciais preservadas.')
    print(f'Backup local: {directory}')


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,ValueError,OSError,KeyError,StopIteration) as exc:
        raise SystemExit(str(exc)) from None
