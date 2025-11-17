"""
PostgreSQL implementation of user database.
Migração futura do JSON file-based database.
"""
import os
from typing import List, Optional
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.models.user import User, UserCreate, UserUpdate, UserRole

Base = declarative_base()

class UserModel(Base):
    """SQLAlchemy model for User table."""
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.CHECKER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PostgresUserDatabase:
    """PostgreSQL-based user database implementation."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize PostgreSQL connection.

        Args:
            database_url: PostgreSQL connection string
                         Format: postgresql://user:password@host:port/dbname
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError("DATABASE_URL not set")

        # Neon uses postgresql:// but SQLAlchemy 2.0 requires postgresql+psycopg2://
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        self.engine = create_engine(self.database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

        # Create default admin if database is empty
        self._ensure_default_admin()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def _ensure_default_admin(self):
        """Create default admin user if database is empty."""
        session = self._get_session()
        try:
            count = session.query(UserModel).count()
            if count == 0:
                # Create default admin
                admin = UserModel(
                    id="admin-default",
                    email="gabriel.rodrigues@grupobrmed.com.br",
                    name="Gabriel Rodrigues",
                    role=UserRole.ADMIN,
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(admin)
                session.commit()
                print("✅ Default admin created: gabriel.rodrigues@grupobrmed.com.br")
        finally:
            session.close()

    def _model_to_user(self, model: UserModel) -> User:
        """Convert SQLAlchemy model to Pydantic User."""
        return User(
            id=model.id,
            email=model.email,
            name=model.name,
            role=model.role,
            is_active=model.is_active,
            created_at=model.created_at.isoformat(),
            updated_at=model.updated_at.isoformat()
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.email == email).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        session = self._get_session()
        try:
            model = session.query(UserModel).filter(UserModel.id == user_id).first()
            return self._model_to_user(model) if model else None
        finally:
            session.close()

    def get_all_users(self) -> List[User]:
        """Get all users."""
        session = self._get_session()
        try:
            models = session.query(UserModel).all()
            return [self._model_to_user(m) for m in models]
        finally:
            session.close()

    def create_user(self, email: str, name: str, role: UserRole = UserRole.CHECKER) -> User:
        """Create a new user."""
        session = self._get_session()
        try:
            # Check if user already exists
            existing = session.query(UserModel).filter(UserModel.email == email).first()
            if existing:
                raise ValueError(f"User with email {email} already exists")

            # Validate email domain
            if not email.endswith("@grupobrmed.com.br"):
                raise ValueError("Email must be @grupobrmed.com.br")

            # Create new user
            import uuid
            user_model = UserModel(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                role=role,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(user_model)
            session.commit()
            session.refresh(user_model)

            return self._model_to_user(user_model)
        finally:
            session.close()

    def update_user(self, user_id: str, update: UserUpdate) -> User:
        """Update user."""
        session = self._get_session()
        try:
            user_model = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not user_model:
                raise ValueError(f"User {user_id} not found")

            # Update fields
            if update.name is not None:
                user_model.name = update.name
            if update.role is not None:
                user_model.role = update.role
            if update.is_active is not None:
                user_model.is_active = update.is_active

            user_model.updated_at = datetime.utcnow()

            session.commit()
            session.refresh(user_model)

            return self._model_to_user(user_model)
        finally:
            session.close()

    def delete_user(self, user_id: str) -> bool:
        """Delete user."""
        session = self._get_session()
        try:
            user_model = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not user_model:
                return False

            session.delete(user_model)
            session.commit()
            return True
        finally:
            session.close()
