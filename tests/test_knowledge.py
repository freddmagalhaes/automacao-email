"""Verificações da base documental, sem rede, Docker, credenciais ou chamadas à IA."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_knowledge import BEGIN,END,NODE_NAME,augment,build,cleaned_text,compile_base,original_training


class Knowledge(unittest.TestCase):
    def test_registered_documents_and_verified_video_summaries_are_included(self):
        corpus,metadata=compile_base(ROOT)
        docs=json.loads(corpus)['documents']
        originals=[d for d in docs if d['id'].startswith('D')]
        self.assertEqual(len(originals),5)
        self.assertEqual({d['id'] for d in originals},{'D01','D02','D03','D04','D05'})
        self.assertTrue(all(not d['source'].endswith('.pdf.txt') for d in docs))
        self.assertNotIn('GUIA_CONFIGURACAO.md',corpus)
        self.assertNotIn('instrucoes_fluxo_atual.txt',corpus)
        self.assertNotIn('schema_resposta.json',corpus)
        self.assertNotIn('Image Sources',corpus)
        self.assertNotIn('https://goaudits.com',corpus)
        for doc,stamp in zip(docs,metadata['documents']):
            self.assertEqual(doc['id'],stamp['id'])
            if stamp.get('kind')=='video_summary':
                self.assertEqual(hashlib.sha256(doc['text'].encode()).hexdigest(),stamp['text_sha256'])
            else:
                self.assertEqual(hashlib.sha256((ROOT/'ambiente_gpt'/doc['source']).read_bytes()).hexdigest(),stamp['sha256'])

    def test_original_training_and_sending_controls_are_preserved(self):
        workflow=json.loads((ROOT/'workflows'/'02-processamento.json').read_text(encoding='utf-8'))
        manifest=json.loads((ROOT/'manifest.json').read_text())
        chain=next(n for n in workflow['nodes'] if n['name']=='Analisar e redigir')
        restored=original_training(chain['parameters'])
        self.assertEqual(hashlib.sha256(json.dumps(restored,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),manifest['training_sha256'])
        self.assertEqual(chain['parameters']['text'].count(BEGIN),1)
        self.assertEqual(chain['parameters']['text'].count(END),1)
        self.assertIn('Google Gemini Chat Model',{n['name'] for n in workflow['nodes']})
        self.assertFalse(workflow['active'])
        self.assertEqual(workflow['connections']['Reserva obtida?']['main'][0][0]['node'],NODE_NAME)
        self.assertEqual(workflow['connections'][NODE_NAME]['main'][0][0]['node'],'Analisar e redigir')
        # A base complementa a entrada da IA, sem alterar os caminhos de envio.
        self.assertEqual(workflow['connections']['Responder?']['main'][0][0]['node'],'Autorizar tentativa unica')

    def test_build_is_current_and_augmentation_is_idempotent(self):
        build(ROOT,check=True)
        corpus,metadata=compile_base(ROOT)
        workflow=json.loads((ROOT/'workflows'/'02-processamento.json').read_text(encoding='utf-8'))
        manifest=json.loads((ROOT/'manifest.json').read_text())
        self.assertEqual(augment(workflow,corpus,metadata,manifest['training_sha256']),workflow)
        changed=deepcopy(workflow)
        next(n for n in changed['nodes'] if n['name']=='Analisar e redigir')['parameters']['text']+='Alteração externa'
        with self.assertRaisesRegex(ValueError,'Treinamento mudou'):
            augment(changed,corpus,metadata,manifest['training_sha256'])

    def test_missing_source_empty_source_and_path_escape_fail_closed(self):
        (ROOT/'work').mkdir(exist_ok=True)
        with TemporaryDirectory(dir=ROOT/'work') as temporary:
            root=Path(temporary)
            (root/'ambiente_gpt').mkdir()
            (root/'knowledge').mkdir()
            config={'version':'test','status':'autorizado_para_contexto_gemini','max_context_characters':1000,
                    'documents':[{'id':'D01','file':'missing.txt','title':'Documento'}]}
            sources=root/'knowledge'/'sources.json'
            sources.write_text(json.dumps(config))
            with self.assertRaises(FileNotFoundError):
                compile_base(root)
            (root/'ambiente_gpt'/'missing.txt').write_text(' \n')
            with self.assertRaisesRegex(ValueError,'vazio'):
                compile_base(root)
            config['documents'][0]['file']='../segredo.txt'
            sources.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError,'fora da pasta autorizada'):
                compile_base(root)

    def test_xml_noise_and_image_credits_are_removed_without_inventing_content(self):
        text=cleaned_text('ppt/slides/slide1.xml\n\nRecurso confirmado\n\nImage Sources\nhttps://image.example.invalid\n')
        self.assertEqual(text,'Recurso confirmado')

    def test_only_verified_content_is_used_instead_of_video_thumbnails(self):
        videos=json.loads((ROOT/'knowledge'/'video_sources.json').read_text(encoding='utf-8'))
        corpus,_=compile_base(ROOT)
        docs=json.loads(corpus)['documents']
        by_id={d['id']:d for d in docs}
        self.assertNotIn('/9j/',corpus)
        for item in videos.get('videos',[]):
            if item.get('include_in_context'):
                self.assertEqual(by_id[item['id']]['text'],item['summary'])
                self.assertIn(item['evidence_type'],('descricao_publica','transcricao_publica'))
            else:
                self.assertNotIn(item['id'],by_id)

    def test_all_received_video_links_are_distinct_and_have_evidence(self):
        videos=json.loads((ROOT/'knowledge'/'video_sources.json').read_text(encoding='utf-8'))['videos']
        self.assertEqual(len(videos),21)
        self.assertEqual(len({v['youtube_id'] for v in videos}),21)
        self.assertTrue(all(v.get('include_in_context') is True for v in videos))
        transcripts={v['youtube_id'] for v in videos if v['evidence_type']=='transcricao_publica'}
        self.assertEqual(transcripts,{'DdDr88m2nzI','YhvjvzbZlzE'})
        self.assertTrue(all(len(v['summary'].split())<=180 for v in videos))

    def test_title_without_verified_content_is_rejected(self):
        (ROOT/'work').mkdir(exist_ok=True)
        with TemporaryDirectory(dir=ROOT/'work') as temporary:
            root=Path(temporary)
            (root/'ambiente_gpt').mkdir()
            (root/'knowledge').mkdir()
            (root/'ambiente_gpt'/'doc.txt').write_text('Conteúdo de produto autorizado.',encoding='utf-8')
            config={'version':'test','status':'autorizado_para_contexto_gemini','max_context_characters':10000,
                    'documents':[{'id':'D01','file':'doc.txt','title':'Documento'}]}
            (root/'knowledge'/'sources.json').write_text(json.dumps(config))
            video={'id':'V01','youtube_id':'qLA6GBKYT14','url':'https://www.youtube.com/watch?v=qLA6GBKYT14',
                   'title':'Só um título','include_in_context':False,'status':'aguardando_consulta'}
            source=root/'knowledge'/'video_sources.json'
            source.write_text(json.dumps({'videos':[video]}))
            corpus,_=compile_base(root)
            self.assertNotIn('qLA6GBKYT14',corpus)
            video['include_in_context']=True
            source.write_text(json.dumps({'videos':[video]}))
            with self.assertRaisesRegex(ValueError,'sem conteúdo consultado'):
                compile_base(root)


if __name__=='__main__':
    unittest.main()
