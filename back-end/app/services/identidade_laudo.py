"""
Dados de outra pessoa no documento: um bloco "Nome / Paciente" + CPF que não é
do paciente do pedido (STC-947).

O erro medido: a clínica anexa ao prontuário um laudo de outro colaborador (o
ECG, a espirometria, às vezes o ASO inteiro) e a IA dá o exame como encontrado.
A checagem antiga não via: procurava o nome do paciente em qualquer linha do
PDF, e ele aparece no ASO e na ficha de 3 a 46 vezes por documento.

O que esta regra procura é a forma como laudo identifica o paciente: um rótulo
de nome ("Nome:", "Paciente:", "Nome / Name:") e um CPF válido a poucas linhas
um do outro, na mesma página. Acusa quando o CPF não é o do paciente E o nome
ao lado também não é — os dois juntos, porque cada um sozinho falha:

  - Só pelo CPF: a maior parte dos CPFs de terceiros num prontuário é de
    profissional (assinatura digital "ASSINADO POR FULANO (CPF)", médico
    examinador ao lado do CRM, solicitante). Esses não têm rótulo de paciente.
  - Só pelo nome: o OCR corrompe letras do nome, e o replay de out/2026 deu
    saldo de -331 documentos com essa versão.
  - O nome confirma o CPF: CPF diferente com o MESMO nome é o OCR trocando um
    dígito ou o BRNET com CPF errado, não outra pessoa.

Abaixo desse aviso há um mais fraco, só pelo nome (`pessoas_no_documento`):
o rótulo de paciente com nome claramente diferente, sem CPF de terceiro por
perto, e que passa pelos cortes de `_nome_de_outra_pessoa` (grafia, profissional,
coletor, OCR inventando, empresa, vocabulário de nomes). Pega laudo de outro
colaborador que não traz CPF; a tela o mostra como "Nome diferente no laudo",
para o revisor saber que é aviso de outra natureza.

É só um alerta. Não muda status, faltantes nem validation_status: o chamador
grava as ocorrências no payload para a tela do revisor. Não chama API e não
envia dado a ninguém; roda sobre o markdown local.

Medido por replay no texto gravado da cópia de produção de 23/10/2026 (5.175
documentos com texto): acusa 4 dos 19 documentos em que o revisor escreveu
"outro colaborador"/"outra pessoa", e 10 dos 4.209 aprovados. Os 10 aprovados
são bloco de identificação de outra pessoa de fato (conferido no texto e, num
deles, no PDF: acuidade visual de outro trabalhador, de outra empresa) — erro
de revisão, não da regra. Nenhuma das outras 852 rejeições é acusada. Os 15
casos não pegos não têm CPF de terceiro no texto. A variante só pelo nome
rotulado pegaria 9 dos 19, mas acusaria 421 aprovados (10%).
"""
from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Callable, Collection, Iterable, Optional

from app.core.pii import mask_cpf, mask_name
from app.services.ocr_service import _digits_only, _is_valid_cpf
from app.services.patient_name_extractor import _clean_candidate

# Desliga o alerta sem deploy de código: IDENTIDADE_LAUDO=false.
HABILITADA = os.getenv("IDENTIDADE_LAUDO", "true").strip().lower() not in ("0", "false", "nao", "no")

# Linhas antes e depois do CPF onde o rótulo de nome é procurado. Laudo põe
# "Paciente:" e "CPF:" na mesma linha ou em linhas vizinhas; o OCR intercala
# linhas vazias (que não contam) e às vezes "Data de nascimento" no meio.
JANELA_LINHAS = 3

_CPF = re.compile(r"\b\d{3}[\.\s-]{0,5}\d{3}[\.\s-]{0,5}\d{3}[\.\s-]{0,5}\d{2}\b")
_PAGINA = re.compile(r"<!--\s*pagina\s+(\d+)\s*-->")

