# pro_gemini_script_generator.py

import requests
import streamlit as st
from datetime import datetime, timedelta
import json

# Optional YouTube transcript import wrapped in try-except
try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    YT_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YT_TRANSCRIPT_AVAILABLE = False

from duckduckgo_search import DDGSearch
from newspaper import Article

# === API KEYS ===
GEMINI_API_KEY = "AIzaSyDxOT0qyfHbf162QSfOEgHtTvzgsK90H6w"
YOUTUBE_API_KEY = "AIzaSyDf3aAnAyrmGxp2imtzM1YUyCqwEtQG8mY"
GOOGLE_CUSTOM_SEARCH_API_KEY = "AIzaSyDnPnEBzfGYJrx4LNxpHk1vsvVe6BrWE4Y"
GOOGLE_CSE_ID = "AIzaSyDBv8BRhXJZb6Ne7_PdZHls4lkQApvqCL0"

# === ENDPOINTS ===
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CUSTOM_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"

st.set_page_config(page_title="Pro Script Generator (Gemini)", layout="wide")
st.title("Pro Script Generator — Research like 100 top scriptwriters")

def safe_get(url, params=None, headers=None, timeout=15):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception:
        return None

def clean_text(text, max_chars=4000):
    if not text:
        return ""
    return text.replace("\n", " ").replace("\r", " ").strip()[:max_chars]

def search_youtube_videos(query, max_results=5, published_after=None):
    if not YOUTUBE_API_KEY:
        return []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "maxResults": min(50, max_results),
        "key": YOUTUBE_API_KEY
    }
    if published_after:
        params["publishedAfter"] = published_after
    r = safe_get(YOUTUBE_SEARCH_URL, params=params)
    if not r:
        return []
    items = r.json().get("items", [])
    vids = []
    for it in items:
        vid = it.get("id", {}).get("videoId")
        if not vid:
            continue
        vids.append({
            "id": vid,
            "title": it.get("snippet", {}).get("title", ""),
            "description": it.get("snippet", {}).get("description", "")
        })
    return vids

def fetch_transcript(video_id):
    if not YT_TRANSCRIPT_AVAILABLE:
        return ""
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=['en','ur','hi'])
        return " ".join([s.get("text","") for s in segs])
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""
    except Exception:
        return ""

def custom_search(query, max_results=5):
    results = []
    if GOOGLE_CUSTOM_SEARCH_API_KEY and GOOGLE_CSE_ID:
        params = {"key": GOOGLE_CUSTOM_SEARCH_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": max_results}
        r = safe_get(CUSTOM_SEARCH_URL, params=params)
        if r:
            for it in r.json().get("items", []):
                results.append({"title": it.get("title",""), "link": it.get("link",""), "snippet": it.get("snippet","")})
            return results
    ddg = DDGSearch()
    hits = ddg.search(query, max_results=max_results)
    for h in hits:
        url = h.get("href") or h.get("url")
        if not url:
            continue
        results.append({"title": h.get("title",""), "link": url, "snippet": h.get("body","")})
    return results

def fetch_article_text(url, max_chars=6000):
    try:
        art = Article(url)
        art.download()
        art.parse()
        return clean_text(art.text, max_chars)
    except Exception:
        r = safe_get(url)
        if r and r.text:
            return clean_text(r.text, max_chars)
    return ""

def wiki_summary(title):
    try:
        url = WIKIPEDIA_SUMMARY.format(requests.utils.quote(title))
        r = safe_get(url)
        if r:
            return r.json().get("extract","")
    except Exception:
        pass
    return ""

def call_gemini(prompt, temperature=0.7, max_output_tokens=4096):
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not set.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    body = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
        "contents": [{"type": "text", "text": prompt}]
    }
    r = requests.post(url, json=body, timeout=120)
    if not r.ok:
        return None, f"Gemini API error {r.status_code}: {r.text}"
    j = r.json()
    candidates = j.get("candidates") or []
    if candidates:
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text")
        if text:
            return text, None
    return None, f"Unexpected Gemini response: {json.dumps(j)[:400]}"

def build_analysis_prompt(title, snippets):
    joined = "\n\n".join(snippets)[:16000]
    return (
        f"Read the following source excerpts related to the title: {title}\n\n"
        f"{joined}\n\n"
        "Provide 8 concise bullets: strongest hooks, recurring themes, contradictions, surprising facts, and 3 unique angles not commonly covered."
    )

def build_final_prompt(title, analysis_bullets, context_snippets, target_words=3300):
    return (
        "You are the combined expertise of the world's top 100 professional YouTube scriptwriters and researchers.\n\n"
        f"TITLE: {title}\n\n"
        f"USE THE FOLLOWING ANALYSIS BULLETS (do not output bullets, just use them):\n{analysis_bullets}\n\n"
        f"CONTEXT SNIPPETS:\n{context_snippets}\n\n"
        f"Task: Write a single continuous paragraph script (no headings) approx {target_words} words."
    )

with st.sidebar:
    target_minutes = st.number_input("Target minutes", 10, 60, 30)
    target_words = st.number_input("Target words (approx)", 800, 7000, int(target_minutes*120))
    days = st.number_input("Search last N days", 1, 365, 90)
    max_videos = st.slider("Top videos per keyword", 1, 8, 4)
    max_articles = st.slider("Articles per keyword", 1, 8, 5)
    fetch_transcripts = st.checkbox("Fetch transcripts (YouTube)", value=YT_TRANSCRIPT_AVAILABLE)

title = st.text_input("Title")
keywords_text = st.text_area("Optional keywords / competitor channels (one per line)", height=120)

if st.button("Run Pro Research & Generate Script"):
    if not title.strip():
        st.error("Please enter a title.")
    else:
        keywords = [k.strip() for k in (keywords_text or title).splitlines() if k.strip()]
        published_after = (datetime.utcnow() - timedelta(days=int(days))).isoformat("T") + "Z"

        snippets = []

        for kw in keywords:
            vids = search_youtube_videos(kw, max_results=max_videos, published_after=published_after)
            for v in vids:
                snippets.append(clean_text(v.get("title","") + " " + v.get("description",""), max_chars=1200))
                if fetch_transcripts and v.get("id"):
                    t = fetch_transcript(v["id"])
                    if t:
                        snippets.append(clean_text(t, max_chars=3000))

        for kw in keywords:
            arts = custom_search(kw, max_results=max_articles)
            for a in arts:
                snippets.append(clean_text(a.get("title","") + " " + a.get("snippet",""), max_chars=2000))
                link = a.get("link")
                if link:
                    at = fetch_article_text(link, max_chars=4000)
                    if at:
                        snippets.append(at)

        w = wiki_summary(title)
        if w:
            snippets.append(clean_text(w, max_chars=2500))

        if not snippets:
            snippets = [f"No public sources found. Use title as primary seed: {title}"]

        analysis_prompt = build_analysis_prompt(title, snippets[:12])
        analysis_text, err = call_gemini(analysis_prompt, temperature=0.2, max_output_tokens=800)
        if err:
            analysis_text = "- No sources found. Use expert simulation."

        context_join = "\n\n".join(snippets)[:20000]
        final_prompt = build_final_prompt(title, analysis_text, context_join, target_words=int(target_words))

        script_text, err2 = call_gemini(final_prompt, temperature=0.75, max_output_tokens=9000)
        if script_text:
            single_para = " ".join([p.strip() for p in script_text.splitlines() if p.strip()])
            wc =
