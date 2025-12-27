import os
import httpx
import json
from typing import Optional
from ai_service import extract_article_metadata
from youtube_service import is_youtube_url, get_youtube_transcript

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def search_web(query: str, num_results: int = 10) -> list[dict]:
    """Search the web using Serper API."""
    if not SERPER_API_KEY:
        raise Exception("SERPER_API_KEY not configured")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "num": num_results,
            },
        )
        
        if response.status_code != 200:
            raise Exception(f"Serper API error: {response.status_code} - {response.text}")
        
        data = response.json()
        results = data.get("organic", [])
        
        return [
            {
                "title": r.get("title"),
                "url": r.get("link"),
                "snippet": r.get("snippet"),
            }
            for r in results
        ]


async def call_groq(prompt: str, system_prompt: str = None) -> str:
    """Call Groq API for reasoning."""
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY not configured")
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
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
                    "model": "llama-3.3-70b-versatile",  # Higher rate limit than 8b
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
            )
            
            if response.status_code == 429:
                # Rate limited - wait and retry
                import asyncio
                wait_time = (attempt + 1) * 15  # 15s, 30s, 45s
                print(f"[Agent] Rate limited, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            
            if response.status_code != 200:
                raise Exception(f"Groq API error: {response.status_code} - {response.text}")
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
        
        raise Exception("Rate limit exceeded after 3 retries. Please wait a minute and try again.")


async def analyze_input_content(input_text: str, input_type: str) -> dict:
    """
    Analyze the input (article, podcast, tweet, or free text) to extract themes.
    """
    prompt = f"""Analyze this {input_type} and extract the main themes, topics, and concepts.

Input:
{input_text}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
    "main_topics": ["topic1", "topic2", "topic3"],
    "key_concepts": ["concept1", "concept2"],
    "related_fields": ["field1", "field2"],
    "suggested_search_queries": [
        "search query 1 for finding similar articles",
        "search query 2 for finding similar articles",
        "search query 3 for finding similar articles"
    ]
}}

For search queries, create specific queries that would find high-quality long-form articles on these topics. Include terms like "essay", "guide", "deep dive", or author names if relevant."""

    response = await call_groq(prompt)
    
    # Clean and parse JSON
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    
    return json.loads(response.strip())


async def evaluate_search_results(results: list[dict], themes: dict) -> list[dict]:
    """
    Use Groq to evaluate and rank search results for quality and relevance.
    """
    results_text = "\n".join([
        f"{i+1}. {r['title']}\n   URL: {r['url']}\n   Snippet: {r['snippet']}"
        for i, r in enumerate(results)
    ])
    
    themes_text = f"""
Topics: {', '.join(themes.get('main_topics', []))}
Concepts: {', '.join(themes.get('key_concepts', []))}
Fields: {', '.join(themes.get('related_fields', []))}
"""
    
    prompt = f"""You are evaluating search results to find high-quality long-form articles.

Target themes:
{themes_text}

Search results:
{results_text}

Evaluate each result and select the BEST ones that are:
1. Long-form articles or essays (not listicles, not news, not product pages)
2. From reputable sources (personal blogs of experts, quality publications)
3. Highly relevant to the target themes
4. Likely to provide deep insights (not surface-level content)

EXCLUDE:
- News articles about events
- Listicles ("10 ways to...", "5 tips for...")
- Product pages, documentation
- Social media posts
- Video-only content (YouTube unless it's a transcript)
- Paywalled content if obvious

Respond with ONLY valid JSON (no markdown):
{{
    "selected": [
        {{
            "index": 1,
            "url": "exact url from results",
            "title": "exact title from results",
            "reason": "why this is a good pick",
            "quality_score": 8
        }}
    ]
}}

Select 3-7 best results. Quality score is 1-10."""

    response = await call_groq(prompt)
    
    # Clean and parse JSON
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    
    data = json.loads(response.strip())
    return data.get("selected", [])


async def fetch_content_preview(url: str) -> str:
    """Fetch a preview of the content at a URL."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ReadRabbit/1.0)"
            })
            if response.status_code == 200:
                return response.text[:5000]  # First 5000 chars
        except Exception:
            pass
    return ""


async def run_discovery_agent(
    input_content: str,
    input_type: str = "article",  # article, podcast, tweet, text
    max_results: int = 5,
    existing_urls: list[str] = None
) -> dict:
    """
    Main discovery agent that finds similar articles based on input.
    
    Args:
        input_content: URL or text to analyze
        input_type: Type of input (article, podcast, tweet, text)
        max_results: Maximum number of articles to recommend
        existing_urls: URLs already in database (to avoid duplicates)
    
    Returns:
        dict with analysis and recommended articles
    """
    existing_urls = existing_urls or []
    
    # Step 1: Analyze input content
    print(f"[Agent] Analyzing {input_type}...")
    
    # If it's a URL, fetch content first
    if input_content.startswith("http"):
        # Check if it's a YouTube URL
        if is_youtube_url(input_content):
            print(f"[Agent] Detected YouTube URL, extracting transcript...")
            yt_result = get_youtube_transcript(input_content)
            
            if yt_result["success"]:
                transcript = yt_result["transcript"]
                duration = yt_result.get("duration_minutes", 0)
                analysis_input = f"YouTube Video Transcript ({duration} min):\n\n{transcript[:8000]}"
                print(f"[Agent] Got transcript ({len(transcript)} chars, ~{duration} min)")
            else:
                # Fallback to page content if transcript fails
                print(f"[Agent] Transcript failed: {yt_result.get('error')}, falling back to page content")
                content_preview = await fetch_content_preview(input_content)
                analysis_input = f"URL: {input_content}\n\nContent preview:\n{content_preview[:3000]}"
        else:
            # Regular URL - fetch page content
            content_preview = await fetch_content_preview(input_content)
            analysis_input = f"URL: {input_content}\n\nContent preview:\n{content_preview[:3000]}"
    else:
        analysis_input = input_content
    
    themes = await analyze_input_content(analysis_input, input_type)
    print(f"[Agent] Identified themes: {themes['main_topics']}")
    
    # Step 2: Search for similar content
    all_results = []
    search_queries = themes.get("suggested_search_queries", [])[:3]
    
    for query in search_queries:
        print(f"[Agent] Searching: {query}")
        results = await search_web(query, num_results=10)
        all_results.extend(results)
    
    # Remove duplicates and existing URLs
    seen_urls = set(existing_urls)
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)
    
    print(f"[Agent] Found {len(unique_results)} unique results")
    
    if not unique_results:
        return {
            "success": True,
            "themes": themes,
            "recommendations": [],
            "message": "No new articles found"
        }
    
    # Step 3: Evaluate and rank results
    print(f"[Agent] Evaluating quality...")
    evaluated = await evaluate_search_results(unique_results, themes)
    
    # Step 4: Extract metadata for top picks
    print(f"[Agent] Extracting metadata for {len(evaluated)} articles...")
    recommendations = []
    
    for item in evaluated[:max_results]:
        try:
            url = item["url"]
            content = await fetch_content_preview(url)
            metadata = await extract_article_metadata(url, content)
            
            recommendations.append({
                "url": url,
                "title": metadata.get("title", item["title"]),
                "source": metadata.get("source"),
                "author": metadata.get("author"),
                "summary": metadata.get("summary"),
                "topics": metadata.get("topics", []),
                "read_time": metadata.get("read_time"),
                "quality_score": item.get("quality_score", 7),
                "reason": item.get("reason", "Relevant to your interests"),
            })
            print(f"[Agent] ✓ {metadata.get('title', url)[:50]}...")
        except Exception as e:
            print(f"[Agent] ✗ Failed to process {url}: {e}")
            continue
    
    return {
        "success": True,
        "themes": themes,
        "recommendations": recommendations,
        "searches_performed": len(search_queries),
        "results_evaluated": len(unique_results),
    }
