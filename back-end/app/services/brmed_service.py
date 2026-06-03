import os
import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, Any, Optional
import logging
import time
import fcntl
from contextlib import contextmanager
import asyncio
from concurrent.futures import ThreadPoolExecutor
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Pool dedicado para RPA (Playwright)
_RPA_EXECUTOR: ThreadPoolExecutor | None = None
if getattr(settings, "BRMED_RPA_WORKERS", 0) > 0:
    _RPA_EXECUTOR = ThreadPoolExecutor(
        max_workers=settings.BRMED_RPA_WORKERS,
        thread_name_prefix="brmed-rpa"
    )

_RPA_SEMAPHORE = None
if getattr(settings, "BRMED_RPA_CONCURRENCY", 0) > 0:
    _RPA_SEMAPHORE = asyncio.Semaphore(settings.BRMED_RPA_CONCURRENCY)

_RPA_LOCK_FILE = os.getenv("BRMED_RPA_LOCK_FILE", "/tmp/brmed_rpa.lock")

@contextmanager
def _global_rpa_lock() -> Any:
    fd = os.open(_RPA_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _digits_only(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_cpf(cpf: Optional[str]) -> Optional[str]:
    if not cpf:
        return None
    digits = _digits_only(cpf)
    return digits if len(digits) == 11 else None


def _normalize_cnpj(cnpj: Optional[str]) -> Optional[str]:
    if not cnpj:
        return None
    digits = _digits_only(cnpj)
    return digits if len(digits) == 14 else None


def _normalize_passport(passaporte: Optional[str]) -> Optional[str]:
    if not passaporte:
        return None
    clean = re.sub(r"\s+", "", passaporte).upper()
    if not clean:
        return None
    if not re.fullmatch(r"[A-Z0-9]+", clean):
        return None
    return clean


def _parse_response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, str):
            return payload
        if isinstance(payload, list) and payload:
            return str(payload[0])
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                return str(detail[0])
            message = payload.get("message")
            if isinstance(message, str):
                return message
            if payload:
                return str(payload)
    except Exception:
        pass
    return (response.text or "").strip() or f"HTTP {response.status_code}"


def _parse_br_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except Exception:
        return None


def _select_latest_pedido(pedidos: list[dict]) -> Optional[dict]:
    if not pedidos:
        return None

    latest_with_date: Optional[dict] = None
    latest_date: Optional[datetime] = None
    for pedido in pedidos:
        data = _parse_br_date((pedido or {}).get("data_previsao_liberacao"))
        if not data:
            continue
        # Em empate de data, mantém o último na ordem de retorno.
        if latest_date is None or data >= latest_date:
            latest_date = data
            latest_with_date = pedido

    if latest_with_date is not None:
        return latest_with_date
    return pedidos[-1]


def _build_api_success_payload(
    payload: dict,
    cpf: Optional[str],
    passaporte: Optional[str],
    cnpj: str,
) -> Dict[str, Any]:
    pedidos = payload.get("pedidos_exames") or []
    pedidos = [p for p in pedidos if isinstance(p, dict)]
    pedido = _select_latest_pedido(pedidos)
    exames = (pedido or {}).get("exames") or []
    exames_nomes = []
    for exame in exames:
        if isinstance(exame, dict):
            nome = (exame.get("nome") or "").strip()
            if nome:
                exames_nomes.append(nome)
        elif isinstance(exame, str) and exame.strip():
            exames_nomes.append(exame.strip())

    tipo_identificador = "cpf" if cpf else "passaporte"
    identificador = cpf or passaporte

    return {
        "nome": payload.get("nome"),
        "id": payload.get("id"),
        "exames": exames_nomes,
        "source": "prontuai_api",
        "tipo_identificador_consulta": tipo_identificador,
        "identificador_consulta": identificador,
        "cpf_processado": cpf,
        "passaporte_processado": passaporte,
        "cnpj_processado": cnpj,
        "pedido_exame_id": (pedido or {}).get("pedido_exame_id"),
        "tipo_pedido_exame": (pedido or {}).get("tipo_pedido_exame"),
        "data_previsao_liberacao": (pedido or {}).get("data_previsao_liberacao"),
        "atendimento_realizado_em": (pedido or {}).get("atendimento_realizado_em"),
    }

# Função para extrair nome e exames do conteúdo da página
def extract_nome_e_exames(conteudo: str) -> Dict[str, Any]:
    logger.info(f"Conteúdo recebido para extração: {conteudo[:500]}...") # Registra os primeiros 500 caracteres
    # Extrai o nome (até o fim da linha)
    nome_match = re.search(r"Nome / Name:\s*(.*?)(?:Identidade / ID Number:|\n)", conteudo)
    logger.info(f"Nome match object: {nome_match}")
    nome = nome_match.group(1).strip() if nome_match else None
    logger.info(f"Nome extraído: {nome}")
    if nome:
        nome = nome.split("\t")[0].split("  ")[0].strip()

    # Extrai a seção 4 (Exames) até o final do texto
    exames_texto = ""
    inicio = re.search(r"4\.\s*Exames(?:\s*/\s*Exams)?[:]?", conteudo)
    if inicio:
        start_idx = inicio.start()
        fim = re.search(r"\n\s*(5\.|6\.)\s", conteudo[start_idx:])
        if fim:
            end_idx = start_idx + fim.start()
            exames_texto = conteudo[start_idx:end_idx].strip()
        else:
            exames_texto = conteudo[start_idx:].strip()
    logger.info(f"Exames texto extraído: {exames_texto[:500]}...")

    # Extrai todos os grupos de palavras (exames) em cada linha, ignora linha de seção
    exames = []
    for linha in exames_texto.splitlines():
        linha_raw = linha.strip()
        linha_limpa = linha_raw.replace('\t', ' ')
        logger.info(f"Linha limpa para extração de exames: {linha_limpa}")
        if not linha_limpa or linha_limpa.lower().startswith(("4. exames", "4.1")) or linha_limpa.lower().startswith("obrigatório") or re.match(r"^\d+\)", linha_limpa) or "voltar imprimir" in linha_limpa.lower() or "copyright" in linha_limpa.lower():
            continue
        partes = [p.strip() for p in re.split(r"\t+", linha_raw) if p.strip()]
        if len(partes) <= 1:
            partes = [p.strip() for p in re.split(r"\s{2,}", linha_limpa) if p.strip()]
        for parte in partes:
            # Regex para capturar o nome do exame em português antes do '/' ou do final da linha
            # Permite asteriscos (*) que indicam obrigatoriedade e caracteres comuns em exames
            match = re.match(r"^([A-ZÀ-Úa-zà-úÇçÊêÍíÓóÕõÂâÊêÔôÃãÕõÇç0-9\s\*\-()/]+?)(?:\s*/.*)?$", parte)
            if match:
                exame = match.group(1).strip()
                # Remover asterisco no final (indica obrigatoriedade)
                exame = exame.rstrip('*').strip()
                if exame and exame not in exames:
                    exames.append(exame)
    logger.info(f"Exames extraídos: {exames}")
    return {"nome": nome, "exames": exames}

# Função principal de automação RPA

async def _consultar_exames_brmed_async(cpf: str) -> Dict[str, Any]:
    """Executa automação Playwright para consultar exames obrigatórios na BRMED."""
    start_total = time.perf_counter()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  # Modo sem interface gráfica para melhor desempenho
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        # Configura tempo limite padrão para evitar travamentos
        ctx.set_default_timeout(60000)  # 60 segundos
        page = await ctx.new_page()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"resultados/guia_{cpf}_{ts}.json"
        debug_fn = f"resultados/debug_conteudo_{cpf}_{ts}.txt"

        try:
            logger.info("Iniciando automação Playwright...")
            # --- autenticação ---
            logger.info("Navegando para a página de login...")
            t_login = time.perf_counter()
            await page.goto("https://operacoes.grupobrmed.com.br/")
            await page.fill("input[name='username']", os.getenv("BRMED_USERNAME"))
            await page.fill("input[name='password']", os.getenv("BRMED_PASSWORD"))
            await page.click("button[type='submit']")
            await page.wait_for_selector("text=Operações", timeout=30000)
            await page.click("text=Operações")
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.reload()
            await page.wait_for_timeout(2000)
            await page.wait_for_selector("#radio_cpf", timeout=30000)
            try:
                await page.check("#radio_cpf", force=True)
            except Exception:
                await page.click("#radio_cpf", force=True)
            # Garantir que o radio de CPF foi selecionado
            try:
                await page.wait_for_function(
                    "document.querySelector('#radio_cpf') && document.querySelector('#radio_cpf').checked === true",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                logger.warning("Radio CPF não ficou selecionado; seguindo mesmo assim.")
            logger.info(f"Autenticação e seleção de CPF concluídos em {time.perf_counter() - t_login:.2f}s.")

            # --- consulta pelo CPF ---
            # Formatar CPF: 01792655398 -> 017.926.553-98
            cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "")
            cpf_formatado = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:11]}"

            logger.info(f"Consultando CPF: {cpf} (formatado: {cpf_formatado})")
            t_consulta = time.perf_counter()

            # Limpar o campo antes de digitar
            await page.click("#search_field")
            await page.fill("#search_field", "")  # Limpar campo
            await page.type("#search_field", cpf_formatado, delay=50)

            # Garantir radio CPF + submit via JS (evita reset para "Nome")
            await page.evaluate(
                """(cpf) => {
                    const cpfRadio = document.querySelector('#radio_cpf');
                    const nomeRadio = document.querySelector('#radio_nome');
                    if (cpfRadio) cpfRadio.checked = true;
                    if (nomeRadio) nomeRadio.checked = false;
                    const field = document.querySelector('#search_field');
                    if (field) {
                        field.value = cpf;
                        field.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    const form = document.querySelector('form[action="/busca"]');
                    if (form) form.submit();
                }""",
                cpf_formatado,
            )
            await page.wait_for_load_state("networkidle", timeout=60000)
            await page.wait_for_timeout(1500)
            try:
                await page.wait_for_selector("table.tabledata", timeout=60000)
            except PlaywrightTimeoutError:
                logger.warning("Tabela de resultados não apareceu em até 60s. Seguindo com debug da página.")
            logger.info(f"Consulta de CPF realizada em {time.perf_counter() - t_consulta:.2f}s.")

            # Debug: verificar se a tabela com resultados existe
            table_exists = await page.locator("table.tabledata").count()
            logger.info(f"Tabelas com classe 'tabledata' encontradas: {table_exists}")

            if table_exists > 0:
                # Debug: contar links de paciente na tabela
                patient_links = await page.locator("table.tabledata a[href*='/paciente/']").count()
                logger.info(f"Links de paciente encontrados: {patient_links}")

                if patient_links == 0:
                    # Capturar HTML da tabela para debug
                    table_html = await page.locator("table.tabledata").inner_html()
                    logger.warning(f"Nenhum link de paciente encontrado. HTML da tabela: {table_html[:500]}")
                    try:
                        os.makedirs("resultados", exist_ok=True)
                        debug_html = f"resultados/debug_table_{cpf}_{ts}.html"
                        with open(debug_html, "w", encoding="utf-8") as f:
                            f.write(await page.content())
                        debug_png = f"resultados/debug_table_{cpf}_{ts}.png"
                        await page.screenshot(path=debug_png, full_page=True)
                        logger.info(f"HTML/screenshot salvos para debug: {debug_html}, {debug_png}")
                    except Exception as debug_err:
                        logger.warning(f"Falha ao salvar debug da tabela vazia: {debug_err}")
                    raise RuntimeError(f"CPF {cpf} consultado mas nenhum paciente encontrado na tabela. Possível CPF inválido ou sem cadastro.")
            else:
                # Capturar conteúdo da página para debug
                page_content = await page.content()
                logger.warning(f"Tabela de resultados não encontrada. Possível mensagem de erro. Conteúdo: {page_content[:1000]}")
                try:
                    os.makedirs("resultados", exist_ok=True)
                    debug_html = f"resultados/debug_page_{cpf}_{ts}.html"
                    with open(debug_html, "w", encoding="utf-8") as f:
                        f.write(page_content)
                    debug_png = f"resultados/debug_page_{cpf}_{ts}.png"
                    await page.screenshot(path=debug_png, full_page=True)
                    logger.info(f"HTML/screenshot salvos para debug: {debug_html}, {debug_png}")
                except Exception as debug_err:
                    logger.warning(f"Falha ao salvar debug da página sem tabela: {debug_err}")
                raise RuntimeError(f"CPF {cpf}: tabela de resultados não encontrada. Verifique se o CPF existe no sistema.")

            await page.click("table.tabledata a[href*='/paciente/']")
            await page.wait_for_selector("a.close", timeout=30000)
            await page.click("a.close")
            await page.wait_for_selector("text=Guia de Encaminhamento", timeout=30000)
            logger.info("Clicando em 'Guia de Encaminhamento'...")
            async with ctx.expect_page() as new_p_info:
                await page.click("text=Guia de Encaminhamento")
            new_page = await new_p_info.value
            if not new_page:
                logger.error("Nova página não foi aberta ou foi fechada imediatamente.")
                raise Exception("Nova página não disponível.")
            await new_page.wait_for_load_state("networkidle")
            await new_page.wait_for_timeout(3000) # Adiciona um pequeno atraso para garantir que a página carregue completamente
            logger.info("Nova página da guia carregada e aguardando.")

            conteudo = await new_page.evaluate("() => document.body.innerText")

            # Salvar o conteúdo bruto para depuração
            os.makedirs("resultados", exist_ok=True)
            with open(debug_fn, "w", encoding="utf-8") as f:
                f.write(conteudo)
            logger.info(f"Conteúdo bruto da página salvo em: {debug_fn}")

            dados_filtrados = extract_nome_e_exames(conteudo)
            # Salvar resultado
            with open(fn, "w", encoding="utf-8") as f:
                import json
                json.dump(dados_filtrados, f, ensure_ascii=False, indent=4)
            logger.info(f"Resultado da extração salvo em: {fn}")
            
            return {
                **dados_filtrados,
                "source": "rpa",
                "tipo_identificador_consulta": "cpf",
                "identificador_consulta": cpf,
                "cpf_processado": _normalize_cpf(cpf),
                "passaporte_processado": None,
                "cnpj_processado": None,
            }
        except Exception as e:
            logger.error(f"Erro na automação Playwright: {e}")
            return {"erro": f"Erro na automação: {e}", "error_type": "technical", "source": "rpa"}
        finally:
            if browser:
                await browser.close()
                logger.info("Navegador Playwright fechado.")
            logger.info(f"Consulta BRMED finalizada em {time.perf_counter() - start_total:.2f}s.")


