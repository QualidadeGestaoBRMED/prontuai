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
    "ENCONTRADO_INCORRETO",     # apontado como encontrado, mas não estava no documento
    # Dado como encontrado, e estava lá — mas não servia. A IA aceitou um exame
    # que a clínica precisa reenviar.
    "EXAME_OUTRA_DATA",         # era de outra data (antigo, vencido, de outro atendimento)
    "EXAME_ILEGIVEL",           # veio cortado, ilegível ou incompleto (sem conclusão, sem resultado)
    "EXAME_SEM_ASSINATURA",     # sem carimbo ou assinatura do profissional
    "VALIDADE_PERIODICIDADE",   # erro de validade/periodicidade do exame
    "DADO_BRNET",               # a exigência veio errada ou desatualizada do BRNET
    "OUTRO",
})

# Problemas do documento inteiro: não há exame a que amarrar.
# Problemas do documento inteiro. Os quatro primeiros são de LEITURA (a IA não
# conseguiu ler o que estava lá); os demais são de CONTEÚDO (o que a clínica
# enviou está incompleto ou errado) e foram levantados a partir do que os
# revisores de fato escreveram no antigo campo "Motivo da rejeição".
#
# Medido no banco de dev sobre 387 rejeições escritas à mão: o ASO sozinho
# responde por 106 delas (27%) — cortado ou em duas páginas, sem marcação de
# aptidão, ou com dado errado. Peça faltando no prontuário são 34, exames
# espalhados em vários anexos são 25 e envio duplicado 9. As quatro categorias
# de leitura que existiam cobriam 7 das 387: quase tudo caía em "Outro" ou no
# texto livre, que agora saiu do modal.
CATEGORIAS_DOCUMENTO: frozenset[str] = frozenset({
    "OCR_NOME",             # nome do paciente lido errado ou corrompido
    "OCR_CPF",              # CPF lido errado
    "OCR_DATA",             # data do exame/ASO lida errada
    "OCR_CNPJ",             # CNPJ da empresa lido errado
    "DOC_ILEGIVEL",         # o documento não foi lido de forma aproveitável
    "ASO_INCOMPLETO",       # ASO cortado, ou só uma das duas páginas
    "ASO_SEM_APTIDAO",      # ASO sem a marcação de apto/inapto
    "ASO_DADO_ERRADO",      # ASO com tipagem, data ou carimbo errados
    "PRONTUARIO_INCOMPLETO",# faltou peça do prontuário (ficha, laudo, o próprio ASO)
    "ANEXOS_SEPARADOS",     # exames do mesmo paciente vieram em anexos diferentes
    "ENVIO_DUPLICADO",      # o mesmo documento foi enviado mais de uma vez
    "PACIENTE_TROCADO",     # o documento é de outro paciente
    "ASO_SEM_REAPROVEITAMENTO",  # a clínica não usou o ASO com reaproveitamento enviado no agendamento
    # Erros da consulta ao BRNET, quando a IA para antes de comparar exames:
    # 347 dos 628 motivos de rejeição gravados no dev eram a mensagem dessas
    # falhas copiada. Sem estas, o revisor não tinha como dizer que ela errou ali.
    "BRNET_EXPEDICAO",      # a expedição em aberto existia
    "BRNET_PACIENTE",       # o paciente estava cadastrado
    "BRNET_EXIGENCIA",      # as exigências de exame vieram erradas
    # "Outro", contado em `notes`. Precisa ser código, e não só texto: a rota
    # exige ao menos um problema apontado em todo parecer negativo.
    "OUTRO_PROBLEMA",
})

# União das duas, para quem só precisa saber se um código é válido.
CATEGORIAS: frozenset[str] = CATEGORIAS_EXAME | CATEGORIAS_DOCUMENTO

