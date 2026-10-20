from enum import Enum
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Iterable, List, Optional
from datetime import datetime


class UserRole(str, Enum):
    """Roles de usuários no sistema"""
    ADMIN = "ADMIN"      # Acesso total + gerenciar usuários
    MANAGER = "MANAGER"  # Gestor: igual ao ADMIN, exceto exclusões e operações de sistema
    CURATOR = "CURATOR"  # Curadoria do catálogo de exames + Menu Principal em somente leitura
    CHECKER = "CHECKER"  # Apenas checagem de exames
    SENDER = "SENDER"    # Apenas enviar documentos (pendentes)
    VIEWER = "VIEWER"    # Visualizador: só o dashboard de indicadores, sem acesso a documentos


# Papéis sem clinic_id, que leem documentos de TODAS as clínicas. O SENDER é o
# único preso a uma clínica. Fonte única: antes esta lista era copiada em três
# lugares (rota de documentos e duas consultas), e um papel novo precisava ser
# lembrado em cada um — esquecer um deles fazia o papel cair no ramo do SENDER.
GLOBAL_READ_ROLES = frozenset({
    UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR,
})


# Um usuário pode ter mais de um cargo (`roles`), e `role` continua existindo
# como o PAPEL PRINCIPAL: o mais forte da lista, nesta ordem.
#
# O principal não é cosmético. É ele que vai para `audit_logs.user_role`, e a
# consulta do dashboard só reconhece revisão humana quando ele é ADMIN, CHECKER
# ou MANAGER — por isso CHECKER vem antes de CURATOR: quem acumula os dois
# continua tendo a revisão contada. E SENDER vem depois de todo cargo que lê
# documentos, de modo que o principal só é SENDER quando nenhum outro cargo
# dá leitura de documento; todo `role == SENDER` que recorta dado por clínica
# continua certo sem mudar uma linha.
#
# VIEWER fica DEPOIS do SENDER, e não por ser "menor": se viesse antes, o
# Enviador + Visualizador teria principal VIEWER e escaparia de todo recorte
# `role == SENDER` (ler documento de outra clínica, por exemplo). Como o VIEWER
# não dá acesso a documento nenhum, deixá-lo por último não tira nada de
# ninguém — o principal só é VIEWER quando ele é o único cargo.
#
# Permissão é outra coisa: para PODER algo, basta ter o cargo em qualquer
# posição da lista (ver `User.tem_papel` e `_exigir_papel` em core/auth.py).
PRECEDENCIA_PAPEIS = (
    UserRole.ADMIN, UserRole.MANAGER, UserRole.CHECKER, UserRole.CURATOR, UserRole.SENDER,
    UserRole.VIEWER,
)


# Cargo que outro já contém não se acumula com ele: "Gestor + Visualizador"
# não dá nada além do Gestor sozinho, e a lista dizia o contrário a quem a lia.
# O ADMIN contém todos; o MANAGER contém checagem, envio e dashboard
# (`require_checker`, `require_sender` e `DASHBOARD_ROLES` em core/auth.py).
#
# O SENDER entra mesmo prendendo o usuário a uma clínica: decisão de produto
# (out/2026). Ninguém usava a combinação, e o ADMIN/MANAGER que envia segue o
# caminho de quem não tem clínica.
#
# Espelho em front-end/hooks/usePermissions.ts (`CARGOS_CONTIDOS`). Mude os dois
# juntos — e ao dar acesso novo ao MANAGER, veja se ele passou a conter mais um.
CARGOS_CONTIDOS: dict[UserRole, frozenset[UserRole]] = {
    UserRole.ADMIN: frozenset(UserRole) - {UserRole.ADMIN},
    UserRole.MANAGER: frozenset({UserRole.CHECKER, UserRole.SENDER, UserRole.VIEWER}),
}


