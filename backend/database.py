from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, Enum, ARRAY, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Handle Render's postgres:// vs postgresql:// issue
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine with connection pool settings for Neon
if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Check connection health before using
        pool_recycle=300,    # Recycle connections every 5 minutes
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    engine = None
    SessionLocal = None

Base = declarative_base()


class SourceType(str, enum.Enum):
    MANUAL = "Manual"
    AI_SUGGESTED = "AI Suggested"
    IMPORTED = "Imported"


class ArticleStatus(str, enum.Enum):
    UNREAD = "Unread"
    READ = "Read"
    DISMISSED = "Dismissed"


class Article(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True)
    title = Column(String(500), nullable=False)
    url = Column(String(2000), nullable=False, unique=True)
    source = Column(String(200))  # Publication name
    author = Column(String(200))
    summary = Column(Text)
    topics = Column(ARRAY(String))  # PostgreSQL array
    read_time = Column(Integer)  # Minutes
    source_type = Column(String(50), default=SourceType.MANUAL.value)
    status = Column(String(50), default=ArticleStatus.UNREAD.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Embedding for recommendations (1536 dimensions for OpenAI text-embedding-3-small)
    embedding = Column(ARRAY(Float))

    # User explicitly saved this article (bookmarked in UI)
    is_saved = Column(Integer, default=0)  # 0=not saved, 1=saved

    # Phase 3A: Groq LLM quality score (0.0–1.0), populated during enrichment
    groq_quality_score = Column(Float, nullable=True)

    # Relationship to saved articles
    saved_by = relationship("SavedArticle", back_populates="article")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "author": self.author,
            "summary": self.summary,
            "topics": self.topics or [],
            "read_time": self.read_time,
            "source_type": self.source_type,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "has_embedding": self.embedding is not None,
            "groq_quality_score": self.groq_quality_score,
        }


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String(320), unique=True, nullable=False)
    name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    saved_articles = relationship("SavedArticle", back_populates="user")


class SavedArticle(Base):
    __tablename__ = "saved_articles"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    article_id = Column(String, ForeignKey("articles.id"), nullable=False)
    saved_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)  # User's personal notes

    # Relationships
    user = relationship("User", back_populates="saved_articles")
    article = relationship("Article", back_populates="saved_by")


class ReadingHistory(Base):
    __tablename__ = "reading_history"

    id = Column(String, primary_key=True)
    # FK dropped in Phase 3B migration — stores anonymous localStorage UUIDs
    # that have no corresponding row in the users table
    user_id = Column(String, nullable=True)
    article_id = Column(String, ForeignKey("articles.id"), nullable=False)
    action = Column(String(50))  # 'viewed', 'clicked', 'dismissed'
    created_at = Column(DateTime, default=datetime.utcnow)


class EvalEvent(Base):
    """Phase 3C: tracks AI suggestion acceptance, For You CTR, domain diversity."""
    __tablename__ = "eval_events"

    id = Column(String, primary_key=True)
    event_type = Column(String(100), nullable=False)  # 'suggest_accepted', 'for_you_click', etc.
    article_id = Column(String, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String, nullable=True)  # anonymous localStorage UUID
    event_metadata = Column("metadata", JSON, nullable=True)   # flexible payload per event type
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    """Dependency for FastAPI to get database session."""
    if SessionLocal is None:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    if engine:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
    else:
        print("No DATABASE_URL configured, skipping database initialization")
