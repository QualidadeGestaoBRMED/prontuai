"""
Endpoints do catálogo de exames similares (exame pai + variações).

Painel de curadoria: só ADMIN e MANAGER leem e escrevem; exclusão é
exclusiva de ADMIN, como no resto do sistema.

Esta fase é só catálogo. A geração de vetor por termo e a reconstrução do
índice FAISS entram depois — as colunas de embedding já existem e ficam nulas.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import require_admin, require_management
from app.core.config import settings
from app.core.database import user_db
from app.core.logging import set_audit_context
from app.services import exam_catalog_source, exam_vector_service
from app.models.exam import (
    ExamCatalogStats,
    ExamPendency,
    ExamConflictResolution,
    ExamParent,
    ExamParentCreate,
    ExamParentDetail,
    ExamParentUpdate,
    ExamVariation,
    ExamVariationConflict,
    ExamVariationCreate,
    ExamVariationUpdate,
)
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exams", tags=["Catálogo de Exames"])


async def _pos_escrita(termos: list[tuple[str, str, bool]]) -> dict:
    """
    Fecha uma escrita no catálogo: invalida o cache do motor, gera os vetores dos
    termos alterados e reconstrói o índice.

    **A invalidação é a parte que muda o comportamento da validação.** O motor
    monta o portão de extração e o mapa de sinônimos em cache; sem descartá-lo,
    um exame cadastrado no painel só passaria a valer no próximo restart.

    Cada item é (id da linha, texto a vetorizar, é variação).

    **Best-effort de propósito.** A escrita no banco já foi confirmada quando
    isto roda: se a OpenAI falhar ou a chave não existir, o exame continua
    cadastrado e a linha fica com `embedding` nulo — que é o próprio marcador de
    pendência. Derrubar o cadastro porque um serviço externo caiu seria pior:
    o curador perderia o trabalho por um motivo que não tem a ver com ele.

    A reconstrução é do índice inteiro, ~17ms para o catálogo completo, e roda
    mesmo quando `termos` está vazio (o caso da exclusão, em que nada é
    vetorizado mas o índice precisa perder a linha).
    """
    relatorio = {"vetorizados": 0, "falhas": 0, "vetores_no_indice": None, "aviso": None}

    # Primeiro o cache: mesmo que a vetorização falhe, o vocabulário novo passa a
    # valer — e é ele que conserta a maior parte dos casos medidos.
    exam_catalog_source.invalidar()

    if termos and not exam_vector_service.vetorizacao_disponivel():
        relatorio["aviso"] = "OPENAI_API_KEY não configurada: termos ficaram sem vetor"
        logger.warning(f"[EXAMS] {relatorio['aviso']}")
    elif termos:
        for row_id, texto, eh_variacao in termos:
            try:
                vetor = await exam_vector_service.gerar_embedding(texto)
                user_db.salvar_embedding_exame(
                    row_id=row_id,
                    embedding=vetor,
                    modelo=settings.MODELO_EMBEDDING,
                    eh_variacao=eh_variacao,
                )
                relatorio["vetorizados"] += 1
            except Exception as e:
                relatorio["falhas"] += 1
                logger.error(
                    f"[EXAMS] Falha ao vetorizar '{texto}': {type(e).__name__}: {e}"
                )

    try:
        resumo = exam_vector_service.reconstruir_indice(user_db.listar_vetores_catalogo())
        relatorio["vetores_no_indice"] = resumo["vetores"]
        if not resumo["assinado"]:
            relatorio["aviso"] = "índice gravado sem assinatura (ARTIFACT_SIGNING_KEY ausente)"
    except Exception as e:
        logger.exception(f"[EXAMS] Falha ao reconstruir índice do catálogo: {e}")
        relatorio["aviso"] = f"índice não reconstruído: {type(e).__name__}"

    return relatorio


# ----------------------------------------------------------------------
# Rotas literais vêm antes de /{parent_id}, senão o path param as engole.
# ----------------------------------------------------------------------


@router.get("/stats", response_model=ExamCatalogStats)
async def get_catalog_stats(current_user: User = Depends(require_management)):
    """Resumo do catálogo para o cabeçalho do painel."""
    try:
        return user_db.get_exam_catalog_stats()
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao obter estatísticas do catálogo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas do catálogo",
        )


@router.get("/pendencies", response_model=List[ExamPendency])
async def list_pendencies(
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(require_management),
):
    """
    Exames que o BRNET pede e que não têm pai no catálogo.

    É a pendência mais consequente da curadoria: sem pai, a comparação nunca
    encontra o exame — nem por sinônimo, nem pela varredura do markdown. Ordenado
    por quantidade de documentos em que o BRNET pediu o exame.
    """
    try:
        return user_db.listar_exames_brnet_sem_pai(limit=limit)
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao listar pendências: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar pendências do catálogo",
        )


@router.get("/conflicts", response_model=List[ExamVariationConflict])
async def list_conflicts(
    pending_only: bool = True,
    current_user: User = Depends(require_management),
):
    """
    Termos que a importação viu sob mais de um pai e não atribuiu.
    Nenhuma escolha automática é feita: cada um espera decisão humana.
    """
    try:
        return user_db.list_exam_conflicts(pending_only=pending_only)
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao listar conflitos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar conflitos de importação",
        )


@router.post("/conflicts/{conflict_id}/resolve", response_model=ExamVariationConflict)
async def resolve_conflict(
    conflict_id: str,
    payload: ExamConflictResolution,
    current_user: User = Depends(require_management),
):
    """Atribui a variação em conflito a um pai, ou descarta o termo."""
    try:
        conflito = user_db.resolve_exam_conflict(
            conflict_id=conflict_id,
            resolution=payload.resolution,
            parent_id=payload.parent_id,
            actor=current_user.email,
        )
        if not conflito:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conflito não encontrado",
            )

        if payload.resolution == "atribuida":
            # A variação criada pela resolução precisa entrar no índice.
            nova = next(
                (
                    v
                    for v in (user_db.get_exam_parent(payload.parent_id).variations
                              if payload.parent_id else [])
                    if v.name_normalized == conflito.name_normalized
                ),
                None,
            )
            if nova:
                await _pos_escrita([(nova.id, nova.name, True)])

        set_audit_context({
            "conflict_id": conflict_id,
            "resolution": payload.resolution,
            "parent_id": payload.parent_id,
        })
        logger.info(
            f"[EXAMS] {current_user.email} resolveu conflito {conflict_id} "
            f"como '{payload.resolution}'"
        )
        return conflito
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao resolver conflito {conflict_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao resolver conflito",
        )


@router.patch("/variations/{variation_id}", response_model=ExamVariation)
async def update_variation(
    variation_id: str,
    payload: ExamVariationUpdate,
    current_user: User = Depends(require_management),
):
    """Renomeia, ativa/desativa, ou move a variação para outro pai."""
    try:
        variacao = user_db.update_exam_variation(
            variation_id=variation_id,
            name=payload.name,
            parent_id=payload.parent_id,
            is_active=payload.is_active,
            actor=current_user.email,
        )
        if not variacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Variação não encontrada",
            )

        await _pos_escrita(
            [(variacao.id, variacao.name, True)] if payload.name is not None else []
        )

        set_audit_context({"variation_id": variation_id, "parent_id": variacao.parent_id})
        logger.info(f"[EXAMS] {current_user.email} atualizou variação {variation_id}")
        return variacao
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao atualizar variação {variation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar variação",
        )


@router.delete("/variations/{variation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variation(
    variation_id: str,
    current_user: User = Depends(require_admin),
):
    """Remove uma variação. Apenas ADMIN."""
    try:
        if not user_db.delete_exam_variation(variation_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Variação não encontrada",
            )
        await _pos_escrita([])
        set_audit_context({"variation_id": variation_id})
        logger.info(f"[EXAMS] {current_user.email} removeu variação {variation_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao remover variação {variation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover variação",
        )


# ----------------------------------------------------------------------
# Exame pai
# ----------------------------------------------------------------------


@router.get("")
async def list_parents(
    search: Optional[str] = None,
    exam_status: Optional[str] = Query(None, alias="status"),
    include_inactive: bool = False,
    only_without_variations: bool = False,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_management),
):
    """
    Lista exames pai com a contagem de variações.

    `search` casa tanto o nome do pai quanto o de qualquer variação dele —
    quem procura "transaminase" quer achar TGP (ALT).
    """
    if exam_status is not None and exam_status not in ("ativo", "quarentena"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status deve ser 'ativo' ou 'quarentena'",
        )
    try:
        itens, total = user_db.list_exam_parents(
            search=search,
            status=exam_status,
            include_inactive=include_inactive,
            only_without_variations=only_without_variations,
            limit=limit,
            offset=offset,
        )
        return {"items": itens, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao listar exames: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar exames",
        )


@router.post("", response_model=ExamParentDetail, status_code=status.HTTP_201_CREATED)
async def create_parent(
    payload: ExamParentCreate,
    current_user: User = Depends(require_management),
):
    """
    Cria um exame pai, com variações opcionais no mesmo passo.

    Colisão de nome (com outro pai ou com variação existente) responde 409:
    o catálogo é árvore estrita, um termo pertence a um único lugar.
    """
    try:
        pai = user_db.create_exam_parent(
            name=payload.name,
            status=payload.status,
            is_external=payload.is_external,
            notes=payload.notes,
            variations=payload.variations,
            source="manual",
            actor=current_user.email,
        )
        termos = [(pai.id, pai.name, False)]
        termos += [(v.id, v.name, True) for v in pai.variations]
        vetor = await _pos_escrita(termos)

        set_audit_context({
            "parent_id": pai.id, "name": pai.name, "status": pai.status,
            "vetorizados": vetor["vetorizados"], "falhas_vetor": vetor["falhas"],
        })
        logger.info(
            f"[EXAMS] {current_user.email} criou exame pai '{pai.name}' ({pai.id}) "
            f"| vetores: {vetor['vetorizados']} ok, {vetor['falhas']} falha(s)"
        )
        # Recarrega para o has_embedding do retorno refletir o que foi gravado.
        return user_db.get_exam_parent(pai.id) or pai
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao criar exame pai: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar exame pai",
        )


@router.get("/{parent_id}", response_model=ExamParentDetail)
async def get_parent(
    parent_id: str,
    current_user: User = Depends(require_management),
):
    """Exame pai com todas as variações."""
    try:
        pai = user_db.get_exam_parent(parent_id)
        if not pai:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exame não encontrado",
            )
        return pai
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao obter exame {parent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter exame",
        )


@router.patch("/{parent_id}", response_model=ExamParentDetail)
async def update_parent(
    parent_id: str,
    payload: ExamParentUpdate,
    current_user: User = Depends(require_management),
):
    """Atualiza exame pai. Campos ausentes no corpo ficam como estão."""
    try:
        pai = user_db.update_exam_parent(
            parent_id=parent_id,
            name=payload.name,
            status=payload.status,
            is_external=payload.is_external,
            is_active=payload.is_active,
            notes=payload.notes,
            actor=current_user.email,
        )
        if not pai:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exame não encontrado",
            )
        # Invalida sempre; vetoriza só quando o nome muda, porque renomear torna
        # o vetor antigo obsoleto.
        await _pos_escrita([(pai.id, pai.name, False)] if payload.name is not None else [])

        set_audit_context({"parent_id": parent_id, "name": pai.name, "status": pai.status})
        logger.info(f"[EXAMS] {current_user.email} atualizou exame pai {parent_id}")
        return user_db.get_exam_parent(parent_id) or pai
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao atualizar exame {parent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar exame",
        )


@router.delete("/{parent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parent(
    parent_id: str,
    current_user: User = Depends(require_admin),
):
    """Remove exame pai e todas as suas variações. Apenas ADMIN."""
    try:
        if not user_db.delete_exam_parent(parent_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exame não encontrado",
            )
        vetor = await _pos_escrita([])
        set_audit_context({"parent_id": parent_id, "vetores_no_indice": vetor["vetores_no_indice"]})
        logger.info(f"[EXAMS] {current_user.email} removeu exame pai {parent_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao remover exame {parent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover exame",
        )


@router.post(
    "/{parent_id}/variations",
    response_model=ExamVariation,
    status_code=status.HTTP_201_CREATED,
)
async def create_variation(
    parent_id: str,
    payload: ExamVariationCreate,
    current_user: User = Depends(require_management),
):
    """Adiciona uma variação ao exame pai."""
    try:
        variacao = user_db.create_exam_variation(
            parent_id=parent_id,
            name=payload.name,
            source="manual",
            actor=current_user.email,
        )
        if not variacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exame pai não encontrado",
            )
        vetor = await _pos_escrita([(variacao.id, variacao.name, True)])
        set_audit_context({
            "parent_id": parent_id, "variation_id": variacao.id,
            "vetorizados": vetor["vetorizados"], "falhas_vetor": vetor["falhas"],
        })
        logger.info(
            f"[EXAMS] {current_user.email} adicionou variação '{variacao.name}' "
            f"ao exame {parent_id} | vetores: {vetor['vetorizados']} ok, {vetor['falhas']} falha(s)"
        )
        variacao.has_embedding = vetor["vetorizados"] > 0
        return variacao
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception(f"[EXAMS] Erro ao adicionar variação ao exame {parent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao adicionar variação",
        )