def cargo_que_contem(papel: UserRole, papeis: Iterable[UserRole | str]) -> Optional[UserRole]:
    """O cargo da lista que já contém `papel`, ou None."""
    for outro in normalizar_papeis(papeis):
        if papel in CARGOS_CONTIDOS.get(outro, ()):
            return outro
    return None


def normalizar_papeis(papeis: Iterable[UserRole | str]) -> List[UserRole]:
    """Sem repetição e na ordem de `PRECEDENCIA_PAPEIS`: o primeiro é o principal."""
    conjunto = {UserRole(p) for p in papeis}
    return [p for p in PRECEDENCIA_PAPEIS if p in conjunto]


def papel_principal(papeis: Iterable[UserRole | str]) -> UserRole:
    normalizados = normalizar_papeis(papeis)
    if not normalizados:
        raise ValueError("O usuário precisa ter pelo menos um cargo")
    return normalizados[0]


class User(BaseModel):
    """Modelo de usuário do sistema"""
    id: Optional[str] = None
    email: EmailStr
    name: str
    # Papel principal, derivado de `roles` (ver PRECEDENCIA_PAPEIS). Quem só
    # informa `role` — linha anterior à migração 012, teste, token antigo —
    # ganha `roles = [role]`.
    role: UserRole = UserRole.CHECKER
    roles: List[UserRole] = Field(default_factory=list)
    is_active: bool = True
    clinic_id: Optional[str] = None  # Obrigatório quando um dos cargos é SENDER; NULL nos demais casos
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _alinhar_papeis(self) -> "User":
        self.roles = normalizar_papeis(self.roles or [self.role])
        self.role = self.roles[0]
        return self

    def tem_papel(self, *papeis: UserRole) -> bool:
        """Tem pelo menos um dos cargos, em qualquer posição da lista."""
        return any(p in self.roles for p in papeis)

    class Config:
        json_schema_extra = {
            "example": {
                "email": "usuario@grupobrmed.com.br",
                "name": "João Silva",
                "role": "CHECKER",
                "roles": ["CHECKER", "CURATOR"],
                "is_active": True
            }
        }


class UserCreate(BaseModel):
    """Schema para criação de usuário.

    `roles` é a forma nova; `role` sozinho continua aceito para quem ainda
    manda um cargo só. Com os dois, vale `roles`.
    """
    email: EmailStr
    name: str
    role: Optional[UserRole] = None
    roles: Optional[List[UserRole]] = None
    clinic_id: Optional[str] = None  # Obrigatório quando um dos cargos é SENDER

    def papeis(self) -> List[UserRole]:
        return normalizar_papeis(self.roles or [self.role or UserRole.CHECKER])

    class Config:
        json_schema_extra = {
            "example": {
                "email": "novo@grupobrmed.com.br",
                "name": "Novo Usuário",
                "roles": ["CHECKER", "SENDER"],
                "clinic_id": "id-da-clinica"
            }
        }


class UserUpdate(BaseModel):
    """Schema para atualização de usuário. Cargos: ver `UserCreate`."""
    name: Optional[str] = None
    role: Optional[UserRole] = None
    roles: Optional[List[UserRole]] = None
    is_active: Optional[bool] = None
    clinic_id: Optional[str] = None

    def papeis(self) -> Optional[List[UserRole]]:
        """Os cargos pedidos, ou None quando a edição não mexe neles."""
        if self.roles is not None:
            return normalizar_papeis(self.roles)
        if self.role is not None:
            return [self.role]
        return None

    class Config:
        json_schema_extra = {
            "example": {
                "roles": ["MANAGER", "CURATOR"],
                "is_active": True
            }
        }


class UserInDB(User):
    """Usuário com informações adicionais do banco"""
    hashed_password: Optional[str] = None  # Para futuro, se implementar senha


class TokenData(BaseModel):
    """Dados decodificados do JWT token"""
    email: EmailStr
    role: UserRole
    name: str
    clinic_id: Optional[str] = None  # NULL para CHECKER/ADMIN