# Rótulo de quem é examinado. "Nome do médico:" não casa: depois de "nome" só
# vêm as variações do próprio rótulo, e então os dois-pontos.
_ROTULO_NOME = re.compile(
    r"(?i)^[\s#*>|-]*"
    r"(?:nome(?:\s+do\s+paciente|\s+completo)?(?:\s*/\s*(?:full\s+)?name)?"
    r"|paciente|patient(?:\s+name)?|colaborador[a]?|funcion[aá]ri[oa]|trabalhador[a]?)"
    r"\s*[:\-]\s*(?P<valor>\S.*)$"
)
# CPF de quem atende, assina ou pede o exame, e não de quem é examinado.
_PROFISSIONAL = re.compile(
    r"(?i)\b(?:CRM|CRO|CRF|CRFA|COREN|CRP|CRBM|CREFITO|CRN|RQE|M[ÉE]DIC[OA]|DRA?\b\.?|"
    r"EXAMINADOR[A]?|RESPONS[ÁA]VEL|SOLICITANTE|ASSINAD[OA]|ASSINATURA|T[ÉE]CNIC[OA]|"
    r"FONOAUDI[ÓO]LOG[OA]|PSIC[ÓO]LOG[OA]|ENFERMEIR[OA]|BIOM[ÉE]DIC[OA]|FARMAC[ÊE]UTIC[OA]|"
    r"CERTIFICADO)"
)
_LINHA_CNPJ_OU_PASSAPORTE = re.compile(r"(?i)CNPJ|PASSAPORTE|PASSPORT")
# O CPF de paciente vem rotulado ("CPF:", "Identificação:") ou na própria linha
# do nome. Sem rótulo, o número colado num nome ("FULANO DE TAL:12345678900") é
# o titular do certificado ICP-Brasil que assinou o laudo — o médico.
_ROTULO_CPF = re.compile(r"(?i)\bC\.?P\.?F\b|IDENTIFICA[CÇ][AÃ]O|DOCUMENTO")

# Linhas com texto olhadas acima e abaixo do bloco de identificação em busca do
# título do laudo. Nos documentos de out/2026 o título fica a até 8 linhas.
ALCANCE_EXAME = 10
# O ASO identifica o paciente logo abaixo do título, e o exame dele é o clínico.
_CLINICO = re.compile(r"\bCLINICO\b")
_TITULO_ASO = "ATESTADO DE SAUDE OCUPACIONAL"

# Força do aviso: nome e CPF de outra pessoa, ou só o nome (ver `pessoas_no_documento`).
NOME_E_CPF = "nome_e_cpf"
SO_NOME = "so_nome"

# Cortes do aviso só pelo nome (ver `_nome_de_outra_pessoa`).
# Abaixo disso o nome não "soa" como o do paciente: o OCR estraga o nome escrito
# à mão do próprio paciente e deixa a grafia parecida (0,5 a 0,9); o de outra
# pessoa fica perto de 0,3.
LIMIAR_SEMELHANCA = 0.45
# Fração mínima das palavras do nome que precisa estar no vocabulário de nomes.
FRACAO_NOMES_CONHECIDOS = 0.5
# Conselho ou assinatura logo abaixo do nome: é o profissional que assina.
_CONSELHO = re.compile(r"(?i)\b(?:CRM|CRO|CRFA|CRF|CRP|COREN|CRBM|CREFITO|CRN|RQE|CRMV)\b|ASSINAD[OA]")
# Formulário de cadeia de custódia do toxicológico: o "Nome:" é do coletor.
_COLETA_TOXICOLOGICO = re.compile(r"(?i)SUPERVISOR DA COLETA|\bCOLLECTION\b|CUST[ÓO]DIA|CUSTODY")
_EMPRESA = re.compile(
    r"(?i)\b(?:LTDA|S\.?A\.?|EIRELI|ME|EPP|MED|SERVI[CÇ]OS|MARITIMA|NAVIO|EMPRESA|CL[IÍ]NICA|HOSPITAL|"
    r"LABORAT[OÓ]RIO)\b|[()/]"
)

_PARTICULAS = {"DA", "DE", "DO", "DAS", "DOS", "E", "DI", "DU"}


# ---------------------------------------------------------------------------
# Mesmo nome, com tolerância ao OCR
# ---------------------------------------------------------------------------

