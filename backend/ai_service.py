import os
import httpx
import json
from typing import Optional

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


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
        # Take first 3000 chars to stay within context limits
        content_hint = f"\n\nHere's the beginning of the article content:\n{html_content[:3000]}"
    
    prompt = f"""Analyze this article URL and extract metadata.

URL: {url}
{content_hint}

Extract the following information and respond ONLY with valid JSON (no markdown, no explanation):

{{
    "title": "The article title",
    "author": "Author name (or null if unknown)",
    "source": "Publication/website name (e.g., 'Paul Graham', 'The New Yorker', 'Farnam Street')",
    "summary": "A compelling 1-2 sentence summary that makes someone want to read it",
    "topics": ["Topic1", "Topic2", "Topic3"],
    "read_time": estimated_minutes_to_read
}}

For topics, choose 2-4 relevant tags from categories like: AI, Technology, Productivity, Career, Philosophy, Business, Psychology, Writing, Startups, Finance, Science, Design, Leadership, Health, Creativity.

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
