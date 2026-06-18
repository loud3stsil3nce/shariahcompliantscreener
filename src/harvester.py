import os
import re
import json
import urllib.parse
import asyncio
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# Setup API keys
load_dotenv_status = False
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv_status = True
except ImportError:
    pass

def call_with_retry(api_func, *args, **kwargs):
    import time
    import re
    max_retries = kwargs.pop("max_retries", 5)
    for attempt in range(max_retries):
        try:
            return api_func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower():
                sleep_time = float(2.0 ** attempt)
                match = re.search(r"retry in (\d+\.?\d*)s", err_str)
                if match:
                    sleep_time = float(match.group(1)) + 1.0
                print(f"⚠️ Rate limit hit. Sleeping for {sleep_time:.2f}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(sleep_time)
            else:
                raise e
    raise Exception("Max retries exceeded for Gemini API call.")

def get_gemini_embeddings(texts, model="models/gemini-embedding-001"):
    """Fetch embeddings for a list of texts using Gemini's API in batches."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []
    
    # Configure genai just in case it isn't configured globally
    genai.configure(api_key=api_key)
    
    # Batched embedding retrieval
    embeddings = []
    batch_size = 50  # Gemini supports batching
    import time
    rate_limit_encountered = False
    for idx, i in enumerate(range(0, len(texts), batch_size)):
        batch = texts[i:i+batch_size]
        if rate_limit_encountered:
            print("⚠️ Skipping batch embedding due to prior rate limit block. Appending zero-vectors.")
            for _ in batch:
                embeddings.append([0.0] * 3072)
            continue
            
        if idx > 0:
            time.sleep(6.0)  # Pace batch embedding requests to stay under 15 RPM free tier limit
            
        try:
            result = call_with_retry(
                genai.embed_content,
                model=model,
                content=batch,
                task_type="retrieval_document",
                max_retries=1
            )
            embeddings.extend(result['embedding'])
        except Exception as e:
            print(f"Error fetching embeddings for batch: {e}")
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower() or "max retries" in err_str.lower()
            
            if is_rate_limit:
                print("⚠️ Batch failed due to rate limits. Skipping fallback to avoid flooding API. Appending zero-vectors.")
                rate_limit_encountered = True
                for _ in batch:
                    embeddings.append([0.0] * 3072)
            else:
                # Fallback to single requests or zero vectors (only for non-rate-limit errors)
                for text in batch:
                    try:
                        res = call_with_retry(
                            genai.embed_content,
                            model=model,
                            content=text,
                            task_type="retrieval_document"
                        )
                        embeddings.append(res['embedding'])
                    except Exception as fallback_err:
                        print(f"Fallback single request failed: {fallback_err}")
                        # Provide zero vector fallback on failure
                        embeddings.append([0.0] * 3072)  # 3072 is default gemini-embedding-001 size
    return embeddings

def get_gemini_query_embedding(query, model="models/gemini-embedding-001"):
    """Fetch embedding for a query using Gemini's API."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return [0.0] * 3072
    
    genai.configure(api_key=api_key)
    try:
        result = call_with_retry(
            genai.embed_content,
            model=model,
            content=query,
            task_type="retrieval_query",
            max_retries=1
        )
        return result['embedding']
    except Exception as e:
        print(f"Error fetching query embedding: {e}")
        return [0.0] * 3072

def chunk_text(text, chunk_size=1000, overlap=150):
    """Split text recursively into overlapping chunks."""
    if not text:
        return []
    
    # Normalize whitespaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        # Try to find a sentence or word boundary to cut nicely
        if end < len(text):
            # Look back up to 100 characters for a period, semicolon, or space
            boundary = -1
            for offset in range(100):
                char = text[end - offset]
                if char in ['.', ';', '\n']:
                    boundary = end - offset + 1
                    break
                elif char == ' ' and boundary == -1:
                    boundary = end - offset
            if boundary != -1:
                end = boundary
        
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= len(text) or chunk_size - overlap <= 0:
            break
            
    return [c for c in chunks if len(c) > 30]  # Filter out noise

def semantic_search(query, chunks, chunk_embeddings, top_k=5):
    """Perform cosine-similarity vector search over chunks using NumPy."""
    if not chunks or not chunk_embeddings:
        return []
    
    query_emb = get_gemini_query_embedding(query)
    
    q_vec = np.array(query_emb)
    c_vecs = np.array(chunk_embeddings)
    
    # Check if we have zero/missing embeddings
    is_fallback = np.all(q_vec == 0.0) or np.all(c_vecs == 0.0)
    
    if is_fallback:
        print("⚠️ Embeddings are unavailable or zero-vectors. Falling back to keyword-based sparse retrieval...")
        stopwords = {"and", "the", "or", "in", "of", "to", "for", "a", "is", "on", "with", "by", "at", "from", "as", "an", "that", "this", "be", "are", "split", "details", "revenue"}
        query_words = [w.strip(".,;:?!()\"'") for w in query.lower().split()]
        query_words = {w for w in query_words if w and w not in stopwords}
        
        scored_chunks = []
        for idx, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            score = 0
            for qw in query_words:
                if qw in chunk_lower:
                    score += chunk_lower.count(qw)
            # Normalize slightly by chunk length to prevent biased results towards giant chunks
            norm_score = score / (1.0 + 0.01 * len(chunk))
            scored_chunks.append((idx, norm_score))
            
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_indices = [x[0] for x in scored_chunks[:top_k]]
        
        results = []
        for idx in top_indices:
            chunk_lower = chunks[idx].lower()
            matches = sum(1 for qw in query_words if qw in chunk_lower)
            match_ratio = matches / len(query_words) if query_words else 0.0
            results.append({
                "chunk": chunks[idx],
                "score": match_ratio
            })
        return results
        
    # Compute dot products and norms
    dot_products = np.dot(c_vecs, q_vec)
    c_norms = np.linalg.norm(c_vecs, axis=1)
    q_norm = np.linalg.norm(q_vec)
    
    # Avoid divide by zero
    c_norms = np.where(c_norms == 0, 1e-9, c_norms)
    q_norm = 1e-9 if q_norm == 0 else q_norm
    
    similarities = dot_products / (c_norms * q_norm)
    
    # Sort by similarity in descending order
    top_indices = np.argsort(similarities)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        results.append({
            "chunk": chunks[idx],
            "score": float(similarities[idx])
        })
    return results

# --- SEC EDGAR, TRANSCRIPTS & SEARCH FETCHERS ---

async def fetch_transcript(ticker, year=2025, quarter=4):
    """Fetch earnings call transcript from APIs or fallback to web scraping."""
    ticker = ticker.upper().strip()
    
    # 1. Try Financial Modeling Prep (FMP) if API Key exists
    fmp_key = os.getenv("FMP_API_KEY")
    if fmp_key:
        url = f"https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}?quarter={quarter}&year={year}&apikey={fmp_key}"
        try:
            r = await asyncio.to_thread(requests.get, url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0].get("transcript", "")
        except Exception as e:
            print(f"FMP transcript fetch failed for {ticker}: {e}")

    # 2. Try Alpha Vantage if API Key exists
    av_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if av_key:
        url = f"https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol={ticker}&year={year}&quarter=Q{quarter}&apikey={av_key}"
        try:
            r = await asyncio.to_thread(requests.get, url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                # Alpha Vantage returns transcript in 'transcript' key or list
                if "transcript" in data:
                    return data["transcript"]
        except Exception as e:
            print(f"Alpha Vantage transcript fetch failed for {ticker}: {e}")

    # 3. Fallback: Search Google for the transcript text
    print(f"⚠️ No Transcript API keys found. Searching Google for {ticker} Q{quarter} {year} transcript...")
    search_query = f"{ticker} Q{quarter} {year} earnings call transcript Motley Fool"
    urls = await search_google_urls(search_query)
    
    for url in urls[:2]:
        if "fool.com" in url or "seekingalpha.com" in url or "transcript" in url.lower():
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    body = soup.find(class_="tail-content") or soup.find(class_="article-body") or soup.find("article")
                    if body:
                        text = body.get_text(" ")
                        if "transcript" in text.lower() or "call" in text.lower():
                            return text
            except Exception as e:
                print(f"Failed to scrape transcript from {url}: {e}")
                
    return ""

async def search_ir_presentation_pdf(ticker, year=2025, quarter=4):
    """Find the URL of the company's investor presentation PDF using search queries."""
    ticker = ticker.upper().strip()
    query = f"{ticker} investor relations Q{quarter} {year} earnings presentation filetype:pdf"
    
    # Try SerpAPI if key exists
    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        url = f"https://serpapi.com/search.json?q={urllib.parse.quote(query)}&api_key={serp_key}"
        try:
            r = await asyncio.to_thread(requests.get, url, timeout=15)
            if r.status_code == 200:
                results = r.json()
                org_results = results.get("organic_results", [])
                for res in org_results:
                    link = res.get("link", "")
                    if link.lower().endswith(".pdf"):
                        return link
        except Exception as e:
            print(f"SerpAPI PDF search failed for {ticker}: {e}")

    # Fallback: Scrape Google search results
    urls = await search_google_urls(query)
    for url in urls:
        if url.lower().endswith(".pdf") or "presentation" in url.lower() or "supplement" in url.lower():
            return url
    return ""

async def search_google_urls(query):
    """Scrape Google Search for URLs as a zero-dependency fallback."""
    urls = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded_query}"
    
    try:
        r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith("http") and "google.com" not in href:
                    urls.append(href)
    except Exception as e:
        print(f"Google scrape failed for query '{query}': {e}")
        
    return urls

async def download_pdf_text(url):
    """Download a PDF and extract its text content."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=25)
        if r.status_code == 200:
            import io
            from pypdf import PdfReader
            pdf_file = io.BytesIO(r.content)
            reader = PdfReader(pdf_file)
            text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text.append(t)
            return "\n".join(text)
    except Exception as e:
        print(f"Failed to download or parse PDF {url}: {e}")
    return ""

async def search_web_evidence(query, num_results=3):
    """
    Query SerpAPI or scrape Google for a query, and return a concatenated 
    text block of search result titles, snippets, and scraped page texts.
    """
    evidence_parts = []
    serp_key = os.getenv("SERPAPI_API_KEY")
    
    urls_to_scrape = []
    
    if serp_key:
        url = f"https://serpapi.com/search.json?q={urllib.parse.quote(query)}&api_key={serp_key}"
        try:
            r = await asyncio.to_thread(requests.get, url, timeout=15)
            if r.status_code == 200:
                results = r.json()
                org_results = results.get("organic_results", [])
                for idx, res in enumerate(org_results[:num_results]):
                    title = res.get("title", "")
                    snippet = res.get("snippet", "")
                    link = res.get("link", "")
                    evidence_parts.append(f"Search Result {idx+1}: {title}\nURL: {link}\nSnippet: {snippet}\n")
                    if link and not link.lower().endswith(".pdf"):
                        urls_to_scrape.append(link)
        except Exception as e:
            print(f"SerpAPI query failed for '{query}': {e}")
    
    # If SerpAPI failed or wasn't configured, fall back to direct scraping
    if not evidence_parts:
        urls = await search_google_urls(query)
        urls_to_scrape = urls[:num_results]
        for idx, url_link in enumerate(urls_to_scrape):
            evidence_parts.append(f"Search Result {idx+1} URL: {url_link}")
    
    # Scrape content from the top URLs to gather deep text evidence
    scraped_count = 0
    for url_link in urls_to_scrape[:2]:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = await asyncio.to_thread(requests.get, url_link, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                # Strip scripts/styles
                for s in soup(["script", "style", "nav", "footer", "header"]):
                    s.decompose()
                text = soup.get_text(" ")
                # Clean whitespace
                cleaned_text = " ".join(text.split())
                # Limit characters to avoid overloading context
                evidence_parts.append(f"\n[Scraped Content from {url_link}]:\n{cleaned_text[:3000]}\n")
                scraped_count += 1
        except Exception as e:
            print(f"Failed to scrape text from {url_link}: {e}")
            
    return "\n".join(evidence_parts)


async def harvest_all_sources(ticker, year=2025, quarter=4, sec_text=None):
    """Fetch from SEC, Search, and Transcript parallelly, returning compiled vectors."""
    print(f"🚀 Launching Parallel Harvester for {ticker} Q{quarter} {year}...")
    
    # Fetch tasks
    transcript_task = fetch_transcript(ticker, year, quarter)
    pdf_url_task = search_ir_presentation_pdf(ticker, year, quarter)
    
    # Target web search for segment details
    web_search_query = f"{ticker} segment revenue split breakdown {year}"
    web_search_task = search_web_evidence(web_search_query)
    
    # Run parallel
    transcript_text, pdf_url, web_search_evidence = await asyncio.gather(
        transcript_task, 
        pdf_url_task, 
        web_search_task
    )
    
    pdf_text = ""
    if pdf_url:
        print(f"📥 Found IR presentation PDF: {pdf_url}. Downloading...")
        pdf_text = await download_pdf_text(pdf_url)
        
    # Combine sources into plain text and chunks
    sources_text = []
    all_chunks = []
    
    if sec_text:
        sources_text.append(f"=== SEC 10-K/10-Q FILING TEXT ===\n{sec_text}")
        chunks = chunk_text(sec_text)
        for c in chunks:
            all_chunks.append(f"[SEC 10-K/10-Q Filing] {c}")
            
    if transcript_text:
        sources_text.append(f"=== EARNINGS CALL TRANSCRIPT ===\n{transcript_text}")
        chunks = chunk_text(transcript_text)
        for c in chunks:
            all_chunks.append(f"[Earnings Call Transcript] {c}")
            
    if pdf_text:
        sources_text.append(f"=== INVESTOR PRESENTATION SLIDES ===\n{pdf_text}")
        chunks = chunk_text(pdf_text)
        for c in chunks:
            all_chunks.append(f"[Investor Presentation PDF] {c}")
            
    if web_search_evidence:
        sources_text.append(f"=== WEB SEARCH SEGMENT EVIDENCE ===\n{web_search_evidence}")
        chunks = chunk_text(web_search_evidence)
        for c in chunks:
            all_chunks.append(f"[Web Search Evidence] {c}")
            
    compiled_text = "\n\n".join(sources_text)
    print("⚡ Long-Context Direct Synthesis: Bypassing embedding generation.")
    
    return {
        "compiled_text": compiled_text,
        "chunks": all_chunks,
        "embeddings": [],
        "pdf_url": pdf_url,
        "has_transcript": bool(transcript_text),
        "has_presentation": bool(pdf_text),
        "has_web_search": bool(web_search_evidence)
    }
