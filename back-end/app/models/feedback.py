"""
Parecer humano sobre o resultado da IA em um documento.

Molde da Triagem BR NET (tabela `reviews`), com três diferenças deliberadas:

- o parecer é **opcional** — nunca trava aprovação, rejeição nem download,
  diferente do 409 que a Triagem devolve no download sem avaliação;
- não há tabela de eventos: o `audit_log` é escrito direto pelo handler, com o
  antes e o depois de cada reavaliação;
- as categorias são as do domínio do ProntuAI (OCR → BRNET → comparação),
  não as do PGR/PCMSO.

**Todo motivo de exame aponta para um exame.** `issue_items` é uma lista de
pares (categoria, exame): sem o exame, "faltante incorreto" não diz em quê, e a
resposta não serve para corrigir o motor de comparação nem para responder
"quais exames a IA mais erra".

Os problemas que **não** são de exame — nome do paciente, CPF, data, documento
ilegível — vivem em `document_issues`, uma lista de códigos e nada mais. Campo
separado, e não `exame` opcional dentro de `issue_items`: com nulo permitido, um
motivo de exame sem exame voltaria a passar, que é exatamente o que este formato
existe para impedir.

`notes` é texto livre de quem revisa e **pode conter nome ou CPF de paciente**:
nunca vai para log, auditoria ou telemetria.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

FeedbackStatus = Literal["IA_CORRETA", "IA_CORRETA_COM_AJUSTES", "IA_INCORRETA"]

# Espelho de `CATEGORIAS_EXAME` e `CATEGORIAS_DOCUMENTO` em
# `front-end/types/feedback.ts`. Mudar aqui exige mudar lá: é o back-end que
# recusa categoria inválida, mas é o front que decide quais chips o revisor
# enxerga. `test_categorias_do_back_batem_com_as_do_front` compara as duas
# listas, cada uma com a sua, e quebra se alguém trocar uma de família.
#
# Motivos que apontam para um exame.
CATEGORIAS_EXAME: frozenset[str] = frozenset({
    "EXAME_NAO_RECONHECIDO",    # estava no PDF e a IA não extraiu (vem digitado)
    "SINONIMO_NAO_RECONHECIDO", # extraído, mas fora do catálogo de sinônimos
    "FALTANTE_INCORRETO",       # apontado como faltante, mas existia
    "EXTRA_INCORRETO",          # apontado como extra, mas era legítimo
    "VALIDADE_PERIODICIDADE",   # erro de validade/periodicidade do exame
    "DADO_BRNET",               # a exigência veio errada ou desatualizada do BRNET
    "OUTRO",
})

# Problemas do documento inteiro: não há exame a que amarrar.
CATEGORIAS_DOCUMENTO: frozenset[str] = frozenset({
    "OCR_NOME",       # nome do paciente lido errado ou corrompido
    "OCR_CPF",        # CPF lido errado
    "OCR_DATA",       # data do exame/ASO lida errada
    "DOC_ILEGIVEL",   # o documento não foi lido de forma aproveitável
})

# União das duas, para quem só precisa saber se um código é válido.
CATEGORIAS: frozenset[str] = CATEGORIAS_EXAME | CATEGORIAS_DOCUMENTO

# Status que exigem detalhamento. Sem o "o quê" e o "por quê", um parecer
# negativo não vira dado utilizável — vira só um contador de queixa.
STATUS_COM_DETALHES: frozenset[str] = frozenset({
    "IA_CORRETA_COM_AJUSTES",
    "IA_INCORRETA",
})

# Teto do que o revisor consegue marcar: 7 categorias × exames de um documento.
# Generoso de propósito — serve para barrar payload absurdo, não para limitar uso.
MAX_ITENS = 200


class FeedbackIssueItem(BaseModel):
    """Um par (categoria, exame): o motivo e onde ele aconteceu."""

    categoria: str
    exame: str = Field(min_length=1, max_length=300)
    # Veredito que a IA tinha dado para esse exame (`faltante`, `extra_no_ocr`,
    # `encontrado`, ...), copiado da tabela de comparação. Guardado junto porque
    # o `result_payload` do documento pode ser reprocessado depois, e sem isto
    # não dá para saber o que a IA dizia quando o revisor discordou.
    veredito_ia: Optional[str] = Field(default=None, max_length=50)
    # True quando o exame foi digitado, não escolhido da comparação — o caso do
    # EXAME_NAO_RECONHECIDO. Texto livre não casa com o catálogo: estes itens
    # precisam de curadoria antes de virar sinônimo.
    fora_da_lista: bool = False

    @field_validator("categoria")
    @classmethod
    def categoria_valida(cls, value: str) -> str:
        if value not in CATEGORIAS_EXAME:
            # Recusa também as de documento: elas não têm exame e pertencem a
            # `document_issues`. Aceitar aqui geraria item com exame inventado.
            raise ValueError(f"Categoria de exame inválida: {value}")
        return value

    @field_validator("exame")
    @classmethod
    def exame_sem_espaco_solto(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("O exame não pode ser vazio.")
        return value


class DocumentFeedbackInput(BaseModel):
    """Payload do PUT. A coerência com o status é validada na rota."""

    status: FeedbackStatus
    issue_items: List[FeedbackIssueItem] = Field(default_factory=list, max_length=MAX_ITENS)
    document_issues: List[str] = Field(
        default_factory=list, max_length=len(CATEGORIAS_DOCUMENTO)
    )
    notes: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("document_issues")
    @classmethod
    def problemas_de_documento_validos(cls, value: List[str]) -> List[str]:
        value = list(dict.fromkeys(value))
        invalidos = set(value) - CATEGORIAS_DOCUMENTO
        if invalidos:
            raise ValueError(
                f"Problemas de documento inválidos: {', '.join(sorted(invalidos))}"
            )
        return value

    @field_validator("issue_items")
    @classmethod
    def itens_sem_repeticao(cls, value: List[FeedbackIssueItem]) -> List[FeedbackIssueItem]:
        # O mesmo exame pode aparecer sob duas categorias (um exame pode ter dois
        # problemas); o que não pode é o mesmo par vir duas vezes, o que
        # inflaria a contagem por categoria no painel.
        vistos: set[tuple[str, str]] = set()
        unicos: List[FeedbackIssueItem] = []
        for item in value:
            chave = (item.categoria, item.exame.strip().casefold())
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(item)
        return unicos

    @field_validator("notes")
    @classmethod
    def notas_sem_espaco_solto(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def tem_problema(self) -> bool:
        """Apontou alguma coisa — em exame ou no documento."""
        return bool(self.issue_items or self.document_issues)

    def categorias(self) -> List[str]:
        """Categorias distintas das duas listas, na ordem em que aparecem.

        Derivada, nunca recebida do cliente: a coluna `issue_categories` existe
        para consulta rápida sem desmontar o JSON — e responde de uma vez pelos
        dois tipos de problema. Duas fontes para o mesmo fato sairiam do ar uma
        da outra no primeiro bug de front.
        """
        return list(
            dict.fromkeys(
                [item.categoria for item in self.issue_items] + self.document_issues
            )
        )


class DocumentFeedback(BaseModel):
    """Parecer persistido, como sai da API."""

    id: str
    document_id: str
    status: FeedbackStatus
    issue_categories: List[str] = Field(default_factory=list)
    issue_items: List[FeedbackIssueItem] = Field(default_factory=list)
    document_issues: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    reviewed_by_email: Optional[str] = None
    reviewed_by_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "uuid-feedback",
                "document_id": "uuid-documento",
                "status": "IA_INCORRETA",
                "issue_categories": ["FALTANTE_INCORRETO", "OCR_NOME"],
                "issue_items": [
                    {
                        "categoria": "FALTANTE_INCORRETO",
                        "exame": "Audiometria",
                        "veredito_ia": "faltante",
                        "fora_da_lista": False,
                    }
                ],
                "document_issues": ["OCR_NOME"],
                "notes": "A audiometria estava na página 2 do PDF.",
                "reviewed_by_email": "checador@grupobrmed.com.br",
            }
        }
