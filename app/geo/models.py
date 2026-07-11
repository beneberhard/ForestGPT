from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.geo.db import Base


class Stand(Base):
    __tablename__ = "stands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    species: Mapped[str | None] = mapped_column(String(100))
    area_ha: Mapped[float | None] = mapped_column(Float)
    age_years: Mapped[int | None] = mapped_column(Integer)
    geometry = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    simulation_runs: Mapped[list["SimulationRun"]] = relationship(
        "SimulationRun",
        back_populates="stand",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="stand")
    observations: Mapped[list["StandObservation"]] = relationship(
        "StandObservation",
        back_populates="stand",
        cascade="all, delete-orphan",
    )


class StandObservation(Base):
    __tablename__ = "stand_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stand_id: Mapped[int] = mapped_column(ForeignKey("stands.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    observer: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, nullable=False)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stand: Mapped[Stand] = relationship("Stand", back_populates="observations")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stand_id: Mapped[int | None] = mapped_column(ForeignKey("stands.id"), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100))
    input_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    stand: Mapped[Stand | None] = relationship("Stand", back_populates="simulation_runs")
    outputs: Mapped[list["SimulationOutput"]] = relationship(
        "SimulationOutput",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class SimulationOutput(Base):
    __tablename__ = "simulation_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    run: Mapped[SimulationRun] = relationship("SimulationRun", back_populates="outputs")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(1000))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stand_id: Mapped[int | None] = mapped_column(ForeignKey("stands.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stand: Mapped[Stand | None] = relationship("Stand", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")
