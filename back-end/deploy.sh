#!/bin/bash
set -e

# Script de deploy simplificado para PRODUÇÃO (EC2)
# Usa docker-compose.prod.yml que clona automaticamente do GitHub
# Uso: ./deploy.sh

echo "========================================="
echo "🚀 Deploy Automático (com git clone)"
echo "========================================="

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${YELLOW}🛑 Parando containers antigos...${NC}"
docker-compose -f docker-compose.prod.yml down

echo ""
echo -e "${YELLOW}🏗️  Rebuild com código do GitHub (branch v1)...${NC}"
docker-compose -f docker-compose.prod.yml build --no-cache

echo ""
echo -e "${YELLOW}🚀 Subindo containers...${NC}"
docker-compose -f docker-compose.prod.yml up -d

echo ""
echo -e "${YELLOW}⏳ Aguardando containers iniciarem (30s)...${NC}"
sleep 30

echo ""
echo -e "${YELLOW}📊 Status:${NC}"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo -e "${YELLOW}📝 Logs (últimas 20 linhas):${NC}"
docker-compose -f docker-compose.prod.yml logs --tail=20

echo ""
echo -e "${GREEN}✅ Deploy concluído!${NC}"
echo ""
echo -e "${GREEN}O código foi clonado automaticamente do GitHub (branch v1)${NC}"
echo ""
echo "Comandos úteis:"
echo "  docker-compose -f docker-compose.prod.yml logs -f"
echo "  curl http://localhost/health"
echo ""
