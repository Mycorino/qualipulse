from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.database import Base


class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    participant_id = Column(
        String(36), ForeignKey("participants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operation = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False)
    # Claude token fields
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    # TTS field
    characters = Column(Integer, nullable=True)
    # STT field
    audio_seconds = Column(Float, nullable=True)
    # Cost
    cost_usd = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
