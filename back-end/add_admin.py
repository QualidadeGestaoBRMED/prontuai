#!/usr/bin/env python3
"""
Script para adicionar um usuário admin ao banco de dados.
Uso: python add_admin.py seu-email@gmail.com "Seu Nome"
"""
import sys
from app.core.database import user_db
from app.models.user import UserRole

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python add_admin.py <email> <nome>")
        print("Exemplo: python add_admin.py joao@gmail.com 'João Silva'")
        sys.exit(1)

    email = sys.argv[1]
    name = sys.argv[2]

    try:
        user = user_db.create_user(
            email=email,
            name=name,
            role=UserRole.ADMIN
        )
        print(f"✅ Admin criado com sucesso!")
        print(f"   Email: {user.email}")
        print(f"   Nome: {user.name}")
        print(f"   Role: {user.role}")
        print(f"   ID: {user.id}")
    except ValueError as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)
