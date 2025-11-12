#!/usr/bin/env python3
"""Script para testar acesso a um bucket S3 específico"""

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente
load_dotenv()

def test_bucket_access():
    """Testa acesso a um bucket S3 específico"""

    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    bucket_name = os.getenv("AWS_S3_BUCKET")

    print("=" * 60)
    print("TESTE DE ACESSO AO BUCKET S3")
    print("=" * 60)
    print(f"\nBucket configurado: {bucket_name if bucket_name else 'NÃO CONFIGURADO'}")
    print(f"Região: {aws_region}")
    print()

    if not bucket_name:
        print("❌ ERRO: AWS_S3_BUCKET não configurado no .env")
        return

    try:
        # Criar cliente S3
        s3_client = boto3.client(
            's3',
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )

        print(f"🔍 Testando acesso ao bucket: {bucket_name}...\n")

        # Tentar listar objetos no bucket (limita a 10 para teste rápido)
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            MaxKeys=10
        )

        # Verificar se há objetos
        contents = response.get('Contents', [])

        print(f"✅ Acesso ao bucket '{bucket_name}' bem-sucedido!")
        print(f"\nObjetos no bucket: {response.get('KeyCount', 0)}")

        if contents:
            print("\nPrimeiros objetos encontrados:")
            for i, obj in enumerate(contents[:5], 1):
                print(f"  {i}. {obj['Key']}")
                print(f"     Tamanho: {obj['Size']} bytes")
                print(f"     Modificado: {obj['LastModified']}")
        else:
            print("\n(Bucket vazio - normal para início)")

        print("\n" + "=" * 60)
        print("✅ TESTE DE UPLOAD")
        print("=" * 60)

        # Criar arquivo de teste temporário
        test_content = b"Teste de upload para validar permissoes AWS S3"
        test_key = "test-upload-permission.txt"

        print(f"\n📤 Fazendo upload de arquivo de teste: {test_key}")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content
        )
        print("✅ Upload bem-sucedido!")

        # Tentar ler o arquivo
        print(f"\n📥 Lendo arquivo de teste...")
        response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
        content = response['Body'].read()
        print(f"✅ Leitura bem-sucedida! Conteúdo: {content.decode('utf-8')}")

        # Deletar arquivo de teste
        print(f"\n🗑️  Removendo arquivo de teste...")
        s3_client.delete_object(Bucket=bucket_name, Key=test_key)
        print("✅ Remoção bem-sucedida!")

        print("\n" + "=" * 60)
        print("✅ TODAS AS OPERAÇÕES S3 FUNCIONANDO!")
        print("=" * 60)
        print("\nPermissões validadas:")
        print("  ✅ s3:ListBucket")
        print("  ✅ s3:PutObject")
        print("  ✅ s3:GetObject")
        print("  ✅ s3:DeleteObject")
        print("\nSistema pronto para usar Textract com S3!")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        print(f"❌ ERRO AWS [{error_code}]: {error_message}\n")

        if error_code == 'NoSuchBucket':
            print(f"O bucket '{bucket_name}' não existe.")
            print("\nPossíveis soluções:")
            print("  1. Verifique o nome do bucket no .env (AWS_S3_BUCKET)")
            print("  2. Crie o bucket usando AWS Console ou CLI")
        elif error_code == 'AccessDenied':
            print("Sem permissão para acessar o bucket.")
            print("\nPermissões necessárias:")
            print("  - s3:ListBucket")
            print("  - s3:PutObject")
            print("  - s3:GetObject")
            print("  - s3:DeleteObject")
        else:
            print("Verifique:")
            print("  1. Se o nome do bucket está correto")
            print("  2. Se o usuário IAM tem permissões para S3")
            print("  3. Se a região está correta")

    except Exception as e:
        print(f"❌ ERRO: {e}")

if __name__ == "__main__":
    test_bucket_access()
