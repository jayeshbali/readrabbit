from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel, Field
from typing import Optional
import random
import os
import uuid
from contextlib import asynccontextmanager

# Database imports
from database import get_db, init_db, Article, SourceType, ArticleStatus, SessionLocal, ReadingHistory, EvalEvent

# Check if database is configured
DATABASE_URL = os.getenv("DATABASE_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database tables
    if DATABASE_URL:
        init_db()
        # Run migrations for new columns
        run_migrations()
        # Seed with initial articles if empty
        seed_articles_if_empty()
    yield
    # Shutdown: nothing to do


def run_migrations():
    """Run database migrations to add new columns."""
    if not SessionLocal:
        return

    db = SessionLocal()
    try:
        # Add embedding column if it doesn't exist
        db.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS embedding FLOAT[]
        """))
        # Add is_saved column if it doesn't exist
        db.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS is_saved INTEGER DEFAULT 0
        """))
        # Add groq_quality_score column if it doesn't exist (Phase 3A)
        db.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS groq_quality_score FLOAT
        """))
        db.commit()
        print("Database migration completed - embedding + is_saved + groq_quality_score columns ready")
    except Exception as e:
        db.rollback()
        print(f"Migration note: {e}")
    finally:
        db.close()

    # Create eval_events table and drop reading_history FK (Phase 3C) — separate transaction
    db = SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS eval_events (
                id VARCHAR PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                article_id VARCHAR REFERENCES articles(id) ON DELETE SET NULL,
                user_id VARCHAR,
                metadata JSON,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        # Drop FK constraint on reading_history.user_id if it exists
        db.execute(text("""
            ALTER TABLE reading_history
            DROP CONSTRAINT IF EXISTS reading_history_user_id_fkey
        """))
        db.commit()
        print("Phase 3 schema ready - eval_events table, reading_history FK removed")
    except Exception as e:
        db.rollback()
        print(f"Phase 3 migration note: {e}")
    finally:
        db.close()


app = FastAPI(title="ReadRabbit API", lifespan=lifespan)

# ============== Health Check ==============

@app.get("/")
def root():
    """Root endpoint - quick health check"""
    return {"status": "ok", "service": "ReadRabbit API"}

@app.get("/api/health")
def health_check():
    """Health check endpoint for wake-up pings"""
    return {"status": "ok"}

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
    allow_origin_regex=r"(https://.*\.vercel\.app|chrome-extension://.*)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Admin Auth ==============

_http_bearer = HTTPBearer(auto_error=False)

def verify_admin(creds: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer)):
    """Verify ADMIN_TOKEN for all /api/admin/* routes."""
    token = os.getenv("ADMIN_TOKEN", "")
    if not token or creds is None or creds.credentials != token:
        raise HTTPException(status_code=403, detail="Forbidden")


# ============== AI Suggest Job Store ==============
# Ephemeral by design — jobs are in-memory for the lifetime of the process.
# If Render restarts mid-job, the frontend gets a 404 on poll and re-triggers.
# Dict shape: { job_id: { "status": "pending"|"complete"|"failed",
#                          "results": [...] | None,
#                          "error": str | None } }
_suggest_jobs: dict = {}


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


@app.post("/api/articles/{article_id}/save")
def save_article(article_id: str, db: Session = Depends(get_db)):
    """Toggle save on an article (signals positive interest for recommendations)."""
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")

    db_article.is_saved = 0 if db_article.is_saved else 1
    db.commit()
    return {"status": "saved" if db_article.is_saved else "unsaved", "article_id": article_id}


@app.post("/api/articles/reset")
def reset_shown():
    """Reset shown articles tracking."""
    shown_article_ids.clear()
    return {"status": "reset"}


# ============== Admin Endpoints ==============

@app.get("/api/admin/stats", dependencies=[Depends(verify_admin)])
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


@app.get("/api/admin/eval", dependencies=[Depends(verify_admin)])
def get_eval_stats(db: Session = Depends(get_db)):
    """Phase 3C: Return eval event counts by type."""
    by_type = db.query(
        EvalEvent.event_type, func.count(EvalEvent.id)
    ).group_by(EvalEvent.event_type).all()

    total = db.query(EvalEvent).count()
    reading_history_total = db.query(ReadingHistory).count()

    return {
        "total_eval_events": total,
        "by_event_type": {et: c for et, c in by_type},
        "reading_history_total": reading_history_total,
    }


# ============== AI-Powered Endpoints ==============

class URLInput(BaseModel):
    url: str


@app.post("/api/admin/extract-metadata", dependencies=[Depends(verify_admin)])
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


@app.post("/api/admin/add-article-smart", dependencies=[Depends(verify_admin)])
async def add_article_smart(input: URLInput, db: Session = Depends(get_db)):
    """Fetch URL, extract metadata with AI, generate embedding, and add to database."""
    return await _save_article_from_url(input.url, db)


@app.post("/api/save-article")
async def save_article_from_extension(input: URLInput, db: Session = Depends(get_db)):
    """Public endpoint for the Chrome extension — no token required."""
    return await _save_article_from_url(input.url, db)


async def _save_article_from_url(url: str, db: Session):
    """Shared logic: fetch URL, extract metadata, generate embedding, persist."""
    from ai_service import extract_article_metadata, fetch_url_content, generate_article_embedding

    # Check if URL already exists
    existing = db.query(Article).filter(Article.url == url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Article with this URL already exists")

    try:
        # Fetch and extract
        html_content = await fetch_url_content(url)
        metadata = await extract_article_metadata(url, html_content)

        # Generate embedding for recommendations
        embedding = await generate_article_embedding(metadata)

        # Create article — is_saved=1 so it appears in the For You curated pool
        db_article = Article(
            id=str(uuid.uuid4()),
            title=metadata.get("title", "Untitled"),
            url=url,
            source=metadata.get("source"),
            author=metadata.get("author"),
            summary=metadata.get("summary"),
            topics=metadata.get("topics", []),
            read_time=metadata.get("read_time"),
            source_type=SourceType.MANUAL.value,
            status=ArticleStatus.UNREAD.value,
            embedding=embedding,
            is_saved=1,
        )
        db.add(db_article)
        db.commit()
        db.refresh(db_article)

        return {
            "success": True,
            "article": db_article.to_dict(),
            "embedding_generated": embedding is not None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Admin Curation Endpoints ==============

class CandidateRequest(BaseModel):
    mode: str = "auto"  # auto, topic, similar, source
    topic: Optional[str] = None
    similar_to: Optional[str] = None  # article_id
    source: Optional[str] = None  # author or publication name
    count: int = 10
    match_library_style: bool = True  # Score against existing library


@app.post("/api/admin/candidates", dependencies=[Depends(verify_admin)])
async def get_candidates(
    request: CandidateRequest,
    db: Session = Depends(get_db)
):
    """
    Find article candidates for admin to review and curate.
    
    Modes:
    - auto: AI discovers based on your library clusters
    - topic: Search for a specific topic
    - similar: Find articles similar to one in your library
    - source: Find more from an author/publication
    
    All candidates are scored against your library for relevance.
    """
    from discovery_agent import search_web
    from recommendation_engine import (
        build_user_profile,
        build_interest_clusters,
        cosine_similarity,
        is_research_paper,
        extract_user_interests
    )
    from ai_service import generate_article_embedding, extract_article_metadata, fetch_url_content
    
    # Get existing library for context
    library_articles = db.query(Article).filter(
        Article.embedding != None
    ).all()
    
    library_dicts = [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "author": a.author,
            "topics": a.topics or [],
            "embedding": a.embedding,
            "created_at": a.created_at
        }
        for a in library_articles
    ]
    
    existing_urls = {a.url for a in library_articles}
    existing_titles = {a.title.lower() for a in library_articles}
    
    # Build search queries based on mode
    search_queries = []
    context_message = ""
    
    if request.mode == "auto":
        # Auto-discover based on library clusters
        clusters = build_interest_clusters(library_dicts)
        top_clusters = clusters[:3]  # Top 3 interest areas
        
        for cluster in top_clusters:
            search_queries.append(f"{cluster.name} articles essays blog")
        
        # Also try extracting common sources
        sources = {}
        for a in library_dicts:
            if a.get("source"):
                sources[a["source"]] = sources.get(a["source"], 0) + 1
        
        top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:2]
        for source, _ in top_sources:
            search_queries.append(f"{source} articles")
        
        context_message = f"Auto-discovering based on clusters: {', '.join(c.name for c in top_clusters)}"
    
    elif request.mode == "topic":
        if not request.topic:
            raise HTTPException(status_code=400, detail="Topic required for topic mode")
        
        search_queries = [
            f"{request.topic} articles essays",
            f"{request.topic} blog posts",
            f"best {request.topic} reads"
        ]
        context_message = f"Searching for topic: {request.topic}"
    
    elif request.mode == "similar":
        if not request.similar_to:
            raise HTTPException(status_code=400, detail="Article ID required for similar mode")
        
        source_article = db.query(Article).filter(Article.id == request.similar_to).first()
        if not source_article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Search based on article's topics and title keywords
        topics = source_article.topics or []
        topic_query = " ".join(topics[:2]) if topics else ""
        
        search_queries = [
            f"{topic_query} articles essays",
            f"similar to {source_article.title[:50]}",
        ]
        
        if source_article.author:
            search_queries.append(f"{source_article.author} other essays")
        
        context_message = f"Finding articles similar to: {source_article.title}"
    
    elif request.mode == "source":
        if not request.source:
            raise HTTPException(status_code=400, detail="Source required for source mode")
        
        # Better queries that find actual articles, not index pages
        # Use "by [Author]" to find bylines
        # Combine with topics from user's library for relevance
        clusters = build_interest_clusters(library_dicts)
        top_topics = [c.name for c in clusters[:2]] if clusters else ["essays", "insights"]
        
        search_queries = [
            f'"{request.source}" essay',  # Exact match in quotes
            f"by {request.source} {top_topics[0]}",  # Author + topic
            f"{request.source} {top_topics[1] if len(top_topics) > 1 else 'writing'} article",
            f"{request.source} best essay must read",
        ]
        context_message = f"Finding articles by: {request.source}"
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")
    
    # Execute searches
    raw_results = []
    for query in search_queries[:4]:  # Limit to 4 queries
        try:
            results = await search_web(query, num_results=10)
            raw_results.extend(results)
        except Exception as e:
            print(f"Search error for '{query}': {e}")
    
    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in raw_results:
        url = r.get("url", "")
        if url not in seen_urls and url not in existing_urls:
            seen_urls.add(url)
            unique_results.append(r)
    
    # Filter and score candidates
    candidates = []
    
    # Build user profile for scoring
    user_profile = build_user_profile(library_dicts, [])
    
    for result in unique_results[:request.count * 2]:  # Get more than needed, filter later
        url = result.get("url", "")
        title = result.get("title", "")
        
        # Skip if title already exists (approximate duplicate)
        if title.lower() in existing_titles:
            continue
        
        # Skip research papers
        if is_research_paper(url, "", title):
            continue
        
        # Skip common non-article pages (URL patterns)
        skip_url_patterns = [
            "/tag/", "/category/", "/author/", "/authors/", "/search",
            "/blog/$", "/articles/$", "/essays/$", "/archive",  # Index pages
            "/page/", "/p/", "?page=",  # Pagination
            "linkedin.com", "twitter.com", "youtube.com", "x.com",
            "amazon.com", "goodreads.com", "wikipedia.org",
            "/about", "/contact", "/subscribe", "/newsletter"
        ]
        url_lower = url.lower()
        if any(pattern.rstrip('$') in url_lower for pattern in skip_url_patterns):
            # Check for exact endings (patterns with $)
            is_index = False
            for pattern in skip_url_patterns:
                if pattern.endswith('$'):
                    clean_pattern = pattern.rstrip('$')
                    if url_lower.endswith(clean_pattern) or url_lower.endswith(clean_pattern + '/'):
                        is_index = True
                        break
                elif pattern in url_lower:
                    is_index = True
                    break
            if is_index:
                continue
        
        # Skip index-like titles
        skip_title_patterns = [
            "articles by", "essays by", "posts by", "writing by",
            "all articles", "all essays", "all posts", "blog home",
            "archive", "index", " | blog", "- blog"
        ]
        title_lower = title.lower()
        if any(pattern in title_lower for pattern in skip_title_patterns):
            continue
        
        # Skip if title is just an author/source name (likely an index page)
        if len(title.split()) <= 2 and title.lower() in ["blog", "essays", "articles", "writing"]:
            continue
        
        candidate = {
            "url": url,
            "title": title,
            "snippet": result.get("snippet", ""),
            "source": extract_source_name(url),
        }
        
        # Score against library if requested
        if request.match_library_style and user_profile.clusters:
            try:
                # Generate embedding for candidate
                embedding = await generate_article_embedding({
                    "title": title,
                    "summary": result.get("snippet", ""),
                    "topics": [],
                    "source": candidate["source"]
                })
                
                if embedding:
                    # Score against each cluster, take best match
                    best_score = 0
                    best_cluster = None
                    
                    for cluster in user_profile.clusters:
                        if cluster.embedding:
                            sim = cosine_similarity(cluster.embedding, embedding)
                            if sim > best_score:
                                best_score = sim
                                best_cluster = cluster.name
                    
                    candidate["match_score"] = round(best_score * 100)
                    candidate["matched_cluster"] = best_cluster
                    candidate["embedding"] = embedding  # Keep for later use
                else:
                    candidate["match_score"] = 0
                    candidate["matched_cluster"] = None
            except Exception as e:
                print(f"Embedding error for {title}: {e}")
                candidate["match_score"] = 0
                candidate["matched_cluster"] = None
        else:
            candidate["match_score"] = None
            candidate["matched_cluster"] = None
        
        candidates.append(candidate)
        
        # Stop if we have enough
        if len(candidates) >= request.count:
            break
    
    # Sort by match score if available
    if request.match_library_style:
        candidates.sort(key=lambda x: x.get("match_score", 0) or 0, reverse=True)
    
    # Remove embeddings from response (too large)
    for c in candidates:
        c.pop("embedding", None)
    
    return {
        "candidates": candidates[:request.count],
        "context": context_message,
        "mode": request.mode,
        "queries_used": search_queries[:4],
        "library_stats": {
            "total_articles": len(library_dicts),
            "clusters": [
                {"name": c.name, "articles": c.article_count}
                for c in (user_profile.clusters[:5] if user_profile.clusters else [])
            ]
        }
    }


@app.post("/api/admin/candidates/approve", dependencies=[Depends(verify_admin)])
async def approve_candidate(
    input: URLInput,
    db: Session = Depends(get_db)
):
    """
    Approve a candidate and add it to the library.
    Same as add-article-smart but semantically for curation flow.
    """
    from ai_service import extract_article_metadata, fetch_url_content, generate_article_embedding
    
    # Check if already exists
    existing = db.query(Article).filter(Article.url == input.url).first()
    if existing:
        return {
            "success": False,
            "message": "Article already in library",
            "article": existing.to_dict()
        }
    
    try:
        # Fetch and extract
        html_content = await fetch_url_content(input.url)
        metadata = await extract_article_metadata(input.url, html_content)
        
        # Generate embedding
        embedding = await generate_article_embedding(metadata)
        
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
            source_type=SourceType.AI_SUGGESTED.value,
            status=ArticleStatus.UNREAD.value,
            embedding=embedding,
        )
        db.add(db_article)
        db.commit()
        db.refresh(db_article)
        
        return {
            "success": True,
            "message": "Article added to library",
            "article": db_article.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Phase 3A: Curated Pool Management ==============

@app.post("/api/admin/manual-add", dependencies=[Depends(verify_admin)])
async def manual_add_to_pool(
    input: URLInput,
    db: Session = Depends(get_db)
):
    """
    Manually add a URL to the curated article pool.
    Fetches metadata + embedding, then saves to the articles table.
    """
    from ai_service import extract_article_metadata, fetch_url_content, generate_article_embedding

    existing = db.query(Article).filter(Article.url == input.url).first()
    if existing:
        return {"success": False, "message": "Article already in pool", "article": existing.to_dict()}

    try:
        html_content = await fetch_url_content(input.url)
        metadata = await extract_article_metadata(input.url, html_content)
        embedding = await generate_article_embedding(metadata)

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
            embedding=embedding,
            is_saved=1,  # Mark as curated pool member so it appears in For You feed
        )
        db.add(db_article)
        db.commit()
        db.refresh(db_article)

        return {"success": True, "message": "Article added to pool", "article": db_article.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SuggestInput(BaseModel):
    context: Optional[str] = None  # optional hint to steer suggestions (topic, theme)
    count: Optional[int] = Field(5, ge=1, le=50)  # cap to prevent runaway AI jobs


async def _run_suggest_job(job_id: str, context: Optional[str], count: int):
    """Background task: run AI discovery and store results in _suggest_jobs."""
    from discovery_agent import run_discovery_agent
    from database import SessionLocal

    try:
        db = SessionLocal()
        try:
            existing_urls = [a.url for a in db.query(Article.url).all()]
        finally:
            db.close()
    except Exception as e:
        _suggest_jobs[job_id] = {"status": "failed", "results": None, "error": f"DB error: {e}"}
        return

    try:
        input_content = context or "Find high-quality articles worth reading and curating"
        result = await run_discovery_agent(
            input_content=input_content,
            input_type="text",
            max_results=count,
            existing_urls=existing_urls,
        )
        _suggest_jobs[job_id] = {
            "status": "complete",
            "results": result.get("recommendations", []),
            "error": None,
        }
    except Exception as e:
        _suggest_jobs[job_id] = {
            "status": "failed",
            "results": None,
            "error": str(e),
        }


@app.post("/api/admin/suggest", dependencies=[Depends(verify_admin)])
async def start_suggest_job(
    input: SuggestInput,
    background_tasks: BackgroundTasks,
):
    """
    Start an async AI Suggest job. Returns a job_id immediately.
    Poll GET /api/admin/suggest/{job_id} for results.
    Jobs are in-memory — a Render restart clears them; just re-trigger.
    """
    # Evict oldest jobs if dict grows large (process restart is the normal GC mechanism)
    if len(_suggest_jobs) > 100:
        oldest = next(iter(_suggest_jobs))
        del _suggest_jobs[oldest]

    job_id = str(uuid.uuid4())
    _suggest_jobs[job_id] = {"status": "pending", "results": None, "error": None}
    background_tasks.add_task(_run_suggest_job, job_id, input.context, input.count)
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/admin/suggest/{job_id}", dependencies=[Depends(verify_admin)])
def poll_suggest_job(job_id: str):
    """
    Poll the status of an AI Suggest job.
    Returns {status: 'pending'|'complete'|'failed', results: [...], error: str|None}.
    Returns 404 if the job_id is unknown (process restarted — re-trigger).
    """
    job = _suggest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found — process may have restarted. Re-trigger.")
    return job


def extract_source_name(url: str) -> str:
    """Extract readable source name from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        
        # Known source mappings
        source_map = {
            "paulgraham.com": "Paul Graham",
            "fs.blog": "Farnam Street",
            "gatesnotes.com": "Gates Notes",
            "waitbutwhy.com": "Wait But Why",
            "stratechery.com": "Stratechery",
            "seths.blog": "Seth Godin",
            "perell.com": "David Perell",
            "jamesclear.com": "James Clear",
            "sahilbloom.com": "Sahil Bloom",
            "collabfund.com": "Collaborative Fund",
            "avc.com": "AVC (Fred Wilson)",
            "ben-evans.com": "Ben Evans",
            "eugenewei.com": "Eugene Wei",
            "ribbonfarm.com": "Ribbonfarm",
            "lesswrong.com": "LessWrong",
            "overcomingbias.com": "Overcoming Bias",
            "marginalrevolution.com": "Marginal Revolution",
        }
        
        return source_map.get(domain, domain)
    except:
        return ""


# ============== Database Migration Endpoints ==============

@app.post("/api/admin/migrate-db", dependencies=[Depends(verify_admin)])
def migrate_database(db: Session = Depends(get_db)):
    """
    Run database migrations to add new columns/tables.
    Safe to run multiple times - uses IF NOT EXISTS guards throughout.
    """
    try:
        # Phase 1: embedding column
        db.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS embedding FLOAT[]
        """))

        # Phase 3A: groq quality score on articles
        db.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS groq_quality_score FLOAT
        """))

        # Phase 3B: drop FK constraint on reading_history.user_id so anonymous
        # UUIDs (no users row) can be stored without a FK violation
        db.execute(text("""
            ALTER TABLE reading_history
            DROP CONSTRAINT IF EXISTS reading_history_user_id_fkey
        """))
        db.execute(text("""
            ALTER TABLE reading_history
            ALTER COLUMN user_id DROP NOT NULL
        """))

        # Phase 3C: eval_events table for tracking AI suggestion acceptance,
        # For You CTR, domain diversity, and Groq quality score distribution
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS eval_events (
                id VARCHAR PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                article_id VARCHAR REFERENCES articles(id) ON DELETE SET NULL,
                user_id VARCHAR,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        db.commit()

        return {
            "success": True,
            "message": "Migrations completed: groq_quality_score column, reading_history FK removed, eval_events table created"
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e)
        }


# ============== Embedding Management Endpoints ==============

@app.get("/api/admin/embedding-status", dependencies=[Depends(verify_admin)])
def get_embedding_status(db: Session = Depends(get_db)):
    """Check how many articles have embeddings."""
    total = db.query(Article).count()
    with_embedding = db.query(Article).filter(Article.embedding != None).count()
    without_embedding = total - with_embedding
    
    return {
        "total_articles": total,
        "with_embedding": with_embedding,
        "without_embedding": without_embedding,
        "percentage_complete": round((with_embedding / total * 100) if total > 0 else 0, 1),
        "providers": {
            "voyage": "active (free tier)" if os.getenv("VOYAGE_API_KEY") else "not configured",
            "huggingface": "active (free fallback)",
            "openai": "active" if os.getenv("OPENAI_API_KEY") else "not configured"
        },
        "active_provider": (
            "voyage (recommended)" if os.getenv("VOYAGE_API_KEY") 
            else "huggingface (free fallback)"
        ),
        "note": "Voyage AI is recommended: best quality, 200M free tokens/month"
    }


@app.post("/api/admin/test-embedding", dependencies=[Depends(verify_admin)])
async def test_embedding():
    """Test embedding generation with a sample text."""
    from ai_service import (
        generate_embedding, 
        generate_embedding_voyage,
        generate_embedding_huggingface, 
        generate_embedding_openai
    )
    
    test_text = "Artificial intelligence is transforming how we work and live."
    
    results = {
        "test_text": test_text,
        "providers": {}
    }
    
    # Test Voyage (recommended)
    if os.getenv("VOYAGE_API_KEY"):
        try:
            voyage_embedding = await generate_embedding_voyage(test_text)
            if voyage_embedding:
                results["providers"]["voyage"] = {
                    "status": "success",
                    "dimensions": len(voyage_embedding),
                    "sample": voyage_embedding[:5],
                    "note": "Recommended - best quality for retrieval"
                }
            else:
                results["providers"]["voyage"] = {"status": "failed", "error": "No embedding returned"}
        except Exception as e:
            results["providers"]["voyage"] = {"status": "error", "error": str(e)}
    else:
        results["providers"]["voyage"] = {"status": "not configured", "note": "Get free key at voyageai.com"}
    
    # Test Hugging Face (free fallback)
    try:
        hf_embedding = await generate_embedding_huggingface(test_text)
        if hf_embedding:
            results["providers"]["huggingface"] = {
                "status": "success",
                "dimensions": len(hf_embedding),
                "sample": hf_embedding[:5]
            }
        else:
            results["providers"]["huggingface"] = {"status": "failed", "error": "No embedding returned"}
    except Exception as e:
        results["providers"]["huggingface"] = {"status": "error", "error": str(e)}
    
    # Test OpenAI if configured
    if os.getenv("OPENAI_API_KEY"):
        try:
            openai_embedding = await generate_embedding_openai(test_text)
            if openai_embedding:
                results["providers"]["openai"] = {
                    "status": "success",
                    "dimensions": len(openai_embedding),
                    "sample": openai_embedding[:5]
                }
            else:
                results["providers"]["openai"] = {"status": "failed", "error": "No embedding returned"}
        except Exception as e:
            results["providers"]["openai"] = {"status": "error", "error": str(e)}
    else:
        results["providers"]["openai"] = {"status": "not configured"}
    
    return results


@app.post("/api/admin/enhance-summaries", dependencies=[Depends(verify_admin)])
async def enhance_summaries(
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """
    Enhance short summaries to be more detailed for better embeddings.
    
    This finds articles with short summaries (<100 chars) and enhances them
    using AI to create richer, more detailed summaries.
    """
    from ai_service import enhance_summary
    
    # Find articles with short summaries
    articles = db.query(Article).filter(
        func.length(Article.summary) < 100
    ).limit(limit).all()
    
    if not articles:
        return {
            "message": "No articles need summary enhancement",
            "enhanced_count": 0
        }
    
    enhanced = []
    failed = []
    
    for article in articles:
        try:
            new_summary = await enhance_summary(
                title=article.title,
                current_summary=article.summary or "",
                url=article.url
            )
            
            if new_summary and len(new_summary) > len(article.summary or ""):
                old_summary = article.summary
                article.summary = new_summary
                db.commit()
                enhanced.append({
                    "id": article.id,
                    "title": article.title,
                    "old_summary": old_summary,
                    "new_summary": new_summary,
                    "old_length": len(old_summary or ""),
                    "new_length": len(new_summary)
                })
            else:
                failed.append({
                    "id": article.id,
                    "title": article.title,
                    "reason": "Enhancement not better than original"
                })
        except Exception as e:
            failed.append({
                "id": article.id,
                "title": article.title,
                "reason": str(e)
            })
    
    return {
        "enhanced_count": len(enhanced),
        "failed_count": len(failed),
        "enhanced": enhanced,
        "failed": failed
    }


@app.post("/api/admin/generate-embeddings", dependencies=[Depends(verify_admin)])
async def generate_embeddings(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Generate embeddings for articles that don't have them.
    
    Process articles in batches to avoid rate limits.
    """
    from ai_service import generate_article_embedding
    import asyncio
    
    # Find articles without embeddings
    articles = db.query(Article).filter(
        Article.embedding == None
    ).limit(limit).all()
    
    if not articles:
        return {
            "message": "All articles already have embeddings",
            "generated_count": 0
        }
    
    generated = []
    failed = []
    
    for article in articles:
        try:
            embedding = await generate_article_embedding({
                "title": article.title,
                "summary": article.summary,
                "topics": article.topics,
                "source": article.source,
                "author": article.author
            })
            
            if embedding:
                article.embedding = embedding
                db.commit()
                generated.append({
                    "id": article.id,
                    "title": article.title,
                    "embedding_dims": len(embedding)
                })
            else:
                failed.append({
                    "id": article.id,
                    "title": article.title,
                    "reason": "Embedding generation returned None"
                })
            
            # Add delay between requests to avoid rate limiting
            await asyncio.sleep(1)
            
        except Exception as e:
            failed.append({
                "id": article.id,
                "title": article.title,
                "reason": str(e)
            })
    
    return {
        "generated_count": len(generated),
        "failed_count": len(failed),
        "generated": generated,
        "failed": failed
    }


@app.post("/api/admin/backfill-all", dependencies=[Depends(verify_admin)])
async def backfill_all(db: Session = Depends(get_db)):
    """
    Backfill all articles: enhance summaries then generate embeddings.
    
    This is a convenience endpoint that:
    1. Enhances all short summaries
    2. Generates embeddings for all articles
    
    Use with caution - can take a while for large libraries!
    """
    from ai_service import enhance_summary, generate_article_embedding
    import asyncio
    
    results = {
        "summaries_enhanced": 0,
        "embeddings_generated": 0,
        "errors": []
    }
    
    # Step 1: Enhance short summaries
    articles_needing_summary = db.query(Article).filter(
        func.length(Article.summary) < 100
    ).all()
    
    for article in articles_needing_summary:
        try:
            new_summary = await enhance_summary(
                title=article.title,
                current_summary=article.summary or "",
                url=article.url
            )
            if new_summary and len(new_summary) > len(article.summary or ""):
                article.summary = new_summary
                results["summaries_enhanced"] += 1
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
        except Exception as e:
            results["errors"].append(f"Summary error for {article.title}: {str(e)}")
    
    db.commit()
    
    # Step 2: Generate embeddings for all articles without them
    articles_needing_embedding = db.query(Article).filter(
        Article.embedding == None
    ).all()
    
    for article in articles_needing_embedding:
        try:
            embedding = await generate_article_embedding({
                "title": article.title,
                "summary": article.summary,
                "topics": article.topics,
                "source": article.source,
                "author": article.author
            })
            if embedding:
                article.embedding = embedding
                results["embeddings_generated"] += 1
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
        except Exception as e:
            results["errors"].append(f"Embedding error for {article.title}: {str(e)}")
    
    db.commit()
    
    return results


# ============== Recommendation Endpoints ==============

@app.get("/api/recommendations")
async def get_recommendations_endpoint(
    count: int = 4,
    explain: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get personalized article recommendations.
    
    Uses interest clusters for better personalization:
    - Multiple interest areas (not single average)
    - Recency weighting (recent saves matter more)
    - Topic diversity (max 2 per topic)
    - 50% on-topic, 50% serendipity
    
    Add ?explain=true to see why recommendations were made.
    """
    from recommendation_engine import (
        build_user_profile, 
        get_recommendations,
        extract_user_interests,
        explain_recommendations
    )
    
    # Get articles the user explicitly saved (bookmarked)
    saved_articles = db.query(Article).filter(
        Article.is_saved == 1
    ).all()

    # Get dismissed articles
    dismissed_articles = db.query(Article).filter(
        Article.status == ArticleStatus.DISMISSED.value
    ).all()

    # If no saves yet, fall back to random articles
    if not saved_articles:
        all_articles = db.query(Article).filter(
            Article.status != ArticleStatus.DISMISSED.value,
            Article.embedding != None
        ).all()
        import random
        random.shuffle(all_articles)
        results = [
            {k: v for k, v in {
                "id": a.id, "title": a.title, "url": a.url,
                "source": a.source, "author": a.author, "summary": a.summary,
                "topics": a.topics or [], "read_time": a.read_time,
                "recommendation_type": "random", "recommendation_score": 0.0
            }.items()}
            for a in all_articles[:count]
        ]
        return {"recommendations": results, "user_interests": [], "profile_stats": {"saved_count": 0, "dismissed_count": len(dismissed_articles), "clusters": [], "top_topics": []}}
    
    # Convert to dicts with created_at for recency weighting
    saved_dicts = [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "author": a.author,
            "summary": a.summary,
            "topics": a.topics or [],
            "embedding": a.embedding,
            "created_at": a.created_at  # For recency weighting
        }
        for a in saved_articles
    ]
    
    dismissed_dicts = [
        {
            "id": a.id,
            "embedding": a.embedding
        }
        for a in dismissed_articles
    ]
    
    # Build user profile with clusters
    user_profile = build_user_profile(saved_dicts, dismissed_dicts)
    
    # Get all articles as candidates
    all_articles = db.query(Article).filter(
        Article.embedding != None
    ).all()
    
    candidate_dicts = [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "author": a.author,
            "summary": a.summary,
            "topics": a.topics or [],
            "read_time": a.read_time,
            "embedding": a.embedding
        }
        for a in all_articles
    ]
    
    # Get recommendations
    recommendations = get_recommendations(
        user_profile=user_profile,
        candidate_articles=candidate_dicts,
        count=count,
        serendipity_ratio=0.5,  # 2 out of 4
        max_per_topic=2  # Diversity enforcement
    )
    
    # Remove embeddings from response
    for rec in recommendations:
        rec.pop("embedding", None)
    
    # Build response
    response = {
        "recommendations": recommendations,
        "user_interests": extract_user_interests(user_profile),
        "profile_stats": {
            "saved_count": len(saved_dicts),
            "dismissed_count": len(dismissed_dicts),
            "clusters": [
                {
                    "name": c.name,
                    "articles": c.article_count,
                    "recency": round(c.recency_weight, 2)
                }
                for c in user_profile.clusters[:5]
            ],
            "top_topics": list(user_profile.topic_counts.items())[:5] if user_profile.topic_counts else []
        }
    }
    
    # Add explanation if requested
    if explain:
        response["explanation"] = explain_recommendations(recommendations, user_profile)
    
    return response


@app.get("/api/articles/{article_id}/similar")
async def get_similar_articles_endpoint(
    article_id: str,
    count: int = 4,
    db: Session = Depends(get_db)
):
    """
    Get articles similar to a specific article.
    
    Useful for "More like this" functionality.
    """
    from recommendation_engine import get_similar_articles
    
    # Get the source article
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    if not article.embedding:
        raise HTTPException(status_code=400, detail="Article has no embedding")
    
    article_dict = {
        "id": article.id,
        "title": article.title,
        "embedding": article.embedding
    }
    
    # Get all other articles as candidates
    all_articles = db.query(Article).filter(
        Article.embedding != None,
        Article.id != article_id
    ).all()
    
    candidate_dicts = [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "author": a.author,
            "summary": a.summary,
            "topics": a.topics or [],
            "read_time": a.read_time,
            "embedding": a.embedding
        }
        for a in all_articles
    ]
    
    # Get similar articles
    similar = get_similar_articles(
        article=article_dict,
        candidate_articles=candidate_dicts,
        count=count
    )
    
    # Remove embeddings from response
    for s in similar:
        s.pop("embedding", None)
    
    return {
        "source_article": {
            "id": article.id,
            "title": article.title
        },
        "similar_articles": similar
    }


class ForYouBody(BaseModel):
    user_id: Optional[str] = None
    count: Optional[int] = Field(4, ge=1, le=50)


@app.post("/api/recommendations/for-you")
async def get_for_you_recommendations(
    body: ForYouBody,
    db: Session = Depends(get_db)
):
    """
    Get "For You" recommendations from the curated article pool.

    Phase 3B: replaced web-search approach with curated pool retrieval.
    - Cold start (<5 ReadingHistory rows for user): returns full pool, cold_start=True
    - Normal path: scores pool articles against user profile built from reading history
    - Pool empty: returns [], message about empty pool
    - No embeddings in pool: random order fallback
    """
    from recommendation_engine import build_user_profile, get_recommendations

    user_id = body.user_id
    count = body.count or 4

    # Curated pool: articles approved by admin (is_saved=1 or source_type=AI_Suggested with status=Unread)
    pool_articles = db.query(Article).filter(
        Article.is_saved == 1,
        Article.status != ArticleStatus.DISMISSED.value,
    ).all()

    if not pool_articles:
        return {
            "recommendations": [],
            "cold_start": False,
            "message": "No articles in curated pool yet — check back after an admin approves some articles.",
        }

    # Load reading history for this user
    reading_history_rows = []
    if user_id:
        reading_history_rows = db.query(ReadingHistory).filter(
            ReadingHistory.user_id == user_id
        ).all()

    cold_start = len(reading_history_rows) < 5

    if cold_start:
        # Return up to `count` pool articles, random order
        pool_dicts = [a.to_dict() for a in pool_articles]
        random.shuffle(pool_dicts)
        for d in pool_dicts:
            d.pop("embedding", None)
        return {
            "recommendations": pool_dicts[:count],
            "cold_start": True,
            "message": "Read a few more articles so we can personalise your feed.",
        }

    # Build a lookup of article embeddings for history entries (scoped to history IDs only)
    pool_by_id = {a.id: a for a in pool_articles}
    history_article_ids = [rh.article_id for rh in reading_history_rows]
    history_articles = db.query(Article).filter(
        Article.id.in_(history_article_ids),
        Article.embedding.isnot(None),
    ).all() if history_article_ids else []
    embedding_by_id = {a.id: a.embedding for a in history_articles}

    history_dicts = [
        {
            "article_id": rh.article_id,
            "action": rh.action,
            "embedding": embedding_by_id.get(rh.article_id),
            "topics": pool_by_id[rh.article_id].topics if rh.article_id in pool_by_id else [],
        }
        for rh in reading_history_rows
    ]

    # Build user profile from reading history (no saved/dismissed in this flow)
    user_profile = build_user_profile(
        saved_articles=[],
        dismissed_articles=[],
        reading_history=history_dicts,
        weight_map={"clicked": 1.0, "viewed": 0.5, "saved": 2.0, "dismissed": -1.0},
    )

    # Exclude already-seen articles from candidates
    seen_ids = {rh.article_id for rh in reading_history_rows}
    candidate_dicts = [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "author": a.author,
            "summary": a.summary,
            "topics": a.topics or [],
            "read_time": a.read_time,
            "source_type": a.source_type,
            "status": a.status,
            "embedding": a.embedding,
            "groq_quality_score": a.groq_quality_score,
        }
        for a in pool_articles if a.id not in seen_ids
    ]

    if not candidate_dicts:
        return {
            "recommendations": [],
            "cold_start": False,
            "message": "You've seen all articles in the pool — check back soon.",
        }

    # Check if any candidates have embeddings; fall back to random if none
    has_embeddings = any(c.get("embedding") for c in candidate_dicts)
    if not has_embeddings:
        random.shuffle(candidate_dicts)
        for d in candidate_dicts:
            d.pop("embedding", None)
        return {
            "recommendations": candidate_dicts[:count],
            "cold_start": False,
            "message": "Recommendations based on pool order (embeddings not yet available).",
        }

    recommendations = get_recommendations(
        user_profile=user_profile,
        candidate_articles=candidate_dicts,
        count=count,
        serendipity_ratio=0.3,
    )

    for rec in recommendations:
        rec.pop("embedding", None)

    return {
        "recommendations": recommendations,
        "cold_start": False,
    }


class ReadingHistoryInput(BaseModel):
    user_id: str
    article_id: str
    action: str  # 'clicked', 'viewed', 'dismissed'


@app.post("/api/reading-history")
def record_reading_history(input: ReadingHistoryInput, db: Session = Depends(get_db)):
    """Record a reading history event for an anonymous user (localStorage UUID)."""
    valid_actions = {"clicked", "viewed", "dismissed"}
    if input.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {valid_actions}")

    article = db.query(Article).filter(Article.id == input.article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    entry = ReadingHistory(
        id=str(uuid.uuid4()),
        user_id=input.user_id,
        article_id=input.article_id,
        action=input.action,
    )
    db.add(entry)
    db.commit()
    return {"success": True}


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


class ForYouInput(BaseModel):
    max_results: int = 5


@app.post("/api/agent/for-you")
async def get_for_you_recommendations(input: ForYouInput, db: Session = Depends(get_db)):
    """
    Get personalized recommendations based on your entire library.
    Analyzes all your saved articles to build a reading profile,
    then finds new articles that match your interests.
    """
    from discovery_agent import run_for_you_agent
    
    try:
        # Get all articles from the library
        articles = db.query(Article).filter(
            Article.status != ArticleStatus.DISMISSED.value
        ).all()
        articles_data = [a.to_dict() for a in articles]
        
        # Get existing URLs to avoid duplicates
        existing_urls = [a.url for a in articles]
        
        # Run the For You agent
        result = await run_for_you_agent(
            articles=articles_data,
            max_results=input.max_results,
            existing_urls=existing_urls,
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/reading-profile")
async def get_reading_profile(db: Session = Depends(get_db)):
    """
    Get your reading profile without searching for new articles.
    Shows your interest breakdown, favorite sources, and content preferences.
    """
    from discovery_agent import analyze_reading_profile
    
    try:
        # Get all articles from the library
        articles = db.query(Article).filter(
            Article.status != ArticleStatus.DISMISSED.value
        ).all()
        articles_data = [a.to_dict() for a in articles]
        
        if len(articles_data) < 3:
            return {
                "success": False,
                "error": "Need at least 3 articles to build a profile",
                "article_count": len(articles_data)
            }
        
        profile = await analyze_reading_profile(articles_data)
        profile["success"] = True
        profile["article_count"] = len(articles_data)
        
        return profile
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/youtube")
def debug_youtube(url: str):
    """Debug YouTube transcript extraction."""
    from youtube_service import is_youtube_url, get_youtube_transcript, extract_video_id
    
    video_id = extract_video_id(url)
    
    # Try raw API call to see actual error
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        available = [{"language": t.language, "language_code": t.language_code, "is_generated": t.is_generated} for t in transcript_list]
    except Exception as e:
        available = f"Error: {type(e).__name__}: {str(e)}"
    
    return {
        "url": url,
        "is_youtube": is_youtube_url(url),
        "video_id": video_id,
        "available_transcripts": available,
        "full_result": get_youtube_transcript(url)
    }


@app.get("/api/admin/run-tests", dependencies=[Depends(verify_admin)])
def run_tests():
    """Run the test suite and return results. Side project only."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    return {
        "passed": result.returncode == 0,
        "output": result.stdout,
        "errors": result.stderr,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
