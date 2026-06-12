"""ORM-модели: Company, Calculation (строго по схеме из CLAUDE.md, раздел 5)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Company(Base):
    __tablename__ = "companies"

    bin: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    revenue_2022: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_2023: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_2024: Mapped[float | None] = mapped_column(Float, nullable=True)

    taxes_2022: Mapped[float | None] = mapped_column(Float, nullable=True)
    taxes_2023: Mapped[float | None] = mapped_column(Float, nullable=True)
    taxes_2024: Mapped[float | None] = mapped_column(Float, nullable=True)

    payroll_2022: Mapped[float | None] = mapped_column(Float, nullable=True)
    payroll_2023: Mapped[float | None] = mapped_column(Float, nullable=True)
    payroll_2024: Mapped[float | None] = mapped_column(Float, nullable=True)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class Calculation(Base):
    __tablename__ = "calculations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_mrp: Mapped[float] = mapped_column(Float, nullable=False)
    company_bins: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    results: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    companies_count: Mapped[int] = mapped_column(Integer, nullable=False)
