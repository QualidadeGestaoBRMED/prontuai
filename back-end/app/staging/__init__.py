"""
Ferramentas que só existem em staging (STC-981).

Tudo que serve apenas para testar em staging mora nesta pasta (e, no front, em
`front-end/components/staging/`). O código pode estar em qualquer branch,
inclusive na `v1`: o que garante que ele não age em produção é `ativo()`, não a
ausência do código. Por isso o merge de staging para a v1 não precisa de cuidado
especial com estas ferramentas.

`ativo()` exige DUAS chaves independentes, para que um erro isolado de
configuração não ligue nada em produção:

- `APP_ENV=staging` — vem do `.env` do servidor de staging. Sem a variável, o
  ambiente assumido é `production` (`app/core/config.py`);
- `FERRAMENTAS_DE_STAGING=true` — fixa no `back-end/docker-compose.stg.yml`, que
  só o deploy de staging usa. O compose de produção não a tem.

O deploy de produção confere as duas antes de subir o container
(`ops/deploy/conferir_producao_sem_ferramentas_de_staging.sh` e a conferência do
ambiente renderizado no servidor) e falha se alguma aparecer.

Regras para quem adicionar uma ferramenta aqui:

- todo ponto de entrada chama `ativo()` antes de ler ou gravar qualquer coisa;
- nada de migração nem de modelo do SQLAlchemy: tabela de ferramenta nasce no
  primeiro uso em staging. A migração roda no startup de qualquer ambiente;
- o código compartilhado só importa esta pasta nos pontos de gancho listados em
  `tests/test_ferramentas_de_staging.py`, para a fronteira continuar visível.
"""
from __future__ import annotations

import os

from app.core.config import settings

AMBIENTE = "staging"
VARIAVEL = "FERRAMENTAS_DE_STAGING"


def ativo() -> bool:
    """As ferramentas de staging só valem com as duas chaves."""
    if settings.APP_ENV != AMBIENTE:
        return False
    return os.getenv(VARIAVEL, "").strip().lower() == "true"
