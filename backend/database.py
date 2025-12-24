from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, Enum, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Handle Render's postgres:// vs postgresql:// issue
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
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
        }


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String(320), unique=True, nullable=False)
    name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    saved_articles = relationship("SavedArticle", back_populates="user")
    reading_history = relationship("ReadingHistory", back_populates="user")


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
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    article_id = Column(String, ForeignKey("articles.id"), nullable=False)
    action = Column(String(50))  # 'viewed', 'clicked', 'dismissed'
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="reading_history")


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
