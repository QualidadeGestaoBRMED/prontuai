#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${1:-}"
ACTION="${2:-show}"

if [[ -z "$JOB_ID" ]]; then
  echo "Uso: $0 <job_id> [show|fail]"
  exit 1
fi

if [[ "$ACTION" != "show" && "$ACTION" != "fail" ]]; then
  echo "Ação inválida: $ACTION"
  echo "Uso: $0 <job_id> [show|fail]"
  exit 1
fi

docker compose exec -T prontuai-backend python - "$JOB_ID" "$ACTION" <<'PY'
from datetime import datetime
import sys

from app.core.database import user_db
from app.core.db.models import JobModel

job_id = sys.argv[1]
action = sys.argv[2]

s = user_db._get_session()
try:
    job = s.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        print("job não encontrado")
        raise SystemExit(0)

    if action == "fail":
        job.status = "failed"
        job.progress = 100
        job.current_step = "failed"
        job.message = "Processamento encerrado manualmente."
        job.error = "Job encerrado manualmente após ficar preso em polling."
        job.updated_at = datetime.utcnow()
        job.completed_at = datetime.utcnow()
        s.commit()
        s.refresh(job)
        print("job marcado como failed")

    print("id:", job.id)
    print("status:", job.status)
    print("progress:", job.progress)
    print("current_step:", job.current_step)
    print("message:", job.message)
    print("error:", job.error)
    print("created_at:", job.created_at)
    print("updated_at:", job.updated_at)
    print("started_at:", job.started_at)
    print("completed_at:", job.completed_at)
finally:
    s.close()
PY
