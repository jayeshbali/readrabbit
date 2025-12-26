from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
import random
import os
import uuid
from contextlib import asynccontextmanager

# Database imports
from database import get_db, init_db, Article, SourceType, ArticleStatus, SessionLocal

# Check if database is configured
DATABASE_URL = os.getenv("DATABASE_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database tables
    if DATABASE_URL:
        init_db()
        # Seed with initial articles if empty
        seed_articles_if_empty()
    yield
    # Shutdown: nothing to do


app = FastAPI(title="ReadRabbit API", lifespan=lifespan)

# CORS for frontend
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Pydantic Models ==============

class ArticleCreate(BaseModel):
    title: str
    url: str
    source: Optional[str] = None
    author: Optional[str] = None
    summary: Optional[str] = None
    topics: Optional[list[str]] = []
    read_time: Optional[int] = None
    source_type: Optional[str] = SourceType.MANUAL.value


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    source: Optional[str] = None
    author: Optional[str] = None
    summary: Optional[str] = None
    topics: Optional[list[str]] = None
    read_time: Optional[int] = None
    status: Optional[str] = None


# ============== Seed Data ==============

SEED_ARTICLES = [
    {
        "title": "The Age of AI Has Begun",
        "url": "https://www.gatesnotes.com/The-Age-of-AI-Has-Begun",
        "source": "Gates Notes",
        "author": "Bill Gates",
        "read_time": 12,
        "topics": ["AI", "Technology", "Future"],
        "summary": "Bill Gates on why AI is as revolutionary as mobile phones and the Internet.",
    },
    {
        "title": "How to Do Great Work",
        "url": "http://paulgraham.com/greatwork.html",
        "source": "Paul Graham",
        "author": "Paul Graham",
        "read_time": 45,
        "topics": ["Productivity", "Career", "Philosophy"],
        "summary": "A comprehensive guide on doing meaningful work and finding what to work on.",
    },
    {
        "title": "The Friendship That Made Google Huge",
        "url": "https://www.newyorker.com/magazine/2018/12/10/the-friendship-that-made-google-huge",
        "source": "The New Yorker",
        "author": "James Somers",
        "read_time": 25,
        "topics": ["Technology", "Engineering", "Profiles"],
        "summary": "The story of Jeff Dean and Sanjay Ghemawat, the engineering duo behind Google's infrastructure.",
    },
    {
        "title": "1000 True Fans",
        "url": "https://kk.org/thetechnium/1000-true-fans/",
        "source": "The Technium",
        "author": "Kevin Kelly",
        "read_time": 8,
        "topics": ["Creator Economy", "Business", "Internet"],
        "summary": "You don't need millions of customers. You need 1000 true fans.",
    },
    {
        "title": "The Munger Operating System",
        "url": "https://fs.blog/munger-operating-system/",
        "source": "Farnam Street",
        "author": "Shane Parrish",
        "read_time": 15,
        "topics": ["Mental Models", "Decision Making", "Investing"],
        "summary": "Charlie Munger's approach to life, decision-making, and continuous learning.",
    },
    {
        "title": "Taste for Makers",
        "url": "http://paulgraham.com/taste.html",
        "source": "Paul Graham",
        "author": "Paul Graham",
        "read_time": 10,
        "topics": ["Design", "Aesthetics", "Creation"],
        "summary": "What is good design? How do you develop taste? Paul Graham explores.",
    },
    {
        "title": "The Psychology of Money",
        "url": "https://collabfund.com/blog/the-psychology-of-money/",
        "source": "Collaborative Fund",
        "author": "Morgan Housel",
        "read_time": 20,
        "topics": ["Finance", "Psychology", "Behavior"],
        "summary": "Why personal finance is more about behavior than intelligence.",
    },
    {
        "title": "Speed Matters",
        "url": "https://jsomers.net/blog/speed-matters",
        "source": "James Somers",
        "author": "James Somers",
        "read_time": 6,
        "topics": ["Productivity", "Software", "Workflow"],
        "summary": "Why being fast changes how you think and what you're willing to attempt.",
    },
    {
        "title": "The Days Are Long But The Decades Are Short",
        "url": "https://blog.samaltman.com/the-days-are-long-but-the-decades-are-short",
        "source": "Sam Altman Blog",
        "author": "Sam Altman",
        "read_time": 4,
        "topics": ["Life Advice", "Philosophy", "Aging"],
        "summary": "36 pieces of life advice on Sam Altman's 30th birthday.",
    },
    {
        "title": "What I Wish Someone Had Told Me",
        "url": "https://blog.samaltman.com/what-i-wish-someone-had-told-me",
        "source": "Sam Altman Blog",
        "author": "Sam Altman",
        "read_time": 5,
        "topics": ["Startups", "Career", "Advice"],
        "summary": "Sam Altman's condensed advice for founders and ambitious people.",
    },
]


def seed_articles_if_empty():
    """Seed the database with initial articles if it's empty."""
    if not SessionLocal:
        return
    
    db = SessionLocal()
    try:
        count = db.query(Article).count()
        if count == 0:
            print("Seeding database with initial articles...")
            for article_data in SEED_ARTICLES:
                article = Article(
                    id=str(uuid.uuid4()),
                    title=article_data["title"],
                    url=article_data["url"],
                    source=article_data.get("source"),
                    author=article_data.get("author"),
                    summary=article_data.get("summary"),
                    topics=article_data.get("topics", []),
                    read_time=article_data.get("read_time"),
                    source_type=SourceType.MANUAL.value,
                    status=ArticleStatus.UNREAD.value,
                )
                db.add(article)
            db.commit()
            print(f"Seeded {len(SEED_ARTICLES)} articles!")
    finally:
        db.close()


# ============== In-Memory Fallback (when no DB) ==============

# Track shown articles (in-memory, for both DB and non-DB modes)
shown_article_ids: set[str] = set()


# ============== API Endpoints ==============

@app.get("/")
def read_root():
    return {
        "status": "ok",
        "app": "ReadRabbit API",
        "database": "connected" if DATABASE_URL else "not configured (using mock data)"
    }


@app.get("/api/articles")
def list_articles(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all articles with optional filtering."""
    query = db.query(Article)
    
    if status:
        query = query.filter(Article.status == status)
    if source_type:
        query = query.filter(Article.source_type == source_type)
    
    articles = query.offset(skip).limit(limit).all()
    return {"articles": [a.to_dict() for a in articles], "total": query.count()}


@app.get("/api/articles/random")
def get_random_articles(count: int = 4, db: Session = Depends(get_db)):
    """Get random articles, avoiding recently shown ones."""
    
    # Get articles not yet shown, excluding dismissed
    query = db.query(Article).filter(
        Article.status != ArticleStatus.DISMISSED.value,
        ~Article.id.in_(shown_article_ids) if shown_article_ids else True
    )
    
    available = query.all()
    
    # If we've shown everything, reset
    if len(available) < count:
        shown_article_ids.clear()
        available = db.query(Article).filter(
            Article.status != ArticleStatus.DISMISSED.value
        ).all()
    
    # Random sample
    selected = random.sample(available, min(count, len(available)))
    
    # Track shown
    for article in selected:
        shown_article_ids.add(article.id)
    
    return {"articles": [a.to_dict() for a in selected]}


@app.get("/api/articles/{article_id}")
def get_article(article_id: str, db: Session = Depends(get_db)):
    """Get a single article by ID."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article.to_dict()


@app.post("/api/articles")
def create_article(article: ArticleCreate, db: Session = Depends(get_db)):
    """Create a new article."""
    # Check if URL already exists
    existing = db.query(Article).filter(Article.url == article.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Article with this URL already exists")
    
    db_article = Article(
        id=str(uuid.uuid4()),
        title=article.title,
        url=article.url,
        source=article.source,
        author=article.author,
        summary=article.summary,
        topics=article.topics,
        read_time=article.read_time,
        source_type=article.source_type,
        status=ArticleStatus.UNREAD.value,
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article.to_dict()


@app.put("/api/articles/{article_id}")
def update_article(article_id: str, article: ArticleUpdate, db: Session = Depends(get_db)):
    """Update an existing article."""
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    update_data = article.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_article, key, value)
    
    db.commit()
    db.refresh(db_article)
    return db_article.to_dict()


@app.delete("/api/articles/{article_id}")
def delete_article(article_id: str, db: Session = Depends(get_db)):
    """Delete an article."""
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    db.delete(db_article)
    db.commit()
    return {"status": "deleted", "article_id": article_id}


@app.post("/api/articles/{article_id}/dismiss")
def dismiss_article(article_id: str, db: Session = Depends(get_db)):
    """Mark an article as dismissed (don't show again)."""
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    db_article.status = ArticleStatus.DISMISSED.value
    db.commit()
    shown_article_ids.add(article_id)
    return {"status": "dismissed", "article_id": article_id}


@app.post("/api/articles/reset")
def reset_shown():
    """Reset shown articles tracking."""
    shown_article_ids.clear()
    return {"status": "reset"}


# ============== Admin Endpoints ==============

@app.get("/api/admin/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get database statistics."""
    total = db.query(Article).count()
    by_source_type = db.query(
        Article.source_type, func.count(Article.id)
    ).group_by(Article.source_type).all()
    by_status = db.query(
        Article.status, func.count(Article.id)
    ).group_by(Article.status).all()
    
    return {
        "total_articles": total,
        "by_source_type": {s: c for s, c in by_source_type},
        "by_status": {s: c for s, c in by_status},
        "shown_this_session": len(shown_article_ids),
    }


# ============== AI-Powered Endpoints ==============

class URLInput(BaseModel):
    url: str


@app.post("/api/admin/extract-metadata")
async def extract_metadata(input: URLInput):
    """Extract article metadata from a URL using AI."""
    from ai_service import extract_article_metadata, fetch_url_content
    
    try:
        # Fetch page content to help AI
        html_content = await fetch_url_content(input.url)
        
        # Extract metadata using Groq
        metadata = await extract_article_metadata(input.url, html_content)
        
        return {
            "success": True,
            "url": input.url,
            "metadata": metadata
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/add-article-smart")
async def add_article_smart(input: URLInput, db: Session = Depends(get_db)):
    """Fetch URL, extract metadata with AI, and add to database."""
    from ai_service import extract_article_metadata, fetch_url_content
    
    # Check if URL already exists
    existing = db.query(Article).filter(Article.url == input.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Article with this URL already exists")
    
    try:
        # Fetch and extract
        html_content = await fetch_url_content(input.url)
        metadata = await extract_article_metadata(input.url, html_content)
        
        # Create article
        db_article = Article(
            id=str(uuid.uuid4()),
            title=metadata.get("title", "Untitled"),
            url=input.url,
            source=metadata.get("source"),
            author=metadata.get("author"),
            summary=metadata.get("summary"),
            topics=metadata.get("topics", []),
            read_time=metadata.get("read_time"),
            source_type=SourceType.MANUAL.value,
            status=ArticleStatus.UNREAD.value,
        )
        db.add(db_article)
        db.commit()
        db.refresh(db_article)
        
        return {
            "success": True,
            "article": db_article.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Discovery Agent Endpoints ==============

class DiscoveryInput(BaseModel):
    content: str  # URL or free text
    input_type: str = "article"  # article, podcast, tweet, text
    max_results: int = 5
    auto_save: bool = False  # Whether to automatically save recommendations


@app.post("/api/agent/discover")
async def discover_articles(input: DiscoveryInput, db: Session = Depends(get_db)):
    """
    Run the discovery agent to find similar articles.
    
    Input types:
    - article: URL to an article you liked
    - podcast: URL to a podcast episode
    - tweet: URL to a tweet/thread
    - text: Free text describing what you want
    """
    from discovery_agent import run_discovery_agent
    
    try:
        # Get existing URLs to avoid duplicates
        existing = db.query(Article.url).all()
        existing_urls = [url for (url,) in existing]
        
        # Run the agent
        result = await run_discovery_agent(
            input_content=input.content,
            input_type=input.input_type,
            max_results=input.max_results,
            existing_urls=existing_urls,
        )
        
        # Auto-save if requested
        saved_articles = []
        if input.auto_save and result.get("recommendations"):
            for rec in result["recommendations"]:
                try:
                    # Check again for duplicates
                    if db.query(Article).filter(Article.url == rec["url"]).first():
                        continue
                    
                    db_article = Article(
                        id=str(uuid.uuid4()),
                        title=rec["title"],
                        url=rec["url"],
                        source=rec.get("source"),
                        author=rec.get("author"),
                        summary=rec.get("summary"),
                        topics=rec.get("topics", []),
                        read_time=rec.get("read_time"),
                        source_type=SourceType.AI_SUGGESTED.value,
                        status=ArticleStatus.UNREAD.value,
                    )
                    db.add(db_article)
                    saved_articles.append(db_article.to_dict())
                except Exception:
                    continue
            
            db.commit()
            result["saved_articles"] = saved_articles
            result["saved_count"] = len(saved_articles)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/save-recommendation")
async def save_recommendation(article: ArticleCreate, db: Session = Depends(get_db)):
    """Save a single recommendation from the discovery agent."""
    # Check if URL already exists
    existing = db.query(Article).filter(Article.url == article.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Article already exists")
    
    db_article = Article(
        id=str(uuid.uuid4()),
        title=article.title,
        url=article.url,
        source=article.source,
        author=article.author,
        summary=article.summary,
        topics=article.topics,
        read_time=article.read_time,
        source_type=SourceType.AI_SUGGESTED.value,
        status=ArticleStatus.UNREAD.value,
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    
    return {"success": True, "article": db_article.to_dict()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
