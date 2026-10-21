"""
Endpoints para gerenciamento de clínicas credenciadas.
Apenas administradores podem gerenciar clínicas.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.core.auth import require_admin, require_management, get_current_user
from app.core.database import user_db
from app.core import metrics
from app.models.user import User, UserRole, GLOBAL_READ_ROLES
from app.models.clinic import (
    Clinic,
    ClinicaVinculada,
    ClinicCreate,
    ClinicUpdate,
    CredenciadoBrnetOpcao,
)
from app.core.pii import mask_identifier
from app.services.rede_credenciada_service import (
    CredenciadoRede,
    RedeCredenciadaIndisponivel,
    buscar_credenciado,
    listar_rede_credenciada,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinics", tags=["Clínicas"])


@router.get("/test-auth")
async def test_auth(current_user: User = Depends(require_management)):
    """Endpoint de teste para verificar autenticação admin"""
    return {
        "authenticated": True,
        "user": {
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
            "clinic_id": current_user.clinic_id
        }
    }


@router.post("/test-create")
async def test_create(
    name: str,
    # Cria clínica sem vínculo com o BRNET, o que só o ADMIN pode fazer.
    current_user: User = Depends(require_admin)
):
    """Endpoint de teste simplificado para criar clínica"""
    try:
        logger.info(f"[TEST] Recebido: name={name}")
        logger.info(f"[TEST] User: {current_user.email} ({current_user.role})")
        logger.info(f"[TEST] user_db type: {type(user_db).__name__}")

        if not hasattr(user_db, 'create_clinic'):
            return {"error": "user_db não tem método create_clinic"}

        clinic = user_db.create_clinic(name=name)
        return {"success": True, "clinic_id": clinic.id}

    except Exception as e:
        logger.exception(f"[TEST] Erro: {e}")
        return {"error": str(e)}


@router.get("", response_model=List[Clinic])
async def list_clinics(
    include_inactive: bool = False,
    current_user: User = Depends(require_management)
):
    """
    Lista todas as clínicas credenciadas.
    Apenas administradores.
    """
    try:
        clinics = user_db.get_all_clinics(include_inactive=include_inactive)
        logger.info(f"[CLINICS] Admin {current_user.email} listou {len(clinics)} clínicas")
        return clinics
    except Exception as e:
        logger.exception(f"Erro ao listar clínicas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar clínicas: {str(e)}"
        )


@router.get("/options")
async def list_clinic_options(current_user: User = Depends(get_current_user)):
    """
    Lista enxuta (id + nome) das clínicas ativas para preencher filtros/combobox.
    Disponível a ADMIN, MANAGER e CHECKER — não expõe CNPJ, telefone ou endereço.
    """
    try:
        # Mesma regra de quem vê documentos de todas as clínicas: as opções servem
        # justamente ao filtro por clínica dessas telas. O SENDER fica de fora
        # porque só enxerga a própria.
        if not current_user.tem_papel(*GLOBAL_READ_ROLES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem permissão para listar opções de clínicas",
            )
        clinics = user_db.get_all_clinics(include_inactive=False)
        options = sorted(
            ({"id": c.id, "name": c.name} for c in clinics),
            key=lambda option: (option["name"] or "").lower(),
        )
        return options
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao listar opções de clínicas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar opções de clínicas"
        )


async def _credenciado_da_rede(brnet_id: str) -> CredenciadoRede:
    """O credenciado escolhido, conferido contra a rede do BRNET."""
    try:
        credenciado = await buscar_credenciado(brnet_id)
    except RedeCredenciadaIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não foi possível consultar a rede credenciada do BRNET: {exc}",
        ) from exc
    if credenciado is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O credenciado {brnet_id} não está na rede credenciada do BRNET.",
        )
    return credenciado


@router.get("/credenciados-brnet", response_model=List[CredenciadoBrnetOpcao])
async def list_credenciados_brnet(current_user: User = Depends(require_management)):
    """
    Rede credenciada do BRNET, para escolher o credenciado de uma clínica.

    Cada credenciado vem com as clínicas do ProntuAI já vinculadas a ele —
    inclusive inativas, porque reativar uma é melhor que cadastrar outra.
    """
    try:
        rede = await listar_rede_credenciada()
    except RedeCredenciadaIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não foi possível consultar a rede credenciada do BRNET: {exc}",
        ) from exc

    vinculadas: dict[str, list[ClinicaVinculada]] = {}
    for clinica in user_db.get_all_clinics(include_inactive=True):
        if clinica.brnet_id:
            vinculadas.setdefault(clinica.brnet_id, []).append(
                ClinicaVinculada(id=clinica.id, name=clinica.name, is_active=clinica.is_active)
            )
    return [
        CredenciadoBrnetOpcao(**c.model_dump(), clinicas=vinculadas.get(c.identificador, []))
        for c in rede
    ]


@router.get("/{clinic_id}/users")
async def list_clinic_users(
    clinic_id: str,
    current_user: User = Depends(require_admin),
):
    """
    Usuários vinculados a uma clínica — só e-mail, nome e situação.

    **Só ADMIN**, de propósito. O resto desta tela é `require_management`, então
    MANAGER continua listando e editando clínicas sem enxergar as pessoas delas.

    Serve à investigação: hoje, para saber quem envia por uma clínica, é preciso
    pegar o nome dela, filtrar no Histórico e tirar o e-mail de um documento.
    Isso só funciona se a clínica já enviou alguma coisa — e a pergunta costuma
    ser justamente por que ela não enviou.

    Inativo entra na lista, marcado. Numa investigação, "o usuário existe mas
    está desativado" é a resposta, não ruído.

    Na prática são os SENDER: os outros papéis têm `clinic_id` nulo porque
    enxergam todas as clínicas.

    Cada usuário vem com `last_upload_at` e `last_login_at`, que são o resto da
    mesma pergunta: saber *quem* está vinculado não diz se a clínica está
    operando. "Tem três SENDER cadastrados, nenhum logou em dois meses" e "tem
    um só, logou hoje e nunca enviou" exigem respostas opostas, e hoje as duas
    aparecem iguais na tela.

    `ultimo_envio_clinica` fecha o caso em que ninguém da lista enviou nada
    porque quem enviava foi desvinculado — o envio continua sendo da clínica.
    """
    try:
        if not user_db.get_clinic_by_id(clinic_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clínica não encontrada",
            )
        usuarios = user_db.list_users(include_inactive=True, clinic_id=clinic_id)
        ordenados = sorted(
            usuarios, key=lambda x: (not x.is_active, (x.name or "").lower())
        )

        # Duas consultas agregadas para a lista inteira, não uma por usuário.
        atividade = user_db.get_users_activity(
            user_ids=[u.id for u in ordenados],
            user_emails=[u.email for u in ordenados],
        )
        ultimo_envio_clinica = user_db.get_clinic_last_upload(clinic_id)

        def _iso(valor):
            return valor.isoformat() if valor else None

        # Sem e-mail nem nome no log: a trilha registra quem consultou e quantos
        # vieram, não quem são.
        logger.info(
            "[CLINICS] %s listou %s usuário(s) da clínica %s",
            current_user.email, len(usuarios), clinic_id,
        )
        return {
            "ultimo_envio_clinica": _iso(ultimo_envio_clinica),
            "usuarios": [
                {
                    "id": u.id,
                    "email": u.email,
                    "name": u.name,
                    "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                    "is_active": u.is_active,
                    "last_upload_at": _iso(
                        atividade.get(u.id, {}).get("last_upload_at")
                    ),
                    "last_login_at": _iso(
                        atividade.get(u.id, {}).get("last_login_at")
                    ),
                }
                for u in ordenados
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao listar usuários da clínica %s: %s", clinic_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar usuários da clínica",
        )


@router.get("/{clinic_id}", response_model=Clinic)
async def get_clinic(
    clinic_id: str,
    current_user: User = Depends(require_management)
):
    """
    Obtém detalhes de uma clínica específica.
    Apenas administradores.
    """
    try:
        clinic = user_db.get_clinic_by_id(clinic_id)

        if not clinic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clínica não encontrada"
            )

        logger.info(f"[CLINICS] Admin {current_user.email} acessou clínica {clinic_id}")
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter clínica {clinic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter clínica: {str(e)}"
        )


@router.post("", response_model=Clinic, status_code=status.HTTP_201_CREATED)
async def create_clinic(
    clinic_data: ClinicCreate,
    current_user: User = Depends(require_management)
):
    """
    Cria uma nova clínica credenciada.
    Apenas administradores.

    A clínica é identificada por ID (UUID). Usuários SENDER são associados a ela posteriormente.
    """
    # Sem credenciado do BRNET, só o ADMIN cadastra: contas internas e
    # credenciado que não está na rede. O Gestor escolhe da lista.
    brnet_id = (clinic_data.brnet_id or "").strip() or None
    cidade, uf = clinic_data.city, clinic_data.state
    email = clinic_data.email
    if brnet_id:
        credenciado = await _credenciado_da_rede(brnet_id)
        brnet_id = credenciado.identificador
        # Cidade e UF vêm da rede, não do formulário: são os do credenciado.
        cidade, uf = credenciado.cidade, credenciado.uf
        # E-mail: o digitado vence (o da rede pode estar desatualizado); vazio,
        # fica o do credenciado — é o que a tela avisa embaixo do campo.
        email = email or credenciado.email
    elif not current_user.tem_papel(UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Escolha o credenciado do BRNET. Só administradores cadastram clínica sem vínculo.",
        )

    try:
        logger.info(f"[CLINICS] Tentativa de criação: name={clinic_data.name}, cnpj={mask_identifier(clinic_data.cnpj)}, brnet_id={brnet_id}")
        logger.info(f"[CLINICS] Admin autenticado: {current_user.email}")

        # Verificar se user_db tem os métodos necessários
        if not hasattr(user_db, 'create_clinic'):
            logger.error("[CLINICS] user_db não tem método create_clinic - usando JSON database?")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Banco de dados não configurado corretamente. DATABASE_URL deve estar configurado."
            )

        clinic = user_db.create_clinic(
            name=clinic_data.name,
            cnpj=clinic_data.cnpj,
            phone=clinic_data.phone,
            address=clinic_data.address,
            city=cidade,
            state=uf,
            brnet_id=brnet_id,
            email=email,
        )

        logger.info(f"[CLINICS] Admin {current_user.email} criou clínica {clinic.id} ({clinic.name})")
        metrics.CLINICAS_CRIADAS.add(1)
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CLINICS] Erro ao criar clínica: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar clínica: {str(e)}"
        )


@router.patch("/{clinic_id}", response_model=Clinic)
async def update_clinic(
    clinic_id: str,
    clinic_data: ClinicUpdate,
    current_user: User = Depends(require_management)
):
    """
    Atualiza dados de uma clínica.
    Apenas administradores.
    """
    try:
        # Verificar se clínica existe
        existing = user_db.get_clinic_by_id(clinic_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clínica não encontrada"
            )

        brnet_id = (clinic_data.brnet_id or "").strip() or None
        cidade, uf = clinic_data.city, clinic_data.state
        if clinic_data.remover_vinculo_brnet:
            if not current_user.tem_papel(UserRole.ADMIN):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Só administradores tiram o vínculo de uma clínica com o BRNET.",
                )
            brnet_id = None
        elif brnet_id:
            credenciado = await _credenciado_da_rede(brnet_id)
            brnet_id = credenciado.identificador
            cidade, uf = credenciado.cidade, credenciado.uf

        clinic = user_db.update_clinic(
            clinic_id=clinic_id,
            name=clinic_data.name,
            cnpj=clinic_data.cnpj,
            phone=clinic_data.phone,
            address=clinic_data.address,
            city=cidade,
            state=uf,
            is_active=clinic_data.is_active,
            brnet_id=brnet_id,
            remover_vinculo_brnet=clinic_data.remover_vinculo_brnet,
        )

        logger.info(f"[CLINICS] Admin {current_user.email} atualizou clínica {clinic_id}")
        return clinic

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao atualizar clínica {clinic_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar clínica: {str(e)}"
        )
