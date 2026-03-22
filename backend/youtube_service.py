import re
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/watch\?.*v=)([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def get_youtube_transcript(url: str, max_chars: int = 15000) -> dict:
    """
    Fetch transcript from a YouTube video.
    
    Returns:
        {
            "success": True/False,
            "video_id": "...",
            "transcript": "full transcript text...",
            "duration_minutes": 45,
            "error": "..." (if failed)
        }
    """
    video_id = extract_video_id(url)
    
    if not video_id:
        return {
            "success": False,
            "error": "Could not extract video ID from URL"
        }
    
    try:
        # Try to get transcript (prefers manual captions, falls back to auto-generated)
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try English first, then any available language
        transcript = None
        try:
            transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
        except:
            # Get first available transcript
            for t in transcript_list:
                transcript = t
                break
        
        if not transcript:
            return {
                "success": False,
                "video_id": video_id,
                "error": "No transcript available"
            }
        
        # Fetch the actual transcript data
        transcript_data = transcript.fetch()
        
        # Combine all text segments
        full_text = " ".join([entry['text'] for entry in transcript_data])
        
        # Calculate approximate duration
        if transcript_data:
            last_entry = transcript_data[-1]
            duration_seconds = last_entry.get('start', 0) + last_entry.get('duration', 0)
            duration_minutes = int(duration_seconds / 60)
        else:
            duration_minutes = 0
        
        # Truncate if too long
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "... [transcript truncated]"
        
        return {
            "success": True,
            "video_id": video_id,
            "transcript": full_text,
            "duration_minutes": duration_minutes,
        }
        
    except TranscriptsDisabled:
        return {
            "success": False,
            "video_id": video_id,
            "error": "Transcripts are disabled for this video"
        }
    except NoTranscriptFound:
        return {
            "success": False,
            "video_id": video_id,
            "error": "No transcript found for this video"
        }
    except Exception as e:
        return {
            "success": False,
            "video_id": video_id,
            "error": str(e)
        }


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL."""
    return bool(extract_video_id(url))
