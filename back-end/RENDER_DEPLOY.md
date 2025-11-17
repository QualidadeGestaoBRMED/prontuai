# Deploy no Render - Guia Rápido

## 1. Criar conta no Render

Acesse: https://render.com e faça login com GitHub

## 2. Conectar repositório

1. No dashboard do Render, clique em **New +** → **Blueprint**
2. Conecte seu repositório GitHub
3. Selecione o repositório `prontuai`
4. O Render vai detectar automaticamente o `render.yaml`

## 3. Configurar variáveis de ambiente

No dashboard do Render, vá em **Environment** e adicione:

```bash
OPENAI_API_KEY=sk-proj-...
BRMED_USERNAME=seu_usuario
BRMED_PASSWORD=sua_senha
AWS_ACCESS_KEY_ID=sua_key_id
AWS_SECRET_ACCESS_KEY=sua_secret_key
JWT_SECRET_KEY=gere_uma_chave_aleatoria_aqui
```

**Gerar JWT_SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 4. Deploy

O Render vai fazer o deploy automaticamente!

Aguarde ~5-10 minutos para o build completar.

## 5. Obter URL da API

Após deploy, a URL será algo como:
```
https://prontuai-backend.onrender.com
```

## 6. Testar

```bash
curl https://prontuai-backend.onrender.com/health
# Deve retornar: {"status":"healthy"}
```

## 7. Atualizar front-end

No Vercel, adicione a variável de ambiente:
```
NEXT_PUBLIC_API_URL=https://prontuai-backend.onrender.com
```

## Notas importantes

- **Plano Free**: O serviço hiberna após 15 min de inatividade
- **Cold start**: Primeira requisição após hibernar demora ~30s
- **Upgrade para Starter ($7/mês)**: Sem hibernação
- **Logs**: Disponíveis no dashboard do Render

## Troubleshooting

### Erro de build
```bash
# Verificar requirements.txt tem gunicorn e uvicorn
grep gunicorn requirements.txt
grep uvicorn requirements.txt
```

### Porta incorreta
O Render injeta a variável `$PORT` automaticamente. O comando já está configurado no render.yaml.

### Timeout
Aumente o timeout no render.yaml (padrão: 300s)
