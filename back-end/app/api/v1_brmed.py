from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from app.services import workflow_service, brmed_service
from app.core.job_manager import job_manager
from app.core.auth import require_sender, get_current_user
from app.models.user import User, UserRole
from app.core.database import user_db
import logging
import json
import asyncio
import tempfile
import shutil

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/processar-documento", summary="Processar documento completo com OCR, BRMED e Validação")
async def processar_documento_completo_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True), # Recebe como string JSON
    current_user: User = Depends(require_sender) # Requer autenticação SENDER
):
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição de processamento completo.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

    # Log de entrada da requisição
    file_size = "desconhecido"
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        await arquivo.seek(0)  # Rewind para o workflow poder ler
    except:
        pass

    logger.info(f"[REQUEST] Documento recebido: {arquivo.filename} ({file_size})")

    try:
        # Converte a string JSON de exames_obrigatorios para lista
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST] Exames obrigatórios fornecidos: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios. Esperado JSON array de strings.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exames obrigatórios devem ser um array JSON válido.")

    try:
        resultado = await workflow_service.processar_documento_completo(arquivo, exames_obrigatorios_list)
        logger.info(f"[REQUEST] Processamento concluído com sucesso para: {arquivo.filename}")

        # Salvar documento no banco de dados
        if current_user.clinic_id:
            try:
                # Extrair informações do resultado
                cpf = resultado.get('ocr', {}).get('cpf_extraido', None)
                exams_found = resultado.get('ocr', {}).get('exames_encontrados', [])
                ocr_markdown = resultado.get('ocr', {}).get('resultado_markdown', '')
                validation_status = 'validated' if resultado.get('validacao', {}).get('todos_presentes', False) else 'pending'

                # Criar documento no banco
                document = user_db.create_document(
                    clinic_id=current_user.clinic_id,
                    uploaded_by_user_id=current_user.id,
                    filename=arquivo.filename,
                    cpf=cpf,
                    exams_found=exams_found,
                    validation_status=validation_status,
                    ocr_markdown=ocr_markdown
                )

                logger.info(f"[DB] Documento salvo com ID: {document.id}")
                resultado['document_id'] = document.id
            except Exception as db_error:
                logger.error(f"[DB] Erro ao salvar documento: {db_error}")
                # Não interromper o fluxo se falhar ao salvar no banco

        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado no processamento completo do documento: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no processamento do documento.")

@router.post("/processar-documento-stream", summary="Processar documento com feedback em tempo real (SSE)")
async def processar_documento_stream_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True)
):
    """Endpoint com Server-Sent Events para feedback de progresso em tempo real."""

    if not arquivo:
        logger.warning("Arquivo não enviado na requisição de processamento stream.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

    # Log de entrada
    file_size = "desconhecido"
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        await arquivo.seek(0)
    except:
        pass

    logger.info(f"[REQUEST-STREAM] Documento recebido: {arquivo.filename} ({file_size})")

    try:
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST-STREAM] Exames obrigatórios: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exames obrigatórios devem ser um array JSON válido.")

    async def event_generator():
        """Gerador de eventos SSE."""
        try:
            # Enviar evento inicial
            yield f"data: {json.dumps({'progress': 0, 'step': 'inicio', 'message': 'Documento recebido, iniciando processamento...'})}\n\n"
            await asyncio.sleep(0.1)

            # Lista para coletar eventos de progresso
            progress_events = []

            # Callback para receber updates do workflow
            async def progress_callback(progress: int, step: str, message: str):
                event_data = json.dumps({'progress': progress, 'step': step, 'message': message})
                logger.info(f"[PROGRESS] {progress}% - {step}: {message}")
                progress_events.append(f"data: {event_data}\n\n")

            # Processar documento com callback
            resultado = await workflow_service.processar_documento_completo(
                arquivo,
                exames_obrigatorios_list,
                progress_callback=progress_callback
            )

            # Yield todos os eventos coletados
            for event in progress_events:
                yield event
                await asyncio.sleep(0.01)

            # Enviar resultado final
            yield f"data: {json.dumps({'progress': 100, 'step': 'concluido', 'message': 'Processamento concluído!', 'resultado': resultado})}\n\n"
            logger.info(f"[REQUEST-STREAM] Processamento concluído para: {arquivo.filename}")

        except Exception as e:
            logger.exception(f"Erro no processamento stream: {e}")
            error_data = json.dumps({'progress': -1, 'step': 'erro', 'message': f'Erro: {str(e)}'})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Desabilita buffering do nginx
        }
    )

