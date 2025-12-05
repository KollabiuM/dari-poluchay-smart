from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Text, ForeignKey, TIMESTAMP, func


# Базовый класс для всех моделей
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50))
    created_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(50))
    interests: Mapped[str] = mapped_column(Text)
    objections: Mapped[str] = mapped_column(Text)
    created_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    content: Mapped[str] = mapped_column(Text)
    analysis_results: Mapped[str] = mapped_column(Text)
    created_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
