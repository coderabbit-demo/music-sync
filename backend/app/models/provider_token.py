from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProviderToken(Base):
    __tablename__ = "provider_tokens"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String(20), nullable=False, unique=True)
    access_token: Mapped[str] = mapped_column(sa.Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_expiry: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    scope: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.CheckConstraint("provider IN ('spotify', 'ytmusic')", name="ck_provider_token_provider"),
    )