# Motivo externo: a IA leu o documento certo, e o revisor decidiu diferente por
# uma razão que não estava nele. Não é erro da IA — o painel de acurácia conta o
# caso como acerto.
#
# Campo PRÓPRIO do parecer, e não mais um código em `document_issues`: aquela
# lista é "o que a IA errou", e misturar os dois inflaria a contagem de
# categorias de erro justamente com os casos em que ela não errou.
#
# Antes do modal, o painel adivinhava o motivo externo por palavra-chave no
# texto livre da aprovação. O modal não pede texto para aprovar, então sem este
# campo o sinal sumia — e a divergência passava a contar como erro da IA.
#
# As opções saíram do que os revisores escreviam: medido no dev, sobre as
# aprovações com justificativa que o painel classificava como motivo externo,
# exame feito por fora (quase sempre o toxicológico, em parceiro ou outro
# sistema) 51, guia não anexada com os exames no anexo 40, exames de outro ticket
# ou lançados em duplicidade 18, liberação sem o exame autorizada pelo cliente 16.
# "Não exigido na grade" tinha 3 e foi para "Outro".
#
# Revisão de 23/10/2026, sobre as 1.070 justificativas escritas quando a IA barrou
# e o revisor liberou: o "voucher não anexado" (44) é a guia, e o rótulo passou a
# usar a palavra dos revisores. Entraram dois casos que caíam no texto livre, os
# dois de documento em que a IA para antes de comparar exames:
#   * CNPJ_DIVERGENTE — o CNPJ do ASO é de outra empresa e o BRNET não acha o
#     paciente. Em 23 de 129 justificativas que citavam CNPJ, a IA leu certo o
#     único CNPJ do documento; nas outras ela não leu ou o documento tinha vários,
#     e aí é erro dela ("Errou", OCR_CNPJ), não motivo externo.
#   * ATENDIMENTO_NAO_REGISTRADO — o atendimento ainda não estava no BRNET (sem
#     expedição em aberto) quando a IA consultou.
# Os dois, aprovados, também deixam de contar como falha técnica no painel: a
# IA não falhou, o dado de fora é que não batia.
MOTIVOS_EXTERNOS: frozenset[str] = frozenset({
    "EXAME_POR_FORA",               # feito em parceiro ou registrado em outro sistema
    "GUIA_NAO_ANEXADA",             # a clínica não anexou o voucher/guia; os exames estão no PDF
    "CNPJ_DIVERGENTE",              # o CNPJ do ASO é de outra empresa
    "ATENDIMENTO_NAO_REGISTRADO",   # o atendimento ainda não estava registrado no BRNET
    "OUTRO_TICKET",                 # enviado em duplicidade, ou os exames são de outro ticket
    "CLIENTE_AUTORIZOU",            # liberação sem o exame, autorizada pelo cliente
    "OUTRO",                        # contado em `notes`, que aí é obrigatório
})

# Motivos externos que explicam uma falha técnica: a IA parou porque o dado de
# fora (empresa, atendimento) não batia, não porque leu errado.
MOTIVOS_EXTERNOS_DE_FALHA: frozenset[str] = frozenset({
    "CNPJ_DIVERGENTE",
    "ATENDIMENTO_NAO_REGISTRADO",
})

# Status que exigem detalhamento. Sem o "o quê" e o "por quê", um parecer
# negativo não vira dado utilizável — vira só um contador de queixa.
STATUS_COM_DETALHES: frozenset[str] = frozenset({
    "IA_CORRETA_COM_AJUSTES",
    "IA_INCORRETA",
})

# Teto do que o revisor consegue marcar: categorias de exame × exames de um documento.
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
    # Só num parecer IA_CORRETA — a coerência com o status é validada na rota.
    motivo_externo: Optional[str] = None

    @field_validator("motivo_externo")
    @classmethod
    def motivo_externo_valido(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in MOTIVOS_EXTERNOS:
            raise ValueError(f"Motivo externo inválido: {value}")
        return value

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
    motivo_externo: Optional[str] = None
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
