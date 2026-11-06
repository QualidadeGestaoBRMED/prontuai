"""
Exame de laboratório com coleta muito anterior ao ASO: aviso no exame e rejeição pela IA.

O erro relatado pela operação: a clínica anexa exame do ano anterior e a IA aprova,
porque a comparação olha só o nome do exame, e a checklist de campos só diz se existe
alguma data no documento.

O chamador grava `data_antiga` no item e, com `REJEITA`, a IA rejeita o documento
(decisão de 05/11/2026, STC-991): coleta 180 dias ou mais antes do ASO. Há exame antigo
aceito de propósito, e é o revisor quem libera, com o motivo externo "cliente autorizou".
Não muda faltantes nem confiança. Não chama API e não envia dado a ninguém; roda sobre o
markdown local.

Por que 180: na cópia de produção de 03/11, dos 4.553 documentos com coleta lida, 99%
têm a coleta até 16 dias antes do ASO, 17 ficam entre 31 e 102 dias, nenhum entre 103 e
316, e 5 entre 317 e 371. Qualquer corte entre 103 e 316 separa os mesmos 5.

Só olha o exame com resultado no PDF (`evidencia == "com_resultado"`) e só a data com
o rótulo "coleta": data solta é frágil, o histórico de resultados do laudo traz anos
anteriores na mesma página e o OCR erra dígito. Havendo mais de um laudo do exame, vale
a coleta mais recente: um laudo novo no PDF basta para não avisar.

Medido por replay no texto gravado dos envios desde 14/09/2026 (cópia de produção de
03/11): ver os números em `tests/test_data_exame.py`.
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from typing import Any, Optional

from app.services import evidencia_laboratorio

# Desliga o aviso sem deploy de código: DATA_EXAME_AVISO=false.
HABILITADA = os.getenv("DATA_EXAME_AVISO", "true").strip().lower() not in ("0", "false", "nao", "no")
# Mantém o aviso e volta a só avisar, sem rejeitar: DATA_EXAME_REJEITA=false.
REJEITA = os.getenv("DATA_EXAME_REJEITA", "true").strip().lower() not in ("0", "false", "nao", "no")

try:
    LIMITE_DIAS = int(os.getenv("DATA_EXAME_LIMITE_DIAS", "180"))
except ValueError:
    LIMITE_DIAS = 180

# Mais velho que isso é data de outra coisa mal associada ao rótulo, não coleta.
MAX_IDADE = timedelta(days=5 * 365)

REFERENCIA_ASO = "aso"
REFERENCIA_PROCESSAMENTO = "processamento"

_PAGINA = re.compile(r"<!--\s*pagina\s+\d+\s*-->")
_DATA = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b"
# O rótulo e a data podem vir separados por "Data:" ou por coluna de tabela do OCR.
# A coluna seguinte pode ser a de nascimento: a data dela não é a da coleta.
_COLETA = re.compile(r"\bCOLET(?:A|ADO|ADA)\b((?:(?!NASC)[^0-9]){0,25})" + _DATA)
_DATA_SOLTA = re.compile(r"(?<![\d/.-])" + _DATA)
_ASO = re.compile(r"\bATESTADO\s+DE\s+SAUDE\s+OCUPACIONAL\b|\bA\.?S\.?O\.?\b")
_LINHA_NAO_E_DO_ASO = re.compile(r"NASC|VALIDADE|ADMISS")


def _sem_acento(texto: str) -> str:
    """Maiúsculo e sem acento, mantendo a pontuação de que as datas dependem."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).upper()


def _data(dia: str, mes: str, ano: str) -> Optional[date]:
    numero = int(ano)
    try:
        return date(numero + 2000 if numero < 100 else numero, int(mes), int(dia))
    except ValueError:
        return None


def _paginas(markdown: str) -> list[str]:
    """As páginas do markdown; sem marcador, o documento inteiro é uma página só."""
    return [p for p in _PAGINA.split(markdown) if p.strip()]


def coletas(texto: str, hoje: date) -> list[date]:
    """As datas de coleta plausíveis do texto: nem futuras, nem velhas demais."""
    normalizado = _sem_acento(texto)
    datas = (_data(*m.group(2, 3, 4)) for m in _COLETA.finditer(normalizado))
    return [d for d in datas if d and hoje - MAX_IDADE <= d <= hoje]


