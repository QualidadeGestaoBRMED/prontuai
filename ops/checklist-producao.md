# Checklist final de producao (ProntuAI)

## Infra
- [ ] Backend acessivel por dominio publico (Nginx/Ngrok OK)
- [ ] TLS ativo no endpoint publico
- [ ] Firewall basico e rate limit

## Segurança
- [ ] Credenciais fora do repo
- [ ] LOG_FORMAT=json sem dados sensiveis em texto livre
- [ ] JWT_SECRET_KEY alterada

## Operacao
- [ ] OCR OK (Textract)
- [ ] API ProntuAI OK
- [ ] Jobs rodando sem travar fila

## Observabilidade
- [ ] Loki + Grafana ativos
- [ ] Dashboard "ProntuAI - Logs" funcionando
- [ ] Alertas configurados (contact point)

## UX
- [ ] Loading correto em pendentes/checagem
- [ ] Ordenacao correta (mais recente primeiro)
- [ ] Mensagens em PT-BR

## Dados
- [ ] Auditoria ativa (POST/PATCH/DELETE)
- [ ] Retencao definida (logs e documentos)
- [ ] Backup testado

