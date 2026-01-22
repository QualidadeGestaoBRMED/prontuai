import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

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
    inicio = re.search(r"4\. Exames / Exams:", conteudo)
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

async def consultar_exames_brmed(cpf: str) -> Dict[str, Any]:
    """Executa automação Playwright para consultar exames obrigatórios na BRMED."""
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
            await page.goto("https://operacoes.grupobrmed.com.br/")
            await page.fill("input[name='username']", os.getenv("BRMED_USERNAME"))
            await page.fill("input[name='password']", os.getenv("BRMED_PASSWORD"))
            await page.click("button[type='submit']")
            await page.wait_for_selector("text=Operações", timeout=30000)
            await page.click("text=Operações")
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.reload()
            await page.wait_for_timeout(2000)
            await page.evaluate("document.querySelector('#radio_cpf').click()")
            await page.wait_for_timeout(1000)
            logger.info("Autenticação e seleção de CPF concluídos.")

            # --- consulta pelo CPF ---
            # Formatar CPF: 01792655398 -> 017.926.553-98
            cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "")
            cpf_formatado = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:11]}"

            logger.info(f"Consultando CPF: {cpf} (formatado: {cpf_formatado})")

            # Limpar o campo antes de digitar
            await page.click("input[type='text']")
            await page.fill("input[type='text']", "")  # Limpar campo
            await page.type("input[type='text']", cpf_formatado, delay=50)

            await page.locator("input[type='submit'].button-bold")\
                .scroll_into_view_if_needed()
            await page.click("input[type='submit'].button-bold", force=True)
            await page.wait_for_load_state("networkidle", timeout=30000)
            logger.info("Consulta de CPF realizada.")

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
                    raise RuntimeError(f"CPF {cpf} consultado mas nenhum paciente encontrado na tabela. Possível CPF inválido ou sem cadastro.")
            else:
                # Capturar conteúdo da página para debug
                page_content = await page.content()
                logger.warning(f"Tabela de resultados não encontrada. Possível mensagem de erro. Conteúdo: {page_content[:1000]}")
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
            
            return dados_filtrados
        except Exception as e:
            logger.error(f"Erro na automação Playwright: {e}")
            return {"erro": f"Erro na automação: {e}"}
        finally:
            if browser:
                await browser.close()
                logger.info("Navegador Playwright fechado.") 
