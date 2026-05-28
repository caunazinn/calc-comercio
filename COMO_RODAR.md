# Como colocar a Calculadora de Sobrevivência no ar

Siga os passos na ordem. Cada etapa leva menos de 10 minutos.

---

## PASSO 1 — Criar o bot no Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Mande `/newbot`
3. Escolha um nome (ex: *Calculadora de Sobrevivência*)
4. Escolha um username (ex: `calculadora_sobrev_bot`)
5. Guarde o **token** que ele retornar (parece com `123456789:AAExxxxxxxx`)

---

## PASSO 2 — Configurar o Google Sheets

### 2.1 — Criar a planilha
1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma planilha em branco
2. Copie o **ID** da URL: `docs.google.com/spreadsheets/d/**SEU_ID_AQUI**/edit`

### 2.2 — Criar credenciais no Google Cloud
1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto (ex: *calculadora-sobrevivencia*)
3. Ative as APIs: **Google Sheets API** + **Google Drive API**
   - Menu lateral → APIs e Serviços → Biblioteca → busca e ativa as duas
4. Crie conta de serviço:
   - Menu lateral → IAM e Administrador → Contas de serviço → Criar
   - Nome: `calculadora-bot` → Criar e continuar → Concluído
5. Gere a chave JSON:
   - Clique na conta criada → Chaves → Adicionar chave → JSON
   - Salve o arquivo como `service_account.json` dentro da pasta `credentials/`
6. Compartilhe a planilha:
   - Abra o arquivo JSON e copie o campo `"client_email"` (termina em `.gserviceaccount.com`)
   - Na sua planilha do Sheets → Compartilhar → cole o e-mail → permissão de Editor

### 2.3 — Configurar o .env
```bash
cp .env.example .env
```
Edite o `.env` e preencha:
```
GOOGLE_SHEETS_ID=cole_o_id_da_sua_planilha
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
```

### 2.4 — Inicializar a planilha
```bash
python scripts/setup_sheets.py
```
Isso cria as abas `taxas_maquininha` e `historico_calculos` automaticamente.

---

## PASSO 3 — Fazer o deploy do servidor Python

### Opção A: Railway (recomendado — grátis)
1. Acesse [railway.app](https://railway.app) → Login com GitHub
2. **New Project → Deploy from GitHub repo**
3. Selecione `calculadora-sobrevivencia`
4. Vá em **Variables** e adicione:
   - `GOOGLE_SHEETS_ID` = seu ID
   - `GOOGLE_CREDENTIALS_PATH` = `credentials/service_account.json`
5. Vá em **Settings → Domains → Generate Domain**
6. Guarde a URL gerada (ex: `https://calculadora-xxx.up.railway.app`)

> ⚠️ O arquivo `credentials/service_account.json` precisa estar no repositório
> ou ser configurado como variável de ambiente (base64). Para projetos de curso,
> pode commitar temporariamente — só remova antes de tornar o repo público.

### Opção B: Render (também grátis)
1. Acesse [render.com](https://render.com) → New Web Service → GitHub
2. O `render.yaml` já configura tudo automaticamente
3. Adicione as variáveis de ambiente no painel
4. Guarde a URL do serviço

---

## PASSO 4 — Configurar o n8n

### 4.1 — Instalar / acessar o n8n
- **Nuvem grátis**: [app.n8n.cloud](https://app.n8n.cloud) (recomendado para começar)
- **Local**: `npx n8n` no terminal

### 4.2 — Importar o fluxo
1. No n8n → **Workflows → Import from File**
2. Selecione `n8n/fluxo_calculadora.json`
3. O fluxo abrirá com todos os nós prontos

### 4.3 — Configurar credencial do Telegram
1. Clique em qualquer nó do Telegram (ex: "Enviar Boas-vindas")
2. Em **Credential → Create New**
3. Cole o token do @BotFather
4. Salve — o n8n aplica a credencial em todos os nós automaticamente

### 4.4 — Configurar a variável da API
1. No n8n → **Settings → Variables → Add Variable**
2. Nome: `API_URL`
3. Valor: URL do seu servidor (ex: `https://calculadora-xxx.up.railway.app`)

### 4.5 — Ativar o workflow
- Clique no toggle no canto superior direito → **Active**

---

## PASSO 5 — Testar

Abra o Telegram, procure o bot pelo username e mande:

```
/start
```
```
/calcular
```
```
custo: 85
margem: 30
pagamento: credito_vista
fixas: 5
vendas: 40
mei: comercio
```

**Resposta esperada:**
```
🧮 CALCULADORA DE SOBREVIVÊNCIA
💳 Pagamento: Crédito à Vista (1x)
📦 Custo do produto: R$ 85.00
📊 DAS-MEI diluído: R$ 1.92
💳 Taxa maquininha (2.99%): R$ 4.19
🏠 Despesas fixas: R$ 7.01
💰 PREÇO DE VENDA: R$ 140.17
✅ Lucro real: R$ 42.05 (30.0%)
```

---

## Estrutura dos arquivos

```
calculadora_sobrevivencia/
├── config.py                  ← Taxas e constantes
├── calculos_financeiros.py    ← Motor de cálculo (Markup + MC)
├── database_sheets.py         ← Integração Google Sheets
├── main.py                    ← API FastAPI (recebe requisições do n8n)
├── requirements.txt
├── Procfile                   ← Deploy Railway/Heroku
├── railway.toml               ← Config Railway
├── render.yaml                ← Config Render
├── .env.example               ← Template de configuração
├── n8n/
│   ├── fluxo_calculadora.json ← Workflow importável no n8n
│   ├── payload_entrada_exemplo.json
│   └── payload_saida_exemplo.json
├── scripts/
│   └── setup_sheets.py        ← Inicializa a planilha automaticamente
├── testes/
│   └── test_calculos.py       ← 18 testes unitários
└── credentials/
    └── service_account.json   ← (você coloca aqui — não commitar no GitHub público)
```
