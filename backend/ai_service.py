import os
import httpx
import json
from typing import Optional, List

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Embedding providers (in order of preference)
# 1. Voyage AI - Best quality, free tier (200M tokens/month)
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_EMBEDDING_URL = "https://api.voyageai.com/v1/embeddings"

# 2. OpenAI - Paid fallback
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"

# 3. Hugging Face - Free fallback (no key needed)
HF_API_KEY = os.getenv("HF_API_KEY")  # Optional - works without key but slower
HF_EMBEDDING_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"


async def extract_article_metadata(url: str, html_content: Optional[str] = None) -> dict:
    """
    Use Groq LLM to extract article metadata from a URL.
    Returns: {title, author, source, summary, topics, read_time}
    """
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY not configured")
    
    # If we have HTML content, include a snippet
    content_hint = ""
    if html_content:
        # Take first 5000 chars for better summary generation
        content_hint = f"\n\nHere's the beginning of the article content:\n{html_content[:5000]}"
    
    prompt = f"""Analyze this article URL and extract metadata.

URL: {url}
{content_hint}

Extract the following information and respond ONLY with valid JSON (no markdown, no explanation):

{{
    "title": "The article title",
    "author": "Author name (or null if unknown)",
    "source": "Publication/website name (e.g., 'Paul Graham', 'The New Yorker', 'Farnam Street')",
    "summary": "A rich 50-80 word summary (see guidelines below)",
    "topics": ["Topic1", "Topic2", "Topic3"],
    "read_time": estimated_minutes_to_read
}}

SUMMARY GUIDELINES (IMPORTANT - this is used for recommendations):
Write a 50-80 word summary that captures:
1. The main topic and central thesis/argument
2. Key insights or surprising takeaways
3. The author's unique perspective or approach
4. Why this matters to the reader

Example good summary:
"Bill Gates argues that AI represents the most important technological advance since the graphical user interface. He explores how AI will transform education through personalized tutoring, revolutionize healthcare in developing countries, and boost productivity across industries. Gates shares his first experience with GPT and why he believes we're at an inflection point similar to the birth of the PC era."

For topics, choose 2-4 relevant tags from categories like: AI, Technology, Productivity, Career, Philosophy, Business, Psychology, Writing, Startups, Finance, Science, Design, Leadership, Health, Creativity, Mental Models, Decision Making, Engineering, Economics.

For read_time, estimate based on typical article length (5-10 min for blogs, 15-30 min for long-form).

Respond with ONLY the JSON object, nothing else."""

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Retry logic for rate limits
        for attempt in range(3):
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",  # Higher rate limit
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that extracts article metadata. Always respond with valid JSON only."
                        },
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            
            if response.status_code == 429:
                # Rate limited - wait and retry
                import asyncio
                wait_time = (attempt + 1) * 15
                await asyncio.sleep(wait_time)
                continue
            
            if response.status_code != 200:
                raise Exception(f"Groq API error: {response.status_code} - {response.text}")
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            try:
                # Clean up potential markdown formatting
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                metadata = json.loads(content)
                return metadata
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse LLM response as JSON: {content}")
        
        raise Exception("Rate limit exceeded after 3 retries")