@router.post("/processar-documento-async", summary="Processar documento em background (assíncrono)")
async def processar_documento_async_api(
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True)
):
    """
    Inicia processamento de documento em background e retorna job_id imediatamente.

    Este endpoint evita timeouts de workers ao processar documentos grandes.
    Use GET /v1/jobs/{job_id} para consultar o progresso e resultado.

    Retorna:
    - job_id: ID único do job para consultar status
    - status: "pending" (job criado e aguardando processamento)
    - message: Mensagem informativa
    """
    if not arquivo:
        logger.warning("Arquivo não enviado na requisição async.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo não enviado.")

    # Log de entrada
    file_size = "desconhecido"
    try:
        content = await arquivo.read()
        file_size = f"{len(content) / 1024 / 1024:.2f}MB"
        await arquivo.seek(0)
    except:
        pass

    logger.info(f"[REQUEST-ASYNC] Documento recebido: {arquivo.filename} ({file_size})")

    # Parse exames obrigatórios
    try:
        exames_obrigatorios_list = json.loads(exames_obrigatorios)
        logger.info(f"[REQUEST-ASYNC] Exames obrigatórios: {len(exames_obrigatorios_list)}")
    except json.JSONDecodeError:
        logger.error("Formato inválido para exames_obrigatorios.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exames obrigatórios devem ser um array JSON válido."
        )

    # Criar job
    job_id = await job_manager.create_job(
        job_type="document_processing",
        metadata={
            "filename": arquivo.filename,
            "file_size": file_size,
            "num_exames_obrigatorios": len(exames_obrigatorios_list)
        }
    )

    # Salvar arquivo temporariamente (UploadFile não pode ser passado para background task)
    temp_file_path = None
    try:
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file_path = temp_file.name
            content = await arquivo.read()
            temp_file.write(content)

        logger.info(f"[JOB {job_id}] Arquivo salvo temporariamente: {temp_file_path}")

        # Adicionar task em background
        background_tasks.add_task(
            process_document_background,
            job_id=job_id,
            file_path=temp_file_path,
            filename=arquivo.filename,
            exames_obrigatorios=exames_obrigatorios_list
        )

        logger.info(f"[JOB {job_id}] Task adicionada ao background")

        return {
            "job_id": job_id,
            "status": "pending",
            "message": f"Documento {arquivo.filename} recebido. Processamento iniciado em background.",
            "poll_url": f"/v1/jobs/{job_id}"
        }

    except Exception as e:
        # Cleanup em caso de erro
        if temp_file_path:
            try:
                import os
                os.unlink(temp_file_path)
            except:
                pass
        logger.exception(f"Erro ao iniciar processamento assíncrono: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao iniciar processamento: {str(e)}"
        )


async def process_document_background(
    job_id: str,
    file_path: str,
    filename: str,
    exames_obrigatorios: list[str]
):
    """
    Processa documento em background task.

    Args:
        job_id: ID do job
        file_path: Caminho do arquivo temporário
        filename: Nome original do arquivo
        exames_obrigatorios: Lista de exames obrigatórios
    """
    try:
        logger.info(f"[JOB {job_id}] Iniciando processamento em background")
        await job_manager.start_job(job_id)

        # Criar callback de progresso
        progress_callback = await job_manager.create_progress_callback(job_id)

        # Criar UploadFile a partir do arquivo temporário
        # Nota: FastAPI UploadFile não pode ser recriado facilmente de um path
        # então vamos ler o arquivo e processar diretamente
        from fastapi import UploadFile
        from io import BytesIO

        with open(file_path, "rb") as f:
            file_content = f.read()

        # Criar UploadFile fake
        upload_file = UploadFile(
            filename=filename,
            file=BytesIO(file_content)
        )

        # Processar documento
        resultado = await workflow_service.processar_documento_completo(
            upload_file,
            exames_obrigatorios,
            progress_callback=progress_callback
        )

        # Marcar job como completo
        await job_manager.complete_job(job_id, resultado)
        logger.info(f"[JOB {job_id}] Concluído com sucesso")

    except Exception as e:
        logger.exception(f"[JOB {job_id}] Erro durante processamento: {e}")
        await job_manager.fail_job(job_id, str(e))

    finally:
        # Cleanup: remover arquivo temporário
        try:
            import os
            os.unlink(file_path)
            logger.debug(f"[JOB {job_id}] Arquivo temporário removido: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"[JOB {job_id}] Erro ao remover arquivo temporário: {cleanup_error}")


@router.post("/consultar-brmed", summary="Consultar exames BRMED por CPF")
async def consultar_brmed_api(cpf: str = Body(..., embed=True)):
    if not cpf:
        logger.warning("CPF não fornecido para consulta BRMED.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CPF é obrigatório.")
    try:
        resultado = await brmed_service.consultar_exames_brmed(cpf)
        if "erro" in resultado:
            logger.error(f"Erro ao consultar BRMED para CPF {cpf}: {resultado['erro']}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=resultado["erro"])
        return resultado
    except Exception as e:
        logger.exception(f"Erro inesperado ao consultar BRMED para CPF {cpf}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado ao consultar BRMED.")
 