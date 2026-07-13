#!/usr/bin/env python3
"""
Gera massa de teste para validar filtro por clínica no frontend.

Uso:
  cd back-end
  DATABASE_URL=postgresql://... python3 scripts/seed_clinic_filter_data.py

O script é idempotente: documentos são marcados com content_hash/run_id
prefixados por "clinic-filter-seed" e não são duplicados em novas execuções.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import user_db  # noqa: E402
from app.models.user import UserRole  # noqa: E402


SEED_PREFIX = "clinic-filter-seed"
REVIEWER_EMAIL = "checker.seed@grupobrmed.com.br"


CLINICS = [
    {
        "name": "Saúde Total Ltda",
        "cnpj": "11.111.111/0001-11",
        "phone": "(85) 3333-1001",
        "city": "Fortaleza",
        "state": "CE",
        "is_active": True,
    },
    {
        "name": "Clínica Santa Rita",
        "cnpj": "22.222.222/0001-22",
        "phone": "(85) 3333-1002",
        "city": "Fortaleza",
        "state": "CE",
        "is_active": True,
    },
    {
        "name": "Vida & Saúde Ocupacional",
        "cnpj": "33.333.333/0001-33",
        "phone": "(85) 3333-1003",
        "city": "Caucaia",
        "state": "CE",
        "is_active": True,
    },
    {
        "name": "Medicina Norte Sul",
        "cnpj": "44.444.444/0001-44",
        "phone": "(85) 3333-1004",
        "city": "Maracanaú",
        "state": "CE",
        "is_active": True,
    },
    {
        "name": "Clínica Arquivada Beta",
        "cnpj": "55.555.555/0001-55",
        "phone": "(85) 3333-1005",
        "city": "Fortaleza",
        "state": "CE",
        "is_active": False,
    },
]


DOCUMENTS = [
    # Saúde Total: muitos registros para paginação + busca "Maria" + todos os status.
    ("Saúde Total Ltda", "Maria Silva Araujo", "12345678901", "validated", True, 0, 1),
    ("Saúde Total Ltda", "Maria Santos Lima", "12345678902", "pending", False, 1, 0),
    ("Saúde Total Ltda", "João Souza Neto", "12345678903", "rejected", False, 2, 1),
    ("Saúde Total Ltda", "Ana Pereira Costa", "12345678904", "rejected", True, 3, 0),
    ("Saúde Total Ltda", "Carlos Eduardo Rocha", "12345678905", "validated", True, 0, 2),
    ("Saúde Total Ltda", "Mariana Alves Pinto", "12345678906", "pending", False, 1, 1),
    ("Saúde Total Ltda", "Rafael Barroso", "12345678907", "validated", True, 0, 0),
    ("Saúde Total Ltda", "Bianca Torres", "12345678908", "pending", False, 2, 0),
    ("Saúde Total Ltda", "Felipe Ramos", "12345678909", "rejected", False, 4, 2),
    ("Saúde Total Ltda", "Larissa Moura", "12345678910", "validated", True, 0, 1),
    ("Saúde Total Ltda", "Pedro Henrique", "12345678911", "pending", False, 1, 0),
    ("Saúde Total Ltda", "Renata Queiroz", "12345678912", "validated", True, 0, 0),
    # Santa Rita: poucos registros para validar filtro estreito.
    ("Clínica Santa Rita", "Helena Costa", "98765432100", "pending", False, 2, 0),
    ("Clínica Santa Rita", "João Santa Rita", "98765432101", "validated", True, 0, 0),
    ("Clínica Santa Rita", "Camila Fernandes", "98765432102", "rejected", False, 3, 1),
    # Vida & Saúde: registros para busca com acento e status variados.
    ("Vida & Saúde Ocupacional", "Sérgio Almeida", "45678912300", "validated", True, 0, 1),
    ("Vida & Saúde Ocupacional", "Saulo Andrade", "45678912301", "pending", False, 1, 0),
    ("Vida & Saúde Ocupacional", "Aline Saúde", "45678912302", "rejected", True, 5, 2),
    # Medicina Norte Sul: clínica ativa sem documentos para estado vazio no filtro.
]


def ensure_clinic(raw: dict[str, Any]):
    clinic = user_db.get_clinic_by_name(raw["name"])
    if not clinic:
        clinic = user_db.create_clinic(
            name=raw["name"],
            cnpj=raw["cnpj"],
            phone=raw["phone"],
            city=raw["city"],
            state=raw["state"],
        )

    if clinic.is_active != raw["is_active"]:
        clinic = user_db.update_clinic(clinic.id, is_active=raw["is_active"])
    return clinic


def ensure_sender(clinic_name: str, clinic_id: str):
    slug = (
        clinic_name.lower()
        .replace("&", "e")
        .replace(" ", ".")
        .replace("í", "i")
        .replace("ú", "u")
        .replace("ã", "a")
        .replace("é", "e")
        .replace("ç", "c")
    )
    email = f"sender.{slug}.seed@clinica.com.br"
    user = user_db.get_user_by_email(email)
    if user:
        return user
    return user_db.create_user(
        email=email,
        name=f"Remetente {clinic_name}",
        role=UserRole.SENDER,
        clinic_id=clinic_id,
    )


def ensure_checker():
    user = user_db.get_user_by_email(REVIEWER_EMAIL)
    if user:
        return user
    return user_db.create_user(
        email=REVIEWER_EMAIL,
        name="Validador Seed",
        role=UserRole.CHECKER,
        clinic_id=None,
    )


def build_payload(patient_name: str, cpf: str, status: str, missing: int, extra: int) -> dict[str, Any]:
    exams_required = ["CLÍNICO OCUPACIONAL", "AUDIOMETRIA", "ACUIDADE VISUAL"]
    exams_ocr = exams_required[: max(1, len(exams_required) - missing)]
    missing_names = exams_required[len(exams_ocr) :]
    extra_names = [f"EXAME EXTRA {index + 1}" for index in range(extra)]

    if status == "validated":
        analysis = "Todos os exames obrigatórios foram enviados. Liberação concedida."
    elif status == "rejected":
        analysis = "Documento com pendências de exames obrigatórios."
    else:
        analysis = "Aguardando revisão manual."

    return {
        "run_id": SEED_PREFIX,
        "cpf": cpf,
        "cpf_processado": cpf,
        "patient_name": patient_name,
        "ocr_result": {
            "text": f"Documento seed de {patient_name}",
            "exames_extraidos": exams_ocr + extra_names,
        },
        "brmed_result": {
            "exames_obrigatorios": exams_required,
            "data_previsao_liberacao": "20/07/2026",
        },
        "validation_result": {
            "exames_faltantes": missing_names,
            "exames_extras": extra_names,
            "analysis": analysis,
        },
        "tabela_comparacao": [
            {
                "exame": exam,
                "status": "faltante" if exam in missing_names else "encontrado",
                "justificativa": "Gerado para teste do filtro por clínica.",
            }
            for exam in exams_required
        ],
        "status": "success",
    }


def create_document_if_missing(index: int, row: tuple[str, str, str, str, bool, int, int], clinics, senders) -> bool:
    clinic_name, patient_name, cpf, status, reviewed, missing, extra = row
    clinic = clinics[clinic_name]
    sender = senders[clinic_name]
    content_hash = f"{SEED_PREFIX}:{index:02d}:{clinic.id}:{cpf}"

    existing = user_db.get_document_by_hash(
        uploaded_by_user_id=sender.id,
        content_hash=content_hash,
        clinic_id=clinic.id,
    )
    if existing:
        return False

    reviewed_at = datetime.now(timezone.utc) if reviewed else None
    reviewed_by = REVIEWER_EMAIL if reviewed else None
    payload = build_payload(patient_name, cpf, status, missing, extra)
    if reviewed_by:
        payload["reviewed_by"] = reviewed_by
        payload["reviewed_at"] = reviewed_at.isoformat()

    user_db.create_document(
        clinic_id=clinic.id,
        uploaded_by_user_id=sender.id,
        uploaded_by_user_email=sender.email,
        filename=f"SEED - {clinic_name} - {patient_name}.pdf",
        content_hash=content_hash,
        cpf=cpf,
        exams_found=payload["ocr_result"]["exames_extraidos"],
        exams_ocr=payload["ocr_result"]["exames_extraidos"],
        exams_brnet=payload["brmed_result"]["exames_obrigatorios"],
        validation_status=status,
        ocr_markdown=f"# Documento seed\n\nPaciente: {patient_name}\nCPF: {cpf}",
        run_id=SEED_PREFIX,
        result_payload=payload,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        approval_reason="Seed aprovado para teste." if status == "validated" and reviewed else None,
        rejection_reason="Seed rejeitado para teste." if status == "rejected" and reviewed else None,
        confidence_score=96 if status == "validated" else 72,
        quality_score=90,
        mandatory_coverage=1.0 if missing == 0 else 0.66,
    )
    return True


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("ERRO: DATABASE_URL não configurada.")
        return 1

    clinics = {clinic["name"]: ensure_clinic(clinic) for clinic in CLINICS}
    active_clinics = {name: clinic for name, clinic in clinics.items() if clinic.is_active}
    senders = {name: ensure_sender(name, clinic.id) for name, clinic in active_clinics.items()}
    ensure_checker()

    created = 0
    for index, document in enumerate(DOCUMENTS, start=1):
        if create_document_if_missing(index, document, clinics, senders):
            created += 1

    print("Massa de teste do filtro por clínica pronta.")
    print(f"Clínicas ativas: {', '.join(active_clinics)}")
    print("Clínica ativa sem documentos: Medicina Norte Sul")
    print("Clínica inativa para validar combobox: Clínica Arquivada Beta")
    print(f"Documentos novos inseridos: {created}")
    print(f"Documentos seed esperados no total: {len(DOCUMENTS)}")
    print("")
    print("Cenários cobertos:")
    print("- Saúde Total Ltda: 12 documentos para paginação, busca por Maria e todos os status.")
    print("- Clínica Santa Rita: 3 documentos para filtro estreito.")
    print("- Vida & Saúde Ocupacional: 3 documentos para busca com acento e status variados.")
    print("- Medicina Norte Sul: estado vazio ao selecionar clínica sem atendimentos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
