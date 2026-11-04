"""
Pedidos do BR NET guardados para repetir testes em staging (STC-981).

A API de pedidos só devolve expedição em aberto. Depois que o paciente é
expedido, ela responde 404 com "Expedição em aberto não encontrada para o
paciente informado." e o documento é rejeitado. Em produção essa é a regra
certa. Em staging ela impede repetir um teste com documento real: nos 14 dias
até 04/11/2026, 10 dos 15 documentos enviados lá receberam essa mensagem.

Com a chave ligada no painel (`/admin/ops-manutencao`):

- toda consulta bem-sucedida guarda a resposta, uma linha por CPF ou passaporte
  e CNPJ, a mesma chave que a API usa;
- a API continua sendo consultada primeiro. O pedido guardado só entra quando ela
  responde que não há expedição em aberto. Falha técnica continua sendo erro;
- o resultado sai com `source` = `pedido_guardado`, que vai para o payload como
  `fonte_exames_obrigatorios`.

**Esta função não pode valer em produção:** usar pedido antigo liberaria documento
sem expedição aberta. Por isso, fora de `APP_ENV=staging`:

- nada é lido nem gravado, e nem a chave é consultada. Sem `APP_ENV` definido, o
  ambiente assumido é `production` (`app/core/config.py`);
- as rotas do painel respondem 404, e a tela esconde o card;
- as tabelas não existem. Elas são criadas aqui na primeira vez que staging as usa,
  e não por migração nem por modelo do SQLAlchemy, de propósito: a migração roda
  no startup e não é desfeita ao voltar a imagem, então um merge por engano
  alteraria o banco de produção.

Além disso, o deploy de produção falha se encontrar este código na `v1`.

É apoio a teste: uma falha aqui nunca muda o que a API respondeu. Só o tipo do
erro vai para o log, porque a resposta tem nome e CPF do paciente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import unicodedata
from typing import Any, Optional

from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

FONTE = "pedido_guardado"
_AMBIENTE = "staging"
_MENSAGEM_SEM_EXPEDICAO = "expedicao em aberto nao encontrada"

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS pedidos_guardados (
        identificador VARCHAR(32) NOT NULL,
        cnpj VARCHAR(14) NOT NULL,
        resposta JSONB NOT NULL,
        criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
        atualizado_em TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY (identificador, cnpj)
    )
    """,
    # Uma linha só. Sem linha = desligada.
    """
    CREATE TABLE IF NOT EXISTS pedidos_guardados_chave (
        id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
        ligada BOOLEAN NOT NULL,
        atualizada_em TIMESTAMP NOT NULL DEFAULT NOW(),
        atualizada_por VARCHAR
    )
    """,
)

_lock = threading.Lock()
_tabelas_prontas = False


def disponivel() -> bool:
    """A função só existe em staging."""
    return settings.APP_ENV == _AMBIENTE


def _engine():
    # Nunca chega aqui fora de staging. É a última barreira contra criar tabela
    # ou ler dado de teste em outro banco.
    if not disponivel():
        raise RuntimeError("Pedidos guardados só existem em staging")
    from app.core.database import user_db

    global _tabelas_prontas
    if not _tabelas_prontas:
        with _lock:
            if not _tabelas_prontas:
                with user_db.engine.begin() as conexao:
                    for comando in _DDL:
                        conexao.execute(text(comando))
                _tabelas_prontas = True
    return user_db.engine


def chave_ligada() -> bool:
    with _engine().connect() as conexao:
        linha = conexao.execute(text("SELECT ligada FROM pedidos_guardados_chave WHERE id = 1")).first()
    return bool(linha and linha[0])


def definir_chave(ligada: bool, ator: Optional[str]) -> None:
    with _engine().begin() as conexao:
        conexao.execute(
            text(
                """
                INSERT INTO pedidos_guardados_chave (id, ligada, atualizada_por)
                VALUES (1, :ligada, :ator)
                ON CONFLICT (id) DO UPDATE
                SET ligada = EXCLUDED.ligada, atualizada_em = NOW(), atualizada_por = EXCLUDED.atualizada_por
                """
            ),
            {"ligada": ligada, "ator": ator},
        )


def resumo() -> dict[str, Any]:
    """O que o painel mostra. Sem dado de paciente."""
    with _engine().connect() as conexao:
        chave = conexao.execute(
            text("SELECT ligada, atualizada_em, atualizada_por FROM pedidos_guardados_chave WHERE id = 1")
        ).first()
        pedidos = conexao.execute(text("SELECT COUNT(*), MAX(atualizado_em) FROM pedidos_guardados")).first()
    return {
        "ligada": bool(chave and chave[0]),
        "chave_atualizada_em": chave[1] if chave else None,
        "chave_atualizada_por": chave[2] if chave else None,
        "total_pedidos": pedidos[0],
        "ultimo_pedido_em": pedidos[1],
    }


def _sem_expedicao_em_aberto(resultado: dict[str, Any]) -> bool:
    if resultado.get("error_type") != "semantic" or resultado.get("http_status") != 404:
        return False
    mensagem = unicodedata.normalize("NFKD", str(resultado.get("erro") or ""))
    mensagem = "".join(c for c in mensagem if not unicodedata.combining(c)).lower()
    return _MENSAGEM_SEM_EXPEDICAO in mensagem


def _gravar(identificador: str, cnpj: str, resposta: dict[str, Any]) -> None:
    with _engine().begin() as conexao:
        conexao.execute(
            text(
                """
                INSERT INTO pedidos_guardados (identificador, cnpj, resposta)
                VALUES (:identificador, :cnpj, CAST(:resposta AS JSONB))
                ON CONFLICT (identificador, cnpj)
                DO UPDATE SET resposta = EXCLUDED.resposta, atualizado_em = NOW()
                """
            ),
            {
                "identificador": identificador,
                "cnpj": cnpj,
                "resposta": json.dumps(resposta, ensure_ascii=False),
            },
        )


def _buscar(identificador: str, cnpj: str) -> Optional[dict[str, Any]]:
    with _engine().connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT resposta FROM pedidos_guardados "
                "WHERE identificador = :identificador AND cnpj = :cnpj"
            ),
            {"identificador": identificador, "cnpj": cnpj},
        ).first()
    return linha[0] if linha else None


async def aplicar(
    resultado: dict[str, Any],
    identificador: Optional[str],
    cnpj: Optional[str],
) -> dict[str, Any]:
    """
    Guarda o pedido recebido da API ou, se ela diz que não há expedição em
    aberto, devolve o guardado. Nos demais casos devolve `resultado` sem mudar.
    `identificador` e `cnpj` já vêm normalizados.
    """
    if not identificador or not cnpj or not disponivel():
        return resultado

    guardar = "erro" not in resultado and bool(resultado.get("exames"))
    if not guardar and not _sem_expedicao_em_aberto(resultado):
        return resultado

    try:
        if not await asyncio.to_thread(chave_ligada):
            return resultado
        if guardar:
            await asyncio.to_thread(_gravar, identificador, cnpj, resultado)
            return resultado
        guardado = await asyncio.to_thread(_buscar, identificador, cnpj)
    except Exception as e:
        logger.warning(f"[PEDIDOS-GUARDADOS] Falha no banco: {type(e).__name__}")
        return resultado

    if not guardado:
        return resultado
    logger.info("[PEDIDOS-GUARDADOS] API sem expedição em aberto; usando o pedido guardado")
    return {**guardado, "source": FONTE}