def _consultar_exames_brmed_thread(cpf: str) -> Dict[str, Any]:
    """Executa o RPA em thread dedicada com loop próprio."""
    with _global_rpa_lock():
        return asyncio.run(_consultar_exames_brmed_async(cpf))


async def consultar_exames_brmed(cpf: str) -> Dict[str, Any]:
    """
    Consulta BRMED isolando o RPA em pool de threads quando configurado.
    Isso evita bloquear o event loop e melhora a capacidade de resposta.
    """
    async def _run() -> Dict[str, Any]:
        if _RPA_EXECUTOR is None:
            return await _consultar_exames_brmed_async(cpf)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_RPA_EXECUTOR, _consultar_exames_brmed_thread, cpf)

    if _RPA_SEMAPHORE is None:
        return await _run()
    async with _RPA_SEMAPHORE:
        return await _run()


async def consultar_exames_prontuai_api(
    cpf: Optional[str] = None,
    passaporte: Optional[str] = None,
    cnpj: Optional[str] = None,
) -> Dict[str, Any]:
    cpf_norm = _normalize_cpf(cpf)
    passaporte_norm = _normalize_passport(passaporte)
    cnpj_norm = _normalize_cnpj(cnpj)

    if cpf and not cpf_norm:
        return {"erro": "cpf deve conter somente números e 11 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if cnpj and not cnpj_norm:
        return {"erro": "cnpj deve conter somente números e 14 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if passaporte and not passaporte_norm:
        return {"erro": "passport deve conter apenas letras e números", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if cpf_norm and passaporte_norm:
        return {"erro": "Informe apenas um: cpf ou passaporte", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if not cpf_norm and not passaporte_norm:
        return {"erro": "cpf ou passaporte é obrigatório", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}
    if not cnpj_norm:
        return {"erro": "cnpj é obrigatório e deve ter 14 dígitos", "error_type": "semantic", "source": "prontuai_api", "http_status": 400}

    if not settings.PRONTUAI_SERVICE_TOKEN or not settings.PRONTUAI_CLIENT_NAME:
        return {
            "erro": "Integração com ProntuAI API não configurada (Service-Token/Client-Name).",
            "error_type": "technical",
            "source": "prontuai_api",
            "http_status": None,
        }

    params: Dict[str, str] = {"cnpj": cnpj_norm}
    if cpf_norm:
        params["cpf"] = cpf_norm
    else:
        params["passport"] = passaporte_norm  # contrato externo usa "passport"

    endpoint = f"{settings.PRONTUAI_API_BASE_URL.rstrip('/')}/api/prontuai/patients_exams/"
    headers = {
        "Service-Token": settings.PRONTUAI_SERVICE_TOKEN,
        "Client-Name": settings.PRONTUAI_CLIENT_NAME,
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.PRONTUAI_API_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, params=params, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        elapsed = time.perf_counter() - started
        logger.warning(
            "[PRONTUAI-API] request.failed source=prontuai_api type=technical elapsed=%.3fs cpf=%s passport=%s cnpj=%s error=%s",
            elapsed,
            "***" if cpf_norm else None,
            "***" if passaporte_norm else None,
            cnpj_norm,
            exc,
        )
        return {"erro": f"Falha de comunicação com API externa: {exc}", "error_type": "technical", "source": "prontuai_api", "http_status": None}

    elapsed = time.perf_counter() - started
    logger.info(
        "[PRONTUAI-API] request.done source=prontuai_api status=%s elapsed=%.3fs cnpj=%s has_cpf=%s has_passport=%s",
        response.status_code,
        elapsed,
        cnpj_norm,
        bool(cpf_norm),
        bool(passaporte_norm),
    )

    if response.status_code == 200:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                return {
                    "erro": "Resposta inválida da API externa.",
                    "error_type": "technical",
                    "source": "prontuai_api",
                    "http_status": 200,
                }
            return _build_api_success_payload(payload, cpf_norm, passaporte_norm, cnpj_norm)
        except Exception as exc:
            return {
                "erro": f"Falha ao interpretar resposta da API externa: {exc}",
                "error_type": "technical",
                "source": "prontuai_api",
                "http_status": 200,
            }

    error_msg = _parse_response_error(response)
    if response.status_code in (400, 404):
        return {
            "erro": error_msg,
            "error_type": "semantic",
            "source": "prontuai_api",
            "http_status": response.status_code,
        }

    return {
        "erro": error_msg,
        "error_type": "technical",
        "source": "prontuai_api",
        "http_status": response.status_code,
    }


async def consultar_exames_prontuai(
    cpf: Optional[str] = None,
    passaporte: Optional[str] = None,
    cnpj: Optional[str] = None,
    allow_rpa_fallback: bool = True,
) -> Dict[str, Any]:
    api_result = await consultar_exames_prontuai_api(cpf=cpf, passaporte=passaporte, cnpj=cnpj)
    if "erro" not in api_result:
        return api_result

    if api_result.get("error_type") != "technical":
        return api_result

    cpf_norm = _normalize_cpf(cpf)
    if not allow_rpa_fallback or not cpf_norm:
        return api_result

    rpa_result = await consultar_exames_brmed(cpf_norm)
    if "erro" in rpa_result:
        return {
            **api_result,
            "fallback_attempted": True,
            "fallback_error": rpa_result.get("erro"),
        }

    return {
        **rpa_result,
        "source": "rpa_fallback",
        "fallback_from": "prontuai_api",
        "fallback_reason": api_result.get("erro"),
        "tipo_identificador_consulta": "cpf",
        "identificador_consulta": cpf_norm,
        "cpf_processado": cpf_norm,
        "passaporte_processado": _normalize_passport(passaporte),
        "cnpj_processado": _normalize_cnpj(cnpj),
    }
