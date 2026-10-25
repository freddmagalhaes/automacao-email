import { writeFileSync } from 'node:fs';

const credentials = [
  {
    id: 'EmailTestePostgres01', name: 'PostgreSQL - Atendimento Teste', type: 'postgres',
    data: {
      host: 'postgres', port: 5432, database: 'atendimento', user: 'automacao_app',
      password: process.env.AUTOMATION_DB_PASSWORD, ssl: 'disable',
    },
  },
  { id: 'EmailTesteGmail01', name: 'Gmail - Conta de Testes', type: 'gmailOAuth2', data: {} },
  {
    id: 'EmailTesteGemini01', name: 'Gemini - Testes', type: 'googlePalmApi',
    data: { apiKey: process.env.GEMINI_API_KEY || '', host: 'https://generativelanguage.googleapis.com' },
  },
];
writeFileSync('/tmp/email-credentials.json', JSON.stringify(credentials), { mode: 0o600 });
