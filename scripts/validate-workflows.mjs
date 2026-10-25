import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const root=resolve(process.argv[2] || 'workflows');
let count=0;
let reviewedInTestMode=false;
for (const filename of readdirSync(root).filter(x=>x.endsWith('.json'))) {
  const workflow=JSON.parse(readFileSync(resolve(root,filename),'utf8'));
  if(workflow.active) throw new Error(`${filename}: workflow deve estar desativado`);
  const names=new Set(workflow.nodes.map(n=>n.name));
  for(const [name,connections] of Object.entries(workflow.connections)) {
    if(!names.has(name)) throw new Error(`Origem inexistente: ${name}`);
    for(const output of Object.values(connections)) for(const edges of output) for(const edge of edges)
      if(!names.has(edge.node)) throw new Error(`Destino inexistente: ${edge.node}`);
  }
  for(const node of workflow.nodes) {
    if(node.type==='n8n-nodes-base.code') {
      new Function('$input','$json','$',node.parameters.jsCode);
      count++;
      if(node.name==='Validar decisao') {
        const run=new Function('$json','$',node.parameters.jsCode);
        const decision={decisao:'responder',categoria:'comercial_geral',motivo:'Informação disponível',
          resposta_html:'<p>Resposta de teste</p>',produto_modulo:'QualitControl',resumo_solicitacao:'Dúvida',
          informacoes_pendentes:[],rascunho_html:''};
        const source={elegivel:true,id_email:'TEST-INVALID-ID',controle_duplicidade_confirmado:true,envio_automatico_habilitado:false};
        const result=run({text:JSON.stringify(decision)},()=>({item:{json:source}}));
        if(result.json.decisao!=='revisao_humana' || result.json.resposta_html!=='' || !result.json.rascunho_html)
          throw new Error('O modo de teste precisa converter a resposta em rascunho para revisão');
        source.envio_automatico_habilitado=true;
        const enabled=run({text:JSON.stringify(decision)},()=>({item:{json:source}}));
        if(enabled.json.decisao!=='responder') throw new Error('A opção explícita de automação não foi preservada');
        reviewedInTestMode=true;
      }
    }
  }
}
if(!reviewedInTestMode) throw new Error('Nó de validação da IA ausente');
console.log(`Três grafos validados; ${count} nós Code compilados; flags e rascunho de revisão verificados sem executar envios.`);
