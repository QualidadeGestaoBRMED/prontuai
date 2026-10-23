#!/usr/bin/env python3
"""
Vincula as clínicas já cadastradas ao credenciado do BRNET (`clinics.brnet_id`).

Uso (dentro do container do backend):
    python scripts/vincular_clinicas_brnet.py              # só mostra o que faria
    python scripts/vincular_clinicas_brnet.py --aplicar

A ponte é o nome: até a migration 014 a clínica não guardava nada do BRNET, e
o time cadastrava com o rótulo "CIDADE - UF - NOME" copiado do BRNET. Casa só o
nome inteiro, com a normalização do dashboard (sem acento, sem caixa, travessão
= hífen) — nunca o nome curto: 38 nomes curtos aparecem em mais de um rótulo
(redes com unidade em várias cidades). Medido em out/2026: 132 das 145 clínicas
ativas casam; as que sobram (contas internas, nome curto, credenciado que saiu
da rede) ficam para vincular à mão na tela de clínicas.

Clínica que já tem vínculo não é tocada. Cidade, UF e e-mail vêm do
credenciado e só preenchem o que está vazio. Inativas entram também: reativar uma clínica
vinculada é o caminho certo quando o credenciado volta.

O relatório lista ainda os credenciados com mais de uma clínica — as duplicatas
que precisam ser unificadas antes de o vínculo virar único (ver a migration 014).
"""
import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.dashboard_service import _chave_nome  # noqa: E402
from app.services.rede_credenciada_service import CredenciadoRede, listar_rede_credenciada  # noqa: E402


def planejar_vinculos(clinicas, rede: list[CredenciadoRede]) -> dict:
    """O que vincular, o que já estava vinculado e o que não tem par na rede."""
    por_nome = {_chave_nome(c.nome): c for c in rede}
    vincular, sem_par, ja_vinculadas = [], [], []
    for clinica in clinicas:
        if clinica.brnet_id:
            ja_vinculadas.append((clinica, clinica.brnet_id))
            continue
        credenciado = por_nome.get(_chave_nome(clinica.name))
        if credenciado:
            vincular.append((clinica, credenciado))
        else:
            sem_par.append(clinica)

    por_credenciado = defaultdict(list)
    for clinica, brnet_id in ja_vinculadas:
        por_credenciado[brnet_id].append(clinica)
    for clinica, credenciado in vincular:
        por_credenciado[credenciado.identificador].append(clinica)
    duplicadas = {k: v for k, v in por_credenciado.items() if len(v) > 1}

    # Já vinculada com cidade, UF ou e-mail vazios: completa pelo credenciado do
    # vínculo (o e-mail entrou na migration 014 depois dos primeiros vínculos).
    por_id = {c.identificador: c for c in rede}
    completar = [
        (clinica, por_id[brnet_id])
        for clinica, brnet_id in ja_vinculadas
        if brnet_id in por_id and not (clinica.city and clinica.state and clinica.email)
    ]
    return {"vincular": vincular, "sem_par": sem_par, "ja_vinculadas": ja_vinculadas,
            "duplicadas": duplicadas, "completar": completar}


def _situacao(clinica) -> str:
    return "ativa" if clinica.is_active else "inativa"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Grava os vínculos (sem isto, só relata).")
    args = parser.parse_args()

    from app.core.database import user_db  # noqa: PLC0415 - exige DATABASE_URL

    rede = await listar_rede_credenciada()
    clinicas = user_db.get_all_clinics(include_inactive=True)
    plano = planejar_vinculos(clinicas, rede)

    print(f"Rede credenciada: {len(rede)} credenciados · clínicas no ProntuAI: {len(clinicas)}")
    print(f"  já vinculadas: {len(plano['ja_vinculadas'])} (a completar cidade/UF/e-mail: {len(plano['completar'])})")
    print(f"  a vincular:    {len(plano['vincular'])}")
    print(f"  sem par:       {len(plano['sem_par'])}")
    if plano["sem_par"]:
        print("\nSem par na rede (vincular à mão ou deixar sem vínculo):")
        for clinica in sorted(plano["sem_par"], key=lambda c: (not c.is_active, c.name)):
            print(f"  - {clinica.name} ({_situacao(clinica)})")
    if plano["duplicadas"]:
        print(f"\nCredenciados com mais de uma clínica ({len(plano['duplicadas'])}) — unificar antes do vínculo único:")
        nomes = {c.identificador: c.nome for c in rede}
        for brnet_id, grupo in sorted(plano["duplicadas"].items(), key=lambda kv: nomes.get(kv[0], kv[0])):
            ativas = sum(1 for c in grupo if c.is_active)
            print(f"  - {brnet_id} {nomes.get(brnet_id, '?')}: {len(grupo)} clínicas ({ativas} ativas)")

    if not args.aplicar:
        print("\n[dry-run] nada foi gravado. Rode com --aplicar para gravar.")
        return 0

    for clinica, credenciado in plano["vincular"] + plano["completar"]:
        user_db.update_clinic(
            clinic_id=clinica.id,
            brnet_id=credenciado.identificador,
            city=None if clinica.city else credenciado.cidade,
            state=None if clinica.state else credenciado.uf,
            email=None if clinica.email else credenciado.email,
        )
    print(f"\nGravado: {len(plano['vincular'])} clínicas vinculadas, {len(plano['completar'])} completadas.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
