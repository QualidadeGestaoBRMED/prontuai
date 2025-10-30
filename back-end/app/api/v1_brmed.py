from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body
from fastapi.responses import StreamingResponse
from app.services import workflow_service, brmed_service
import logging
import json
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/processar-documento", summary="Processar documento completo com OCR, BRMED e Validação")
async def processar_documento_completo_api(
    arquivo: UploadFile = File(...),
    exames_obrigatorios: str = Body(..., embed=True) # Recebe como string JSON
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
 