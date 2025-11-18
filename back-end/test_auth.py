#!/usr/bin/env python3
"""
Script para testar autenticação e criar token JWT manualmente
"""
from dotenv import load_dotenv
load_dotenv()

from app.core.database import user_db
from app.core.auth import create_access_token

# Buscar usuário
email = "gabriel.rodrigues@grupobrmed.com.br"
user = user_db.get_user_by_email(email)

if not user:
    print(f"❌ Usuário {email} não encontrado")
    exit(1)

print(f"✅ Usuário encontrado: {user.email} ({user.role})")
print()

# Criar token JWT
token = create_access_token({"sub": user.id})
print("🔑 Token JWT gerado:")
print(token)
print()
print("Use este token para testar a API:")
print(f'curl -H "Authorization: Bearer {token}" http://localhost:8000/v1/users')
