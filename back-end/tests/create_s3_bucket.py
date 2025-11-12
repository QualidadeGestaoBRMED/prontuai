#!/usr/bin/env python3
"""Script para criar bucket S3 para Textract"""

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente
load_dotenv()

def create_bucket():
    """Cria bucket S3 para Textract"""

    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    # Sugerir nome único para o bucket (buckets S3 são globalmente únicos)
    bucket_name = "brmed-prontuai-textract"

    print("=" * 60)
    print("CRIAÇÃO DE BUCKET S3 PARA TEXTRACT")
    print("=" * 60)
    print(f"\nNome do bucket: {bucket_name}")
    print(f"Região: {aws_region}")
    print()

    try:
        # Criar cliente S3
        s3_client = boto3.client(
            's3',
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )

        print(f"🔨 Tentando criar bucket: {bucket_name}...\n")

        # Criar bucket
        # Nota: us-east-1 não precisa de LocationConstraint
        if aws_region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': aws_region}
            )

        print(f"✅ Bucket '{bucket_name}' criado com sucesso!")

        # Testar acesso
        print(f"\n🔍 Testando acesso ao bucket...\n")
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        print(f"✅ Acesso confirmado! Bucket está vazio e pronto para uso.")

        print("\n" + "=" * 60)
        print("✅ BUCKET CRIADO COM SUCESSO!")
        print("=" * 60)
        print(f"\nAtualize o .env com:")
        print(f"AWS_S3_BUCKET={bucket_name}")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        print(f"❌ ERRO AWS [{error_code}]: {error_message}\n")

        if error_code == 'BucketAlreadyExists':
            print(f"O bucket '{bucket_name}' já existe globalmente (pertence a outra conta).")
            print("\nTente um nome mais único, como:")
            print(f"  - brmed-prontuai-textract-{os.getenv('USER', 'user')}")
            print(f"  - brmed-ocr-{os.getenv('USER', 'user')}-2025")
        elif error_code == 'BucketAlreadyOwnedByYou':
            print(f"✅ O bucket '{bucket_name}' já existe e pertence a você!")
            print(f"\nAtualize o .env com:")
            print(f"AWS_S3_BUCKET={bucket_name}")
        elif error_code == 'AccessDenied':
            print("Sem permissão para criar buckets.")
            print("\n⚠️  O Diogo pode já ter criado um bucket para você.")
            print("Entre em contato com ele para obter o nome do bucket.")
            print("\nOu peça para ele adicionar a permissão 's3:CreateBucket'")
        else:
            print("Verifique:")
            print("  1. Se o usuário IAM tem permissão s3:CreateBucket")
            print("  2. Se a região está correta")
            print("  3. Se as credenciais estão válidas")

    except Exception as e:
        print(f"❌ ERRO: {e}")

if __name__ == "__main__":
    create_bucket()
