"""
Endpoints de gerenciamento de usuários (ADMIN e MANAGER).

Um usuário pode ter mais de um cargo (`roles`). MANAGER pode listar usuários e
criar/editar só quem tem apenas CHECKER e/ou SENDER — inclusive os dois juntos.
Não ativa nem desativa ninguém (nem pelo DELETE, nem pelo PATCH de
`is_active`) e não mexe em ADMIN, MANAGER, CURATOR ou VIEWER (o Visualizador
do dashboard é atribuído só pelo ADMIN, por decisão de produto).

Clínica: obrigatória quando um dos cargos é SENDER, que é o cargo preso a uma
clínica. Os demais enxergam todas.

Cargo que outro da lista já contém é recusado: o ADMIN contém todos, e o
MANAGER contém CHECKER, SENDER e VIEWER (`CARGOS_CONTIDOS` em models/user.py).
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from app.core.auth import require_admin, require_management
from app.core.database import user_db
from app.core import metrics
from app.models.user import User, UserCreate, UserUpdate, UserRole, cargo_que_contem
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Usuários"])

# O que o MANAGER pode atribuir, em qualquer combinação.
PAPEIS_DO_GESTOR = frozenset({UserRole.CHECKER, UserRole.SENDER})


def _gestor_sem_admin(actor: User) -> bool:
    """MANAGER que não é também ADMIN — é a ele que as travas abaixo se aplicam."""
    return actor.tem_papel(UserRole.MANAGER) and not actor.tem_papel(UserRole.ADMIN)


def _exigir_algum_cargo(papeis: Optional[List[UserRole]]) -> None:
    if papeis is not None and not papeis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecione pelo menos um cargo",
        )


def _assert_manager_cannot_touch_admin(actor: User, target_roles: Optional[List[UserRole]]):
    """
    Impede escalada de privilégio: MANAGER só atribui CHECKER e SENDER.

    CURATOR entra nesta lista porque o MANAGER não acessa o catálogo de exames
    — se pudesse atribuir o papel, bastaria criar um usuário para contornar isso.
    Com vários cargos, a checagem é por CADA cargo pedido: senão bastaria
    esconder um ADMIN no meio de [CHECKER, ADMIN].
    """
    if not target_roles or not _gestor_sem_admin(actor):
        return
    if not set(target_roles) <= PAPEIS_DO_GESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gestores só podem atribuir as roles CHECKER e SENDER"
        )


def _recusar_cargo_contido(papeis: Optional[List[UserRole]]) -> None:
    """
    Cargo que outro da lista já contém não entra (ver `CARGOS_CONTIDOS`).

    Vale só para o que está sendo gravado. Quem já tem a sobreposição (dois
    gestores com Visualizador, em out/2026) continua com ela até a próxima
    edição — a tela abre com o cargo contido desmarcado, e o salvar o tira.
    """
    for papel in papeis or ():
        dono = cargo_que_contem(papel, papeis)
        if dono is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"O cargo {papel.value} já está incluído em {dono.value}",
            )


def _validar_clinica(clinic_id: Optional[str]):
    """Clínica obrigatória para quem tem SENDER, e precisa existir."""
    if not clinic_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuários com o cargo SENDER precisam de uma clínica. Crie uma clínica primeiro.",
        )
    clinic = user_db.get_clinic_by_id(clinic_id)
    if not clinic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Clínica com ID {clinic_id} não encontrada",
        )
    return clinic


def _assert_manager_can_edit(actor: User, target_id: str, user_update: UserUpdate) -> None:
    """
    O que o MANAGER pode fazer ao EDITAR um usuário existente.

    `_assert_manager_cannot_touch_admin` olha só o papel que está sendo
    atribuído; faltava olhar quem está sendo editado e o que muda. Sem isto um
    MANAGER rebaixava outro MANAGER (ou um CURATOR) para SENDER e
    desativava ou reativava contas pelo PATCH — contornando o DELETE, que é só
    de ADMIN, e podendo devolver acesso a quem um ADMIN tinha tirado.

    - alvo: só CHECKER e SENDER, os mesmos papéis que ele pode atribuir;
    - `is_active`: não pode mudar. Mandar o valor atual passa, porque o modal de
      edição da tela sempre envia o campo junto com nome e papel.
    """
    target = user_db.get_user_by_id(target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    # Todos os cargos do alvo, não só o principal: um CHECKER + CURATOR tem
    # principal CHECKER e mesmo assim está fora do alcance do gestor.
    if not set(target.roles) <= PAPEIS_DO_GESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gestores só podem alterar usuários CHECKER e SENDER"
        )
    if user_update.is_active is not None and user_update.is_active != target.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem ativar ou desativar usuários"
        )


@router.get("", response_model=List[User])
async def list_users(
    include_inactive: bool = False,
    admin: User = Depends(require_management)
):
    """
    Lista todos os usuários (ADMIN/MANAGER).

    - **include_inactive**: Se True, inclui usuários inativos
    """
    users = user_db.list_users(include_inactive=include_inactive)
    logger.info(f"Admin {admin.email} listou {len(users)} usuários")
    return users


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    admin: User = Depends(require_management)
):
    """
    Cria um novo usuário (ADMIN/MANAGER; MANAGER só atribui CHECKER e SENDER).

    - **roles**: um ou mais cargos (`role` sozinho ainda é aceito)
    - Com SENDER entre os cargos: clinic_id é OBRIGATÓRIO (clínica existente)
    - Sem SENDER: clinic_id é ignorado e fica NULL
    """
    if user_create.roles is not None:
        _exigir_algum_cargo(user_create.roles)
    papeis = user_create.papeis()
    _assert_manager_cannot_touch_admin(admin, papeis)
    _recusar_cargo_contido(papeis)
    try:
        clinic_id = None
        clinic_name = None

        if UserRole.SENDER in papeis:
            clinic = _validar_clinica(user_create.clinic_id)
            clinic_id, clinic_name = clinic.id, clinic.name
            logger.info(f"Criando usuário SENDER {user_create.email} para clínica {clinic.name} ({clinic_id})")

        user = user_db.create_user(
            email=user_create.email,
            name=user_create.name,
            role=papeis[0],
            roles=papeis,
            clinic_id=clinic_id
        )
        logger.info(
            f"Admin {admin.email} criou usuário {user.email} com cargos "
            f"{[p.value for p in user.roles]} (clinic_id: {clinic_id})"
        )
        metrics.USUARIOS_CRIADOS.add(
            1,
            {
                "role": user.role.value,
                "clinica_id": clinic_id or "sem_clinica",
                "clinica_nome": clinic_name or "sem_clinica",
            },
        )
        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    admin: User = Depends(require_management)
):
    """
    Busca um usuário por ID (ADMIN/MANAGER).
    """
    user = user_db.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user


@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    admin: User = Depends(require_management)
):
    """
    Atualiza um usuário existente (ADMIN/MANAGER; MANAGER não pode alterar ADMIN).

    Pode atualizar:
    - **name**: Nome do usuário
    - **roles**: Cargos (`role` sozinho ainda é aceito)
    - **is_active**: Status ativo/inativo
    - **clinic_id**: Clínica associada (obrigatória enquanto houver SENDER)

    Tirar o SENDER de alguém tira também a clínica. Fora disso a clínica fica
    como está: o envio usa a clínica do próprio usuário, e há ADMIN que envia
    por uma.
    """
    if user_update.roles is not None:
        _exigir_algum_cargo(user_update.roles)
    papeis = user_update.papeis()
    _assert_manager_cannot_touch_admin(admin, papeis)
    if _gestor_sem_admin(admin):
        _assert_manager_can_edit(admin, user_id, user_update)
    _recusar_cargo_contido(papeis)

    alvo = user_db.get_user_by_id(user_id)
    if alvo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    papeis_finais = papeis if papeis is not None else alvo.roles
    clinic_id = user_update.clinic_id
    limpar_clinica = False
    if UserRole.SENDER in papeis_finais:
        clinic_id = _validar_clinica(clinic_id or alvo.clinic_id).id
    elif alvo.tem_papel(UserRole.SENDER):
        # Deixou de ser SENDER: a clínica era dele por causa desse cargo.
        clinic_id, limpar_clinica = None, True
    else:
        clinic_id = None  # não muda a clínica de quem nunca foi SENDER

    try:
        user = user_db.update_user(
            user_id=user_id,
            name=user_update.name,
            roles=papeis,
            is_active=user_update.is_active,
            clinic_id=clinic_id,
            limpar_clinica=limpar_clinica,
        )
        logger.info(f"Admin {admin.email} atualizou usuário {user.email}")
        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin)
):
    """
    Desativa um usuário (soft delete, apenas ADMIN).
    O usuário não é removido do banco, apenas marcado como inativo.
    """
    # Não permitir admin desativar a si mesmo
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar sua própria conta"
        )

    # Lido antes da desativação: criar e atualizar registram o e-mail, só o
    # DELETE registrava o id cru — justamente a ação que bloqueia alguém.
    alvo = user_db.get_user_by_id(user_id)

    try:
        user_db.delete_user(user_id)
        logger.info(
            f"Admin {admin.email} desativou usuário "
            f"{alvo.email if alvo else user_id}"
        )
        return None

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/email/{email}", response_model=User)
async def get_user_by_email(
    email: str,
    admin: User = Depends(require_management)
):
    """
    Busca um usuário por email (ADMIN/MANAGER).
    """
    user = user_db.get_user_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user
