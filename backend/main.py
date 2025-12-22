from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import random
import os

app = FastAPI(title="ReadRabbit API")

# CORS for frontend - allow localhost and production URLs
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

# Add production frontend URL from environment
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)
    # Also allow Vercel preview URLs
    allowed_origins.append("https://*.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock Notion database - we'll replace this with real Notion API later
MOCK_ARTICLES = [
    {
        "id": "1",
        "title": "The Age of AI Has Begun",
        "url": "https://www.gatesnotes.com/The-Age-of-AI-Has-Begun",
        "source": "Gates Notes",
        "author": "Bill Gates",
        "read_time": 12,
        "topics": ["AI", "Technology", "Future"],
        "summary": "Bill Gates on why AI is as revolutionary as mobile phones and the Internet.",
    },
    {
        "id": "2",
        "title": "How to Do Great Work",
        "url": "http://paulgraham.com/greatwork.html",
        "source": "Paul Graham",
        "author": "Paul Graham",
        "read_time": 45,
        "topics": ["Productivity", "Career", "Philosophy"],
        "summary": "A comprehensive guide on doing meaningful work and finding what to work on.",
    },
    {
        "id": "3",
        "title": "The Friendship That Made Google Huge",
        "url": "https://www.newyorker.com/magazine/2018/12/10/the-friendship-that-made-google-huge",
        "source": "The New Yorker",
        "author": "James Somers",
        "read_time": 25,
        "topics": ["Technology", "Engineering", "Profiles"],
        "summary": "The story of Jeff Dean and Sanjay Ghemawat, the engineering duo behind Google's infrastructure.",
    },
    {
        "id": "4",
        "title": "1000 True Fans",
        "url": "https://kk.org/thetechnium/1000-true-fans/",
        "source": "The Technium",
        "author": "Kevin Kelly",
        "read_time": 8,
        "topics": ["Creator Economy", "Business", "Internet"],
        "summary": "You don't need millions of customers. You need 1000 true fans.",
    },
    {
        "id": "5",
        "title": "The Munger Operating System",
        "url": "https://fs.blog/munger-operating-system/",
        "source": "Farnam Street",
        "author": "Shane Parrish",
        "read_time": 15,
        "topics": ["Mental Models", "Decision Making", "Investing"],
        "summary": "Charlie Munger's approach to life, decision-making, and continuous learning.",
    },
    {
        "id": "6",
        "title": "Taste for Makers",
        "url": "http://paulgraham.com/taste.html",
        "source": "Paul Graham",
        "author": "Paul Graham",
        "read_time": 10,
        "topics": ["Design", "Aesthetics", "Creation"],
        "summary": "What is good design? How do you develop taste? Paul Graham explores.",
    },
    {
        "id": "7",
        "title": "The Billion Dollar Code",
        "url": "https://www.wired.com/story/the-billion-dollar-code/",
        "source": "Wired",
        "author": "Various",
        "read_time": 18,
        "topics": ["Technology", "Legal", "History"],
        "summary": "The untold story behind Google Earth and the German art project that inspired it.",
    },
    {
        "id": "8",
        "title": "The Psychology of Money",
        "url": "https://collabfund.com/blog/the-psychology-of-money/",
        "source": "Collaborative Fund",
        "author": "Morgan Housel",
        "read_time": 20,
        "topics": ["Finance", "Psychology", "Behavior"],
        "summary": "Why personal finance is more about behavior than intelligence.",
    },
    {
        "id": "9",
        "title": "What I Wish I Had Known When I Started",
        "url": "https://blog.samaltman.com/what-i-wish-someone-had-told-me",
        "source": "Sam Altman Blog",
        "author": "Sam Altman",
        "read_time": 5,
        "topics": ["Startups", "Career", "Advice"],
        "summary": "Sam Altman's condensed advice for founders and ambitious people.",
    },
    {
        "id": "10",
        "title": "The Craft of Writing Effectively",
        "url": "https://www.youtube.com/watch?v=vtIzMaLkCaM",
        "source": "University of Chicago",
        "author": "Larry McEnerney",
        "read_time": 90,
        "topics": ["Writing", "Communication", "Academia"],
        "summary": "A masterclass on why most writing fails and how to make yours matter.",
    },
    {
        "id": "11",
        "title": "Speed Matters",
        "url": "https://jsomers.net/blog/speed-matters",
        "source": "James Somers",
        "author": "James Somers",
        "read_time": 6,
        "topics": ["Productivity", "Software", "Workflow"],
        "summary": "Why being fast changes how you think and what you're willing to attempt.",
    },
    {
        "id": "12",
        "title": "The Days Are Long But The Decades Are Short",
        "url": "https://blog.samaltman.com/the-days-are-long-but-the-decades-are-short",
        "source": "Sam Altman Blog",
        "author": "Sam Altman",
        "read_time": 4,
        "topics": ["Life Advice", "Philosophy", "Aging"],
        "summary": "36 pieces of life advice on Sam Altman's 30th birthday.",
    },
]

# Track which articles have been shown (in-memory for now)
shown_article_ids: set[str] = set()


@app.get("/")
def read_root():
    return {"status": "ok", "app": "ReadRabbit API"}


@app.get("/api/articles/random")
def get_random_articles(count: int = 4):
    """Get random articles, avoiding recently shown ones if possible."""
    available = [a for a in MOCK_ARTICLES if a["id"] not in shown_article_ids]
    
    # If we've shown everything, reset
    if len(available) < count:
        shown_article_ids.clear()
        available = MOCK_ARTICLES.copy()
    
    selected = random.sample(available, min(count, len(available)))
    
    # Track shown articles
    for article in selected:
        shown_article_ids.add(article["id"])
    
    return {"articles": selected}


@app.post("/api/articles/{article_id}/dismiss")
def dismiss_article(article_id: str):
    """Mark an article as 'don't show again'."""
    shown_article_ids.add(article_id)
    return {"status": "dismissed", "article_id": article_id}


@app.post("/api/articles/reset")
def reset_shown():
    """Reset shown articles (for testing)."""
    shown_article_ids.clear()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