async def fetch_url_content(url: str) -> str:
    """Fetch the HTML content of a URL."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ReadRabbit/1.0)"
            })
            if response.status_code == 200:
                return response.text
        except Exception:
            pass
    return ""


# ============== Embedding Functions ==============

def create_embedding_text(article: dict) -> str:
    """
    Create rich text for embedding from article data.
    
    The quality of recommendations depends on this text!
    We combine multiple fields to capture the article's essence.
    """
    parts = []
    
    # Title (most important - captures the main topic)
    if article.get("title"):
        parts.append(article["title"])
    
    # Topics as context (helps cluster similar content)
    topics = article.get("topics", [])
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    
    # Summary (the meat - captures arguments and insights)
    if article.get("summary"):
        parts.append(article["summary"])
    
    # Source (helps match writing style/perspective)
    if article.get("source"):
        parts.append(f"Source: {article['source']}")
    
    # Author (helps match author style)
    if article.get("author") and article.get("author") != article.get("source"):
        parts.append(f"Author: {article['author']}")
    
    return ". ".join(parts)


async def generate_embedding_voyage(text: str) -> Optional[List[float]]:
    """
    Generate embedding using Voyage AI (FREE tier: 200M tokens/month).
    
    Uses voyage-2 which produces 1024 dimensional vectors.
    Optimized for retrieval and similarity tasks - best quality for recommendations.
    
    Args:
        text: The text to embed
        
    Returns:
        List of 1024 floats representing the embedding, or None if failed
    """
    if not VOYAGE_API_KEY:
        return None
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                VOYAGE_EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {VOYAGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "voyage-2",  # Best balance of quality and speed
                    "input": text,
                    "input_type": "document",  # Optimized for storing documents
                },
            )
            
            if response.status_code != 200:
                print(f"Voyage API error: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            embedding = result["data"][0]["embedding"]
            return embedding
            
        except Exception as e:
            print(f"Error generating Voyage embedding: {e}")
            return None


async def generate_embedding_huggingface(text: str) -> Optional[List[float]]:
    """
    Generate embedding using Hugging Face Inference API (FREE).
    
    Uses sentence-transformers/all-MiniLM-L6-v2 which produces 384 dimensional vectors.
    Works without API key (slower) or with free HF token (faster).
    
    Args:
        text: The text to embed
        
    Returns:
        List of 384 floats representing the embedding, or None if failed
    """
    headers = {"Content-Type": "application/json"}
    
    # Add API key if available (faster, but works without)
    if HF_API_KEY:
        headers["Authorization"] = f"Bearer {HF_API_KEY}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Hugging Face might need model to warm up, retry a few times
            for attempt in range(3):
                response = await client.post(
                    HF_EMBEDDING_URL,
                    headers=headers,
                    json={"inputs": text, "options": {"wait_for_model": True}},
                )
                
                if response.status_code == 503:
                    # Model is loading, wait and retry
                    import asyncio
                    await asyncio.sleep(5)
                    continue
                
                if response.status_code == 200:
                    result = response.json()
                    # HF returns the embedding directly as a list
                    # For sentence-transformers, it's a single vector
                    if isinstance(result, list) and len(result) > 0:
                        # If nested (batch response), get first
                        if isinstance(result[0], list):
                            return result[0]
                        return result
                    return None
                
                print(f"HuggingFace API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error generating HuggingFace embedding: {e}")
            return None
    
    return None


async def generate_embedding_openai(text: str) -> Optional[List[float]]:
    """
    Generate embedding using OpenAI's API (PAID but higher quality).
    
    Uses text-embedding-3-small which produces 1,536 dimensional vectors.
    Cost: ~$0.02 per 1M tokens
    
    Args:
        text: The text to embed (should be < 8191 tokens)
        
    Returns:
        List of 1,536 floats representing the embedding, or None if failed
    """
    if not OPENAI_API_KEY:
        return None
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                OPENAI_EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "text-embedding-3-small",
                    "input": text,
                },
            )
            
            if response.status_code != 200:
                print(f"OpenAI Embedding API error: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            embedding = result["data"][0]["embedding"]
            return embedding
            
        except Exception as e:
            print(f"Error generating OpenAI embedding: {e}")
            return None


async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding vector for text.
    
    Tries providers in order:
    1. Voyage AI (FREE 200M tokens/mo - 1024 dims, best quality)
    2. Hugging Face (FREE unlimited - 384 dims, good quality)
    3. OpenAI (PAID - 1536 dims, if API key configured)
    
    Args:
        text: The text to embed
        
    Returns:
        List of floats representing the embedding, or None if all providers failed
    """
    # Try Voyage first (free tier, best quality)
    if VOYAGE_API_KEY:
        embedding = await generate_embedding_voyage(text)
        if embedding:
            return embedding
    
    # Fall back to Hugging Face (free, no key needed)
    embedding = await generate_embedding_huggingface(text)
    if embedding:
        return embedding
    
    # Last resort: OpenAI if configured
    if OPENAI_API_KEY:
        embedding = await generate_embedding_openai(text)
        if embedding:
            return embedding
    
    print("Warning: No embedding provider available or all failed")
    return None


async def generate_article_embedding(article: dict) -> Optional[List[float]]:
    """
    Generate embedding for an article.
    
    This is the main function to call when adding/updating articles.
    
    Args:
        article: Dict with title, summary, topics, source, author
        
    Returns:
        Embedding vector (dimensions depend on provider: Voyage=1024, HF=384, OpenAI=1536)
    """
    # Create the text to embed
    embedding_text = create_embedding_text(article)
    
    # Generate and return the embedding
    return await generate_embedding(embedding_text)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Returns:
        Float between -1 and 1, where:
        - 1.0 = identical direction (very similar)
        - 0.0 = perpendicular (unrelated)
        - -1.0 = opposite direction (very different)
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have same length")
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


async def enhance_summary(title: str, current_summary: str, url: str) -> Optional[str]:
    """
    Enhance a short summary into a richer one for better embeddings.
    
    Used to backfill existing articles with better summaries.
    """
    if not GROQ_API_KEY:
        return None
    
    prompt = f"""Enhance this article summary to be more detailed (50-80 words).

Title: {title}
URL: {url}
Current summary: {current_summary}

Write an enhanced summary that captures:
1. The main thesis or argument
2. Key insights or takeaways
3. The author's perspective
4. Why this matters

Respond with ONLY the enhanced summary text, no quotes or explanation."""

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that writes concise, informative article summaries."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.5,
                    "max_tokens": 200,
                },
            )
            
            if response.status_code != 200:
                return None
            
            result = response.json()
            enhanced = result["choices"][0]["message"]["content"].strip()
            
            # Clean up any quotes
            if enhanced.startswith('"') and enhanced.endswith('"'):
                enhanced = enhanced[1:-1]
            
            return enhanced
            
        except Exception as e:
            print(f"Error enhancing summary: {e}")
            return None
