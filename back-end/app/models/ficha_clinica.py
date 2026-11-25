"""
Campos fechados da ficha clínica (STC-1068), entrada da conduta sugerida (STC-1065).

A lista junta o que a Ficha Médica da BR MED pergunta (anamnese, hábitos, sinais vitais) com o
que muda a conduta no artefato "Conduta ASO por Empresa" da Saúde (Karine): diabetes
insulinodependente, visão monocular, hérnia, medicação controlada e sedativa, epilepsia,
labirintite, transtorno psiquiátrico, álcool e drogas, insuficiência renal, cirurgia recente,
gestação e lactação, fobia de altura/confinamento, doença neurológica e, no exame físico, Romberg
positivo e sinais de uso de substância.

Cada campo sim/não traz o trecho do texto que justifica o valor. Campo que a ficha não traz é
`nao_informado` — nunca `nao`. O mesmo modelo serve às duas fontes:
- `app/services/ficha_clinica_regras.py::ler_ficha_regras(texto) -> FichaClinica`, leitura
  determinística da Ficha Médica da BR MED (sem LLM);
- `app/services/ficha_clinica.py::extrair_ficha(texto) -> FichaClinica | None`, que usa as regras
  e completa só o que ficou `nao_informado` com o 4o mini (Structured Outputs, schema estrito).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SimNao = Literal["sim", "nao", "nao_informado"]


class Campo(BaseModel):
    """Um item sim/não da ficha e o trecho do texto que o justifica (vazio se nao_informado)."""
    model_config = ConfigDict(extra="forbid")

    valor: SimNao
    trecho: Optional[str] = Field(description="Trecho literal do texto que justifica o valor; null se nao_informado.")


class Tabagismo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: Literal["sim", "ex", "nao", "nao_informado"]
    trecho: Optional[str]


class Etilismo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: Literal["sim", "eventual", "nao", "nao_informado"]
    trecho: Optional[str]


class AtividadeFisica(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: Literal["sedentario", "ate_2x_semana", "3x_ou_mais_semana", "outro", "nao_informado"]
    trecho: Optional[str]


class SinaisVitais(BaseModel):
    """Números da ficha. Null quando não lido."""
    model_config = ConfigDict(extra="forbid")

    pa_sistolica: Optional[float]
    pa_diastolica: Optional[float]
    freq_cardiaca: Optional[float]
    peso_kg: Optional[float]
    altura_cm: Optional[float]
    imc: Optional[float]
    circ_abdominal_cm: Optional[float]


class Anamnese(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queixa_atual: Campo
    usa_medicamento: Campo
    doenca_cronica: Campo
    cirurgia_previa: Campo
    cirurgia_ha_menos_de_4_meses: Campo
    alergia: Campo
    internacao: Campo
    acidente_trabalho: Campo
    afastamento_inss: Campo
    uso_drogas: Campo
    tabagismo: Tabagismo
    etilismo: Etilismo
    atividade_fisica: AtividadeFisica


class Condicoes(BaseModel):
    """Doença declarada pelo trabalhador ou registrada pelo médico na ficha."""
    model_config = ConfigDict(extra="forbid")

    hipertensao: Campo
    diabetes: Campo
    diabetes_insulinodependente: Campo
    dislipidemia: Campo
    cardiopatia: Campo
    tireoide: Campo
    respiratoria: Campo
    epilepsia_convulsao: Campo
    labirintite_vertigem: Campo
    transtorno_psiquiatrico: Campo
    insuficiencia_renal_cronica: Campo
    cancer: Campo
    obesidade: Campo
    anemia: Campo
    hernia: Campo
    visao_monocular: Campo
    gestacao: Campo
    lactante: Campo
    fobia_altura_ou_confinamento: Campo  # acrofobia / claustrofobia (NR-35, NR-33)
    doenca_neurologica: Campo


class ExameFisico(BaseModel):
    """Achado do exame físico registrado na ficha que muda a conduta no artefato da Saúde."""
    model_config = ConfigDict(extra="forbid")

    romberg_positivo: Campo
    sinais_uso_substancia: Campo  # sinais de uso de substância psicoativa, inclusive embriaguez


class HistoricoFamiliar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hipertensao: Campo
    diabetes: Campo
    cardiopatia: Campo
    cancer: Campo


class Medicamentos(BaseModel):
    """Classe do medicamento em uso (pelo princípio ativo ou nome comercial)."""
    model_config = ConfigDict(extra="forbid")

    anti_hipertensivo: Campo
    antidiabetico_oral: Campo
    insulina: Campo
    hipolipemiante: Campo
    antiagregante: Campo
    anticoagulante: Campo
    psicotropico: Campo
    sedativo_benzodiazepinico: Campo
    anticonvulsivante: Campo
    opioide: Campo
    imunossupressor_quimioterapico: Campo
    levotiroxina: Campo


class FichaClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sinais_vitais: SinaisVitais
    anamnese: Anamnese
    condicoes: Condicoes
    exame_fisico: ExameFisico
    historico_familiar: HistoricoFamiliar
    medicamentos: Medicamentos
    outros_achados_relevantes: list[str] = Field(
        description="Achados da ficha que pesam na conduta e não cabem nos campos acima, em frases curtas."
    )
    # Quem preencheu cada parte: "regras" (Ficha Médica da BR MED lida sem LLM), "llm" ou "regras+llm".
    fonte: Literal["regras", "llm", "regras+llm"]


def ficha_vazia(fonte: Literal["regras", "llm", "regras+llm"] = "regras") -> FichaClinica:
    """Tudo nao_informado e sinais vitais nulos: o ponto de partida das duas fontes."""
    ni = {"valor": "nao_informado", "trecho": None}

    def bloco(modelo):
        return {nome: ni for nome in modelo.model_fields}

    anamnese = bloco(Anamnese)
    return FichaClinica(
        sinais_vitais=SinaisVitais(**{k: None for k in SinaisVitais.model_fields}),
        anamnese=Anamnese(**anamnese),
        condicoes=Condicoes(**bloco(Condicoes)),
        exame_fisico=ExameFisico(**bloco(ExameFisico)),
        historico_familiar=HistoricoFamiliar(**bloco(HistoricoFamiliar)),
        medicamentos=Medicamentos(**bloco(Medicamentos)),
        outros_achados_relevantes=[],
        fonte=fonte,
    )