def data_do_aso(markdown: str, hoje: date) -> Optional[date]:
    """
    A data mais recente da página do ASO, sem contar nascimento e validade.

    O ASO também imprime a data de cada exame da lista, sempre iguais ou anteriores à
    dele; por isso a mais recente. Em dúvida o erro é para menos: uma data do ASO mal
    lida como antiga encurta a diferença e deixa de avisar, em vez de avisar à toa.
    """
    candidatas: list[date] = []
    for pagina in _paginas(markdown):
        normalizada = _sem_acento(pagina)
        if not _ASO.search(normalizada):
            continue
        for linha in normalizada.splitlines():
            if _LINHA_NAO_E_DO_ASO.search(linha):
                continue
            for m in _DATA_SOLTA.finditer(linha):
                data = _data(*m.groups())
                if data and hoje - MAX_IDADE <= data <= hoje:
                    candidatas.append(data)
        if candidatas:
            break  # a primeira página do ASO; as seguintes podem ser laudos que o citam
    return max(candidatas) if candidatas else None


def coleta_do_exame(
    paginas: list[tuple[str, "evidencia_laboratorio.MarkdownIndexado"]],
    exame: str,
    termos: Iterable[str],
    hoje: date,
) -> Optional[date]:
    """Coleta mais recente entre as páginas onde o exame tem resultado."""
    achadas: list[date] = []
    for texto, indexada in paginas:
        evidencia, _linha = evidencia_laboratorio.avaliar(indexada, exame, termos)
        if evidencia == evidencia_laboratorio.COM_RESULTADO:
            achadas.extend(coletas(texto, hoje))
    return max(achadas) if achadas else None


def anotar_comparativo(
    comparativo: list[dict[str, Any]],
    markdown: str,
    sinonimos_de: Callable[[str], Iterable[str]] = lambda _chave: (),
    hoje: Optional[date] = None,
    limite_dias: Optional[int] = None,
) -> list[str]:
    """
    Grava `data_antiga` nos exames com coleta antiga, no próprio dict, e devolve os
    nomes. Precisa rodar depois de `evidencia_laboratorio.anotar_comparativo`, que diz
    quais exames têm resultado no PDF. `hoje` e `limite_dias` existem para o replay.
    """
    candidatos = [
        item for item in comparativo
        if item.get("status") == "encontrado"
        and item.get("evidencia") == evidencia_laboratorio.COM_RESULTADO
        and item.get("exame")
    ]
    if not candidatos or not markdown:
        return []
    hoje = hoje or date.today()
    limite = LIMITE_DIAS if limite_dias is None else limite_dias
    aso = data_do_aso(markdown, hoje)
    referencia = aso or hoje
    paginas = [(p, evidencia_laboratorio.MarkdownIndexado(p)) for p in _paginas(markdown)]

    antigos: list[str] = []
    for item in candidatos:
        termos = evidencia_laboratorio.termos_do_item(item["exame"], sinonimos_de)
        coleta = coleta_do_exame(paginas, item["exame"], termos, hoje)
        if coleta is None:
            continue
        dias = (referencia - coleta).days
        if dias >= limite:
            item["data_antiga"] = {
                "data_exame": coleta.strftime("%d/%m/%Y"),
                "data_referencia": referencia.strftime("%d/%m/%Y"),
                "referencia": REFERENCIA_ASO if aso else REFERENCIA_PROCESSAMENTO,
                "dias": dias,
            }
            antigos.append(item["exame"])
    return antigos


def motivo_rejeicao(comparativo: Iterable[dict[str, Any]]) -> str:
    """A frase que vai na mensagem da IA. Só nome do exame e dias: a data é do exame,
    não identifica o paciente, mas a mensagem também vai ao log."""
    partes = [
        f"{item['exame']} ({item['data_antiga']['dias']} dias)"
        for item in comparativo
        if isinstance(item, dict) and item.get("data_antiga")
    ]
    if not partes:
        return ""
    rotulo = "Exame coletado" if len(partes) == 1 else "Exames coletados"
    # Sem a data do ASO, a conta foi feita contra a data da análise.
    sem_aso = any(
        item.get("data_antiga", {}).get("referencia") == REFERENCIA_PROCESSAMENTO
        for item in comparativo
        if isinstance(item, dict)
    )
    referencia = "antes da análise do documento" if sem_aso else "antes do ASO"
    return f"{rotulo} {LIMITE_DIAS} dias ou mais {referencia}: {', '.join(partes)}."
