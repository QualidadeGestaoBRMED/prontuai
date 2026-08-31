"""
Vetorização do catálogo de exames e reconstrução do índice FAISS.

Um vetor por termo: o exame pai e cada variação ganham embedding próprio,
apontando para o id do pai. Evita o centroide diluído de concatenar variações
heterogêneas num único vetor.

**Artefato separado de propósito.** Este módulo escreve
`data/exam_catalog_index.faiss`, não o `data/exam_similarity_index.faiss` que
`workflow_service` e `validacao_service` carregam. Os formatos são
incompatíveis: o antigo resolve o resultado da busca por POSIÇÃO na lista JSON
(`exam_similarity_data[idx]`), este usa `IndexIDMap2` com id estável na própria
linha. Sobrescrever o arquivo do motor quebraria a validação em produção.

O motor passa a ler daqui num passo seguinte, não neste.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import tempfile
import threading
import uuid as uuid_lib

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

DIMENSOES = 3072  # text-embedding-3-large
INDEX_PATH = os.path.join(settings.BASE_DIR, "data", "exam_catalog_index.faiss")
SIGNATURE_PATH = f"{INDEX_PATH}.hmac"

# Reconstrução e troca do arquivo acontecem sob lock: WORKERS=1 garante um
# processo, mas não impede duas requisições concorrentes do painel.
_LOCK_RECONSTRUCAO = threading.Lock()


def vetorizacao_disponivel() -> bool:
    """Sem chave da OpenAI não há como gerar vetor; o cadastro segue sem ele."""
    return bool(settings.OPENAI_API_KEY)


def assinatura_disponivel() -> bool:
    return bool(settings.ARTIFACT_SIGNING_KEY)


def derivar_vector_id(row_id: str) -> int:
    """
    Id int64 estável para o FAISS, derivado da UUID da linha.

    Determinístico: dá para recalcular sem sequence. Usa os 63 bits baixos para
    manter o valor positivo. A coluna tem UNIQUE, então colisão falha alto.
    """
    try:
        bruto = uuid_lib.UUID(row_id).bytes
    except (ValueError, AttributeError, TypeError):
        bruto = hashlib.sha256(str(row_id).encode("utf-8")).digest()
    return int.from_bytes(bruto[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


async def gerar_embedding(texto: str) -> bytes:
    """
    Embedding de um termo, serializado em bytes float32 para gravar na linha.

    Levanta a exceção da API para quem chamou decidir — no painel, a decisão é
    manter o cadastro e deixar o vetor nulo.
    """
    from openai import AsyncOpenAI  # import tardio: módulo é carregado no startup

    cliente = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    resposta = await cliente.embeddings.create(
        input=[texto], model=settings.MODELO_EMBEDDING
    )
    vetor = np.array(resposta.data[0].embedding, dtype="float32")
    if vetor.shape[0] != DIMENSOES:
        raise ValueError(
            f"Embedding com {vetor.shape[0]} dimensões, esperado {DIMENSOES}. "
            f"MODELO_EMBEDDING={settings.MODELO_EMBEDDING}"
        )
    return vetor.tobytes()


def _assinar(caminho: str) -> str:
    digest = hmac.new(settings.ARTIFACT_SIGNING_KEY.encode("utf-8"), digestmod=hashlib.sha256)
    with open(caminho, "rb") as handle:
        for bloco in iter(lambda: handle.read(8192), b""):
            digest.update(bloco)
    return digest.hexdigest()


def reconstruir_indice(linhas: list[tuple[int, bytes]]) -> dict:
    """
    Reconstrói o índice inteiro a partir dos vetores já gravados no banco.

    `linhas` são pares (vector_id, bytes do vetor). Reconstruir tudo custa ~17ms
    para o catálogo completo (medido: 750 termos, build 2ms + write 6ms +
    assinatura 9ms), então não vale a complexidade de append incremental — que
    além do mais não resolve edição nem exclusão.

    Escreve em arquivo temporário, faz fsync e troca por rename atômico: quem
    estiver lendo o índice antigo nunca vê um arquivo pela metade.
    """
    import faiss  # import tardio: dependência pesada

    with _LOCK_RECONSTRUCAO:
        base = faiss.IndexFlatL2(DIMENSOES)
        indice = faiss.IndexIDMap2(base)

        if linhas:
            ids = np.array([vid for vid, _ in linhas], dtype="int64")
            vetores = np.vstack(
                [np.frombuffer(bruto, dtype="float32").reshape(1, -1) for _, bruto in linhas]
            )
            if vetores.shape[1] != DIMENSOES:
                raise ValueError(
                    f"Vetores com {vetores.shape[1]} dimensões, esperado {DIMENSOES}"
                )
            indice.add_with_ids(vetores, ids)

        os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=os.path.dirname(INDEX_PATH), suffix=".faiss.tmp", delete=False
        ) as handle:
            caminho_tmp = handle.name
        try:
            faiss.write_index(indice, caminho_tmp)
            with open(caminho_tmp, "rb") as handle:
                os.fsync(handle.fileno())

            assinatura = _assinar(caminho_tmp) if assinatura_disponivel() else None
            if assinatura is None:
                logger.warning(
                    "ARTIFACT_SIGNING_KEY ausente: índice do catálogo gravado SEM assinatura."
                )

            os.replace(caminho_tmp, INDEX_PATH)
            if assinatura:
                tmp_sig = f"{SIGNATURE_PATH}.tmp"
                with open(tmp_sig, "w", encoding="utf-8") as handle:
                    handle.write(assinatura)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_sig, SIGNATURE_PATH)
        except Exception:
            if os.path.exists(caminho_tmp):
                os.unlink(caminho_tmp)
            raise

        logger.info(
            f"[EXAM_VECTOR] Índice do catálogo reconstruído: {indice.ntotal} vetores"
        )
        return {
            "vetores": indice.ntotal,
            "caminho": INDEX_PATH,
            "assinado": assinatura is not None,
        }
