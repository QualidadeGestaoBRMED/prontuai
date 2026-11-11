"""
Sinais vitais impossíveis na ficha médica: peso e altura trocados ou digitados errado.

O erro medido (conferência das divergências de novembro/2026 no PDF): a ficha
médica BR MED sai com "Altura 93 cm, Peso 156 kg, IMC 180,37" — peso e altura
trocados na digitação. O revisor rejeita; a IA aprovava, porque não lê a ficha.

A ficha imprime o bloco "Sinais Vitais" com os rótulos e, depois, os valores na
ordem pulso, peso, altura e IMC. O OCR às vezes desloca essa ordem (perde um
valor e a "altura" lida é o IMC), e isso sozinho dava 20 falsos positivos em
set–nov/2026. A trava é o próprio IMC: o sistema o calcula a partir do peso e da
altura, então, quando o IMC lido bate com peso ÷ altura², a ordem está certa e a
altura impossível é erro de digitação de verdade.

Medido nos aprovados pela IA de set–nov/2026 (cópia de produção de 10/11): 3.758
blocos consistentes; 4 com altura ou peso impossível, os 4 rejeitados pelo
revisor; nenhum aprovado nem aprovado sem revisão.

Só aviso para a checagem: o chamador põe o documento em pendente com a frase de
`motivo`. Não chama API e não envia dado a ninguém; roda sobre o markdown local.
"""
from __future__ import annotations

import os
import re
from typing import Optional

# Desliga sem deploy de código: SINAIS_VITAIS_AVISO=false.
HABILITADA = os.getenv("SINAIS_VITAIS_AVISO", "true").strip().lower() not in ("0", "false", "nao", "no")

ALTURA_CM = (120.0, 230.0)
PESO_KG = (30.0, 250.0)
# Diferença aceita entre o IMC lido e o calculado (arredondamento da ficha).
TOLERANCIA_IMC = 0.03

_NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)"
# Rótulos do bloco "Sinais Vitais" da ficha BR MED e os quatro valores seguintes:
# pulso, peso, altura e IMC.
_BLOCO = re.compile(
    r"Peso\s*\(kg\)\s*\n+\s*Altura\s*\(cm\)\s*\n+(?:#+\s*)?IMC\s*\n+"
    r"\s*\d{2,3}\s*\n+\s*" + _NUM + r"\s*\n+\s*" + _NUM + r"\s*\n+\s*" + _NUM + r"\s*\n",
    re.IGNORECASE,
)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _imc_lido(texto: str) -> float:
    valor = _numero(texto)
    # O OCR perde a vírgula do IMC ("2976" para 29,76).
    if valor > 100 and "," not in texto and "." not in texto:
        valor /= 100
    return valor


def incoerencia(markdown: str) -> Optional[dict]:
    """O primeiro bloco de sinais vitais com altura ou peso impossível, ou None.

    Só conta o bloco em que o IMC lido confirma a leitura de peso e altura."""
    if not HABILITADA or not markdown:
        return None
    for m in _BLOCO.finditer(markdown):
        peso, altura, imc = _numero(m.group(1)), _numero(m.group(2)), _imc_lido(m.group(3))
        if peso <= 0 or altura <= 0:
            continue
        calculado = peso / ((altura / 100) ** 2)
        if abs(calculado - imc) / max(imc, 1) > TOLERANCIA_IMC:
            continue  # leitura fora de ordem: não dá para afirmar nada
        if not (ALTURA_CM[0] <= altura <= ALTURA_CM[1]) or not (PESO_KG[0] <= peso <= PESO_KG[1]):
            return {"peso_kg": peso, "altura_cm": altura, "imc": round(imc, 2)}
    return None


def motivo(achado: dict) -> str:
    """A frase da IA. Só os números da ficha: não identificam o paciente."""
    altura = f"{achado['altura_cm']:g}".replace(".", ",")
    peso = f"{achado['peso_kg']:g}".replace(".", ",")
    imc = f"{achado['imc']:g}".replace(".", ",")
    return (
        f"Ficha médica com peso e altura impossíveis (altura {altura} cm, peso {peso} kg, "
        f"IMC {imc}): confira se não foram trocados."
    )
