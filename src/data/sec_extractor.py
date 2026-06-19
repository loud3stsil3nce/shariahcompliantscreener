import re
import time
import logging
import requests
import bs4

class SECParser:
    """
    A professional-grade SEC Edgar Parser that retrieves, cleans, and filters
    annual and quarterly filings (10-K, 20-F, 10-Q) for Shariah compliance auditing.
    """
    def __init__(self, email="contact@halalscreener.com", company="HalalStockScreener"):
        self.headers = {'User-Agent': f'{company}/1.0 ({email})'}
        # Whitelist of keywords relevant to Shariah compliance auditing
        self.keywords = [
            "segment", "revenue", "product", "aesthetics", "botox", "juvederm",
            "debt", "bond", "loan", "note", "credit facility", "interest-bearing", "interest bearing",
            "marketable securities", "cash equivalents", "treasury bill", "commercial paper", "money market",
            "interest income", "interest expense", "other income", "starshield", "defense", "military",
            "aerospace", "weapons", "financial statements", "note ", "item 8",
            "derivative", "hedging", "swap", "forward contract", "options contract",
            "non-operating income", "nonoperating income", "non-operating expense", "other non-operating"
        ]

    def extract_relevant_sections(self, text, max_chars=300000):
        """
        Filters cleaned 10-K/20-F text to only keep sections relevant to Shariah auditing
        (e.g., segment disclosures, notes on debt, liquid assets) to optimize LLM context usage.
        """
        if len(text) <= max_chars:
            return text

        paragraphs = text.split('\n')
        selected_indices = set()
        
        for idx, para in enumerate(paragraphs):
            para_lower = para.lower()
            # Always keep tables as they contain critical balance sheet details
            if para.strip().startswith('|'):
                selected_indices.add(idx)
                continue
                
            # Match keywords and keep surrounding context for context preservation
            if any(kw in para_lower for kw in self.keywords):
                selected_indices.add(idx)
                if idx > 0: selected_indices.add(idx - 1)
                if idx < len(paragraphs) - 1: selected_indices.add(idx + 1)
                
        sorted_indices = sorted(list(selected_indices))
        filtered_lines = [paragraphs[idx] for idx in sorted_indices]
        filtered_text = '\n'.join(filtered_lines)
        
        # Safe fallback if filter was too aggressive
        if len(filtered_text) < 10000:
            return text[:max_chars]
            
        return filtered_text[:max_chars]

    def html_to_clean_text_with_tables(self, soup):
        """
        Decomposes style tags and converts HTML <table> grids into structured
        Markdown tables, ensuring numerical alignment for LLMs while stripping Inline XBRL tags.
        """
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Parse nested tables starting from the innermost
        for table in list(reversed(soup.find_all('table'))):
            markdown_table = []
            for row in table.find_all('tr'):
                row_text = []
                for cell in row.find_all(['td', 'th']):
                    cell_val = cell.get_text().strip().replace('\n', ' ')
                    cell_val = ' '.join(cell_val.split())
                    row_text.append(cell_val)
                if any(row_text):
                    markdown_table.append("| " + " | ".join(row_text) + " |")
            
            if markdown_table:
                table_text = "\n\n" + "\n".join(markdown_table) + "\n\n"
                table.replace_with(soup.new_string(table_text))
            else:
                table.decompose()
                
        # Insert spacing around block tags to keep paragraphs distinct
        block_tags = ["p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]
        for tag in soup.find_all(block_tags):
            tag.insert_after(soup.new_string("\n"))

        text = soup.get_text()
        
        # Clean up Inline XBRL/iXBRL tags or malformed XML that BeautifulSoup might have bypassed
        text = re.sub(r'<[^>]+>', '', text)
        
        lines = []
        for line in text.split('\n'):
            stripped = ' '.join(line.split())
            if stripped:
                lines.append(stripped)
        return '\n'.join(lines)

    def resolve_ticker_to_cik(self, ticker):
        """Resolves a public U.S. stock ticker symbol to a zero-padded 10-digit SEC CIK."""
        try:
            r = requests.get('https://www.sec.gov/files/company_tickers.json', headers=self.headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                ticker_upper = ticker.upper().strip()
                for key, val in data.items():
                    if val.get('ticker') == ticker_upper:
                        return str(val.get('cik_str')).zfill(10)
        except Exception as e:
            logging.error(f"Failed CIK resolution for {ticker}: {e}")
        return ticker

    def get_latest_10k_text(self, ticker):
        """
        Finds, downloads, and processes the latest annual filing (10-K or 20-F) from SEC EDGAR.
        """
        resolved_cik = self.resolve_ticker_to_cik(ticker)
        
        # Handle international or non-registered listings
        if resolved_cik == ticker and "." in ticker:
            suffix = ticker.split(".")[-1]
            return None, (
                f"SEC EDGAR only hosts filings for US-registered entities. Ticker '{ticker}' "
                f"appears to be an international listing (suffix '.{suffix}') and is not available "
                f"on EDGAR. Please use 'Standard AI Analysis (Fast)' instead, which audits the stock "
                f"using Yahoo Finance database metrics."
            )
            
        search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={resolved_cik}&Find=Search&owner=exclude&action=getcompany"
        
        try:
            time.sleep(0.1)  # Sleep briefly to ensure compliance with SEC's 10 req/sec rate limit
            response = requests.get(search_url, headers=self.headers)
            soup = bs4.BeautifulSoup(response.text, 'html.parser')
            
            filing_types = ['10-K', '10-Q', '20-F', '10-K/A', '10-Q/A', '424B4', 'S-1', 'S-1/A']
            doc_url = None
            
            table = soup.find('table', class_='tableFile2')
            if table:
                rows = table.find_all('row') if table.find('row') else table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 0:
                        f_type = cells[0].text.strip()
                        if f_type in filing_types:
                            link = cells[1].find('a')
                            if link:
                                doc_url = f"https://www.sec.gov{link['href']}"
                                break
            
            # Fallback for explicit type search (e.g. Foreign ADRs whose 20-F is pushed down)
            if not doc_url:
                for fallback_type in ['10-K', '20-F', '424B4', 'S-1']:
                    time.sleep(0.1)
                    alt_url = f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={resolved_cik}&type={fallback_type}&count=10"
                    response = requests.get(alt_url, headers=self.headers)
                    soup = bs4.BeautifulSoup(response.text, 'html.parser')
                    table = soup.find('table', class_='tableFile2')
                    if table:
                        link = table.find('a', id='documentsbutton')
                        if link:
                            doc_url = f"https://www.sec.gov{link['href']}"
                            break
                            
            if not doc_url:
                return None, f"No annual filings (10-K/20-F) found for {ticker}."

            # Fetch the filing document landing page
            time.sleep(0.1)
            doc_response = requests.get(doc_url, headers=self.headers)
            doc_soup = bs4.BeautifulSoup(doc_response.text, 'html.parser')
            
            doc_table = doc_soup.find('table', class_='tableFile')
            if not doc_table:
                 return None, "Document table not found on landing page."
                 
            links = doc_table.find_all('a')
            final_url = None
            for link in links:
                href = link['href']
                if href.endswith('.htm') or href.endswith('.html'):
                    if 'index' not in href.lower() and 'hdr' not in href.lower():
                        if '/ix?doc=' in href:
                            href = href.replace('/ix?doc=', '')
                        final_url = f"https://www.sec.gov{href}"
                        break
            
            if not final_url:
                return None, "Could not find HTML version of filing text."

            # Download actual filing report text
            print(f"📥 Downloading: {final_url}")
            time.sleep(0.1)
            content_response = requests.get(final_url, headers=self.headers)
            content_soup = bs4.BeautifulSoup(content_response.text, 'html.parser')
            
            clean_text = self.html_to_clean_text_with_tables(content_soup)
            filtered_text = self.extract_relevant_sections(clean_text, max_chars=300000)
            return filtered_text, final_url

        except Exception as e:
            return None, f"SEC Error: {str(e)}"

# Module-level convenience wrapper for backward compatibility
def get_latest_10k_text(ticker):
    parser = SECParser()
    return parser.get_latest_10k_text(ticker)