def _tokens(nome: Optional[str]) -> list[str]:
    texto = unicodedata.normalize("NFKD", nome or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    return [t for t in re.findall(r"[A-Z0-9]+", texto) if len(t) > 1 and t not in _PARTICULAS]


def _distancia(a: str, b: str) -> int:
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _token_igual(a: str, b: str) -> bool:
    # Uma letra trocada a cada 5: "J0SE" é JOSE, "ROSANGELA" aceita duas.
    return a == b or _distancia(a, b) <= max(1, min(len(a), len(b)) // 5)


def mesma_pessoa(nome_a: Optional[str], nome_b: Optional[str]) -> bool:
    """
    Os dois nomes podem ser da mesma pessoa, com o OCR no meio. Na dúvida, sim:
    a regra só acusa quando os nomes são claramente de pessoas diferentes.

    - nome sem como comparar (vazio, só partículas): sim;
    - nomes iguais sem os espaços, a menos de erro de OCR ("SILVAJUNIOR"): sim;
    - primeiro nome igual e mais um token igual: sim ("MARIA F SILVA" e
      "MARIA FICTICIA DA SILVA");
    - três quartos dos tokens do nome menor batendo: sim (primeiro nome
      corrompido demais pelo OCR, ou omitido).
    Dois colegas com o mesmo primeiro nome e o mesmo sobrenome passam como a
    mesma pessoa — preço aceito para não acusar erro de OCR.
    """
    ta, tb = _tokens(nome_a), _tokens(nome_b)
    if not ta or not tb:
        return True
    juntos_a, juntos_b = "".join(ta), "".join(tb)
    if _distancia(juntos_a, juntos_b) <= max(1, min(len(juntos_a), len(juntos_b)) // 8):
        return True
    menor, maior = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    casados = sum(1 for t in menor if any(_token_igual(t, u) for u in maior))
    if _token_igual(ta[0], tb[0]) and casados >= 2:
        return True
    if len(menor) == 1:
        return casados == 1
    return casados / len(menor) >= 0.75


# ---------------------------------------------------------------------------
# Blocos de identificação
# ---------------------------------------------------------------------------

def _nome_rotulado(linha: str) -> Optional[str]:
    m = _ROTULO_NOME.match(linha)
    if not m:
        return None
    # A linha do rótulo de quem atende ("Médico: Dr. Fulano") não é de paciente.
    if _PROFISSIONAL.search(linha):
        return None
    return _clean_candidate(m.group("valor"))


def _paginas(linhas: list[str]) -> list[Optional[int]]:
    """Página de cada linha, pelos marcadores do OCR; None antes do primeiro."""
    pagina, saida = None, []
    for linha in linhas:
        m = _PAGINA.search(linha)
        if m:
            pagina = int(m.group(1))
        saida.append(pagina)
    return saida


def chave(cpf: str) -> str:
    """Como a tela e a rota de localização se referem a uma pessoa achada: pelo
    CPF mascarado, o mesmo que o payload guarda."""
    return f"outra_pessoa:{mask_cpf(cpf)}"


def chave_da_pessoa(pessoa: dict) -> str:
    """A chave de `chave`, ou, para quem só tem o nome, o nome mascarado."""
    if pessoa.get("cpf"):
        return chave(pessoa["cpf"])
    return f"nome_diferente:{mask_name(' '.join(_tokens(pessoa['nome'])))}"


def outra_pessoa(
    linhas: Iterable[str],
    cpf_paciente: Optional[str],
    nome_paciente: Optional[str],
    paginas: Optional[list[Optional[int]]] = None,
) -> list[dict]:
    """
    Cada pessoa diferente do paciente identificada no documento, na ordem em que
    aparece: {"nome", "cpf", "linhas": [índices da linha do CPF e da do nome]}.

    `linhas` é o texto linha a linha — do markdown, ou das linhas posicionadas
    do layout na rota de localização, para o clique levar às mesmas linhas.
    `paginas` é a página de cada linha; sem ela, sai dos marcadores do OCR.
    Sem o CPF do paciente a regra não opina: devolve lista vazia.
    """
    linhas = list(linhas)
    cpf_paciente = _digits_only(cpf_paciente)
    if len(cpf_paciente) != 11:
        return []
    if paginas is None:
        paginas = _paginas(linhas)
    # Índices das linhas com texto: a janela conta essas, e não as vazias.
    com_texto = [i for i, linha in enumerate(linhas) if linha.strip() and not _PAGINA.search(linha)]
    posicao = {indice: p for p, indice in enumerate(com_texto)}

    pessoas: dict[str, dict] = {}
    for p, i in enumerate(com_texto):
        linha = linhas[i]
        if _LINHA_CNPJ_OU_PASSAPORTE.search(linha) or _PROFISSIONAL.search(linha):
            continue
        if not _ROTULO_CPF.search(linha) and not _ROTULO_NOME.match(linha):
            continue
        for m in _CPF.finditer(linha):
            cpf = _digits_only(m.group(0))
            if cpf == cpf_paciente or not _is_valid_cpf(cpf):
                continue
            # O rótulo mais perto do CPF, na mesma página: a própria linha
            # primeiro ("Paciente: FULANO  CPF: ..."), depois a vizinhança.
            nome, linha_nome = None, None
            for distancia in range(JANELA_LINHAS + 1):
                for q in dict.fromkeys((p - distancia, p + distancia)):
                    if 0 <= q < len(com_texto) and paginas[com_texto[q]] == paginas[i]:
                        candidato = _nome_rotulado(linhas[com_texto[q]])
                        if candidato:
                            nome, linha_nome = candidato, com_texto[q]
                            break
                if nome:
                    break
            if not nome or len(_tokens(nome)) < 2 or mesma_pessoa(nome, nome_paciente):
                continue
            pessoa = pessoas.setdefault(cpf, {"nome": nome, "cpf": cpf, "tipo": NOME_E_CPF, "linhas": []})
            for indice in (i, linha_nome):
                if indice not in pessoa["linhas"]:
                    pessoa["linhas"].append(indice)
    for pessoa in pessoas.values():
        pessoa["linhas"].sort(key=posicao.get)
    return list(pessoas.values())


def _palavras(nome: str) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]+", nome) if w.upper() not in _PARTICULAS]


def _semelhanca(nome_a: str, nome_b: str) -> float:
    return SequenceMatcher(None, " ".join(_tokens(nome_a)), " ".join(_tokens(nome_b))).ratio()


def _conselho_abaixo(linhas: list[str], i: int, quantas: int = 2) -> bool:
    vistas = 0
    for j in range(i + 1, len(linhas)):
        if linhas[j].strip():
            if _CONSELHO.search(linhas[j]):
                return True
            vistas += 1
            if vistas >= quantas:
                return False
    return False


def _nome_de_outra_pessoa(
    nome: str,
    linhas: list[str],
    i: int,
    nome_paciente: str,
    nomes_conhecidos: Collection[str],
) -> bool:
    """
    Os cortes do aviso só pelo nome, na ordem em que foram medidos. Cada um tira
    um tipo de ruído achado na classificação à mão dos avisos (replay de 23/10):

    1. grafia parecida com a do paciente — o próprio paciente, nome estragado
       pelo OCR ("Marla Fictiua da Sirva" por MARIA FICTICIA DA SILVA);
    2. conselho ou assinatura nas 2 linhas de baixo — profissional;
    3. formulário de custódia do toxicológico por perto — coletor;
    4. palavra começando em minúscula — OCR inventando ("mavia fictiua silra");
    5. última palavra com até 2 letras — nome cortado ("FICTICIA DA SI");
    6. empresa no lugar do nome;
    7. menos da metade das palavras no vocabulário de nomes — OCR inventando
       com maiúsculas ("Quelgo Varnip").

    Com os cortes, o aviso só pelo nome sai em 15 documentos do replay, todos
    de outra pessoa de fato (conferidos um a um), contra 542 sem eles. Os
    limiares foram ajustados nessa mesma base: em documento novo, espere um
    pouco menos.
    """
    palavras = _palavras(nome)
    tokens = _tokens(nome)
    if not palavras or not tokens:
        return False
    if _semelhanca(nome, nome_paciente) >= LIMIAR_SEMELHANCA:
        return False
    if _conselho_abaixo(linhas, i):
        return False
    if any(_COLETA_TOXICOLOGICO.search(linhas[j]) for j in range(max(0, i - 4), min(len(linhas), i + 5))):
        return False
    if any(p[0].islower() for p in palavras) or len(palavras[-1]) <= 2:
        return False
    if _EMPRESA.search(nome):
        return False
    return sum(t in nomes_conhecidos for t in tokens) / len(tokens) >= FRACAO_NOMES_CONHECIDOS


def pessoas_no_documento(
    linhas: Iterable[str],
    cpf_paciente: Optional[str],
    nome_paciente: Optional[str],
    paginas: Optional[list[Optional[int]]] = None,
    nomes_conhecidos: Optional[Collection[str]] = None,
) -> list[dict]:
    """
    As pessoas de `outra_pessoa` (nome e CPF, `tipo` "nome_e_cpf") e, depois
    delas, as que só têm o nome (`tipo` "so_nome", `cpf` None): um rótulo de
    paciente com nome claramente diferente do paciente do pedido, sem CPF de
    terceiro por perto.

    O aviso só pelo nome é mais fraco, e a tela o mostra como tal. Sem cortes ele
    era quase todo ruído: no replay de 23/10 avisava em 413 dos 4.219 aprovados,
    e numa amostra de 60 só 2 eram outra pessoa — o resto era o próprio paciente
    com o nome manuscrito estragado pelo OCR, profissional e coletor. Os cortes
    de `_nome_de_outra_pessoa` precisam de `nomes_conhecidos`; sem vocabulário
    (banco fora), o aviso só pelo nome não sai.

    O nome que é o de uma pessoa já achada com CPF (o mesmo colaborador num
    laudo sem CPF) entra nas linhas dela, e não como outra pessoa.
    """
    linhas = list(linhas)
    pessoas = outra_pessoa(linhas, cpf_paciente, nome_paciente, paginas)
    if not _tokens(nome_paciente):
        return pessoas
    usadas = {i for pessoa in pessoas for i in pessoa["linhas"]}
    so_nome: list[dict] = []
    for i, linha in enumerate(linhas):
        if i in usadas:
            continue
        nome = _nome_rotulado(linha)
        if not nome or len(_tokens(nome)) < 2 or mesma_pessoa(nome, nome_paciente):
            continue
        # A mesma pessoa lida de novo, inclusive com outro erro de OCR.
        pessoa = next((p for p in pessoas + so_nome if mesma_pessoa(nome, p["nome"])), None)
        if pessoa is None:
            if not nomes_conhecidos or not _nome_de_outra_pessoa(nome, linhas, i, nome_paciente, nomes_conhecidos):
                continue
            pessoa = {"nome": nome, "cpf": None, "tipo": SO_NOME, "linhas": []}
            so_nome.append(pessoa)
        pessoa["linhas"].append(i)
    for pessoa in pessoas:
        pessoa["linhas"].sort()
    return pessoas + so_nome


def trecho(pessoa: dict, texto: str) -> Optional[tuple[int, int]]:
    """Onde, na linha, está o que identifica a pessoa: o CPF dela, ou o nome
    depois do rótulo. None quando não dá para apontar — a tela destaca a linha."""
    for m in _CPF.finditer(texto):
        if pessoa.get("cpf") and _digits_only(m.group(0)) == pessoa["cpf"]:
            return m.span()
    m = _ROTULO_NOME.match(texto)
    return m.span("valor") if m else None


def _blocos(pessoa: dict, linhas: list[str]) -> list[list[int]]:
    """As linhas da pessoa separadas por bloco de identificação: nome e CPF de
    um mesmo laudo ficam na mesma página, a até `JANELA_LINHAS` linhas com texto
    um do outro."""
    com_texto = [i for i, linha in enumerate(linhas) if linha.strip() and not _PAGINA.search(linha)]
    posicao = {indice: p for p, indice in enumerate(com_texto)}
    paginas = _paginas(linhas)
    blocos: list[list[int]] = []
    for i in pessoa["linhas"]:
        anterior = blocos[-1][-1] if blocos else None
        if (
            anterior is not None
            and paginas[i] == paginas[anterior]
            and posicao[i] - posicao[anterior] <= JANELA_LINHAS
        ):
            blocos[-1].append(i)
        else:
            blocos.append([i])
    return blocos


def _exame_do_bloco(
    bloco: list[int],
    linhas: list[str],
    normalizar: Callable[[str], str],
    normalizadas: dict[int, str],
    termos: list[tuple[str, list[re.Pattern]]],
) -> Optional[str]:
    """O exame da tabela cujo nome está mais perto do bloco, até `ALCANCE_EXAME`
    linhas com texto acima ou abaixo, sem passar de página. O laudo põe o título
    logo acima da identificação ("## LAUDO DE ESPIROMETRIA" / "DADOS DO
    COLABORADOR" / "Nome:"), ou logo abaixo (Fast Laudos: "Nome:", "CPF:",
    "Laudo Eletrocardiograma"). Empate fica com o de cima."""
    melhor: Optional[tuple[int, str]] = None
    for sentido, inicio in ((-1, bloco[0] - 1), (1, bloco[-1] + 1)):
        i, distancia = inicio, 0
        while 0 <= i < len(linhas) and distancia < ALCANCE_EXAME and not _PAGINA.search(linhas[i]):
            if linhas[i].strip():
                distancia += 1
                if melhor and distancia >= melhor[0]:
                    break
                if i not in normalizadas:
                    normalizadas[i] = normalizar(linhas[i])
                exame = next((e for e, padroes in termos if any(p.search(normalizadas[i]) for p in padroes)), None)
                if exame:
                    melhor = (distancia, exame)
                    break
            i += sentido
    return melhor[1] if melhor else None


def anotar_comparativo(
    comparativo: list[dict],
    pessoas: list[dict],
    linhas: list[str],
    normalizar: Callable[[str], str],
    sinonimos: Callable[[str], set[str]],
) -> None:
    """
    Grava a outra pessoa no exame cujo laudo ela identifica: o item da tabela
    ganha `outra_pessoa` ([{chave, nome, cpf mascarado ou None, pagina, tipo}]) e a pessoa,
    `exames`. Pessoa sem exame da tabela por perto (título que o catálogo não
    conhece, laudo de exame fora da grade) fica com `exames` vazio, e a tela a
    mostra à parte. Não mexe em status nem justificativa.

    `normalizar` e `sinonimos` são os da comparação (`workflow_service`), para
    o título do laudo casar com o exame como a busca de evidências casa.
    """
    termos = []
    for item in comparativo:
        exame = item.get("exame") if isinstance(item, dict) else None
        if not exame:
            continue
        normalizado = normalizar(exame)
        candidatos = {normalizado} | sinonimos(normalizado)
        if _CLINICO.search(normalizado):
            candidatos.add(_TITULO_ASO)
        padroes = [re.compile(rf"\b{re.escape(t)}\b") for t in candidatos if len(t) >= 3]
        termos.append((exame, padroes))
    paginas = _paginas(linhas)
    normalizadas: dict[int, str] = {}
    por_exame: dict[str, list[dict]] = {}
    for pessoa in pessoas:
        pessoa["exames"] = []
        for bloco in _blocos(pessoa, linhas):
            exame = _exame_do_bloco(bloco, linhas, normalizar, normalizadas, termos) if termos else None
            if not exame or exame in pessoa["exames"]:
                continue
            pessoa["exames"].append(exame)
            por_exame.setdefault(exame, []).append({
                "chave": chave_da_pessoa(pessoa),
                "nome": pessoa["nome"],
                "cpf": mask_cpf(pessoa["cpf"]) if pessoa.get("cpf") else None,
                "pagina": paginas[bloco[0]],
                "tipo": pessoa.get("tipo", NOME_E_CPF),
            })
    for item in comparativo:
        if isinstance(item, dict) and item.get("exame") in por_exame:
            item["outra_pessoa"] = por_exame[item["exame"]]


def para_payload(pessoas: list[dict], linhas: list[str]) -> list[dict]:
    """O que vai ao `analysis_details` para a tela: o nome como o OCR leu, o CPF
    mascarado (o revisor confere no PDF; o payload não precisa de mais uma cópia
    do número inteiro), a página, as linhas de origem e os exames em que a tela
    mostra o aviso (ver `anotar_comparativo`)."""
    paginas = _paginas(linhas)
    return [
        {
            "chave": chave_da_pessoa(p),
            "nome": p["nome"],
            "cpf": mask_cpf(p["cpf"]) if p.get("cpf") else None,
            "tipo": p.get("tipo", NOME_E_CPF),
            "pagina": paginas[p["linhas"][0]],
            "linhas": [linhas[i].strip() for i in p["linhas"]],
            "exames": p.get("exames", []),
        }
        for p in pessoas
    ]
