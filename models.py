from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Agent(Base):
    __tablename__ = "agents"

    agent_id = Column(String, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    name = Column(String)
    capabilities = Column(String)

    # Relationship to messages sent by this agent
    messages = relationship("Message", back_populates="sender")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(String, ForeignKey("agents.agent_id"))
    recipient_id = Column(String, index=True) # "GLOBAL" or another agent_id
    mission_tag = Column(String)
    intel_body = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    sender = relationship("Agent", back_populates="messages")
