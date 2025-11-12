#!/usr/bin/env python3
"""Script para testar credenciais AWS e listar buckets S3"""

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente
load_dotenv()

def test_aws_credentials():
    """Testa credenciais AWS e lista buckets disponíveis"""

    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    print("=" * 60)
    print("TESTE DE CREDENCIAIS AWS")
    print("=" * 60)
    print(f"\nRegião: {aws_region}")
    print(f"Access Key ID: {aws_access_key[:10]}..." if aws_access_key else "Access Key ID: NÃO CONFIGURADO")
    print(f"Secret Access Key: {'*' * 20}" if aws_secret_key else "Secret Access Key: NÃO CONFIGURADO")
    print()

    if not aws_access_key or not aws_secret_key:
        print("❌ ERRO: Credenciais AWS não encontradas no .env")
        return

    try:
        # Criar cliente S3
        s3_client = boto3.client(
            's3',
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )

        print("🔍 Listando buckets S3 disponíveis...\n")

        # Listar buckets
        response = s3_client.list_buckets()

        buckets = response.get('Buckets', [])

        if not buckets:
            print("⚠️  Nenhum bucket encontrado.")
        else:
            print(f"✅ {len(buckets)} bucket(s) encontrado(s):\n")
            for i, bucket in enumerate(buckets, 1):
                bucket_name = bucket['Name']
                creation_date = bucket['CreationDate']
                print(f"  {i}. {bucket_name}")
                print(f"     Criado em: {creation_date}")
                print()

        print("=" * 60)
        print("✅ CREDENCIAIS AWS VÁLIDAS!")
        print("=" * 60)

        # Testar Textract
        print("\n🔍 Testando acesso ao AWS Textract...\n")
        textract_client = boto3.client(
            'textract',
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        print("✅ Cliente Textract inicializado com sucesso!")
        print()

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"❌ ERRO AWS [{error_code}]: {error_message}")
        print("\nVerifique:")
        print("  1. Se as credenciais estão corretas")
        print("  2. Se o usuário IAM tem permissões para S3 e Textract")
        print("  3. Se a região está correta")

    except Exception as e:
        print(f"❌ ERRO: {e}")

if __name__ == "__main__":
    test_aws_credentials()
