import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import pandas as pd
import json
import time
from datetime import datetime
import re

st.set_page_config(
    page_title="Daraz.lk Scraper Pro",
    page_icon="🛍️",
    layout="wide"
)

st.markdown("""
<style>
    .main-header {
        color: #F57224;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #F57224 0%, #D65A12 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .product-card {
        border: 1px solid #e2e8f0;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .score-badge {
        background: #34C759;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-weight: bold;
    }
    .search-box {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #F57224;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

if 'scraped_items' not in st.session_state:
    st.session_state.scraped_items = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'scrape_stats' not in st.session_state:
    st.session_state.scrape_stats = {
        'total_urls': 0,
        'processed_urls': 0,
        'items_found': 0,
        'success_count': 0,
        'fail_count': 0
    }
if 'generated_urls' not in st.session_state:
    st.session_state.generated_urls = ""

def get_openai_client():
    api_key = st.session_state.get('api_key', '')
    if api_key and api_key.strip():
        try:
            return OpenAI(api_key=api_key)
        except:
            return None
    return None

def generate_search_urls(query, num_pages):
    urls = []
    category_name = query.title()
    for page in range(1, num_pages + 1):
        url = f"https://www.daraz.lk/catalog/?page={page}&q={query}"
        urls.append({
            'category': f"{category_name} (Page {page})",
            'url': url
        })
    return urls

def clean_json_response(text):
    text = text.strip()
    backtick = chr(96)
    triple_backtick = backtick * 3
    json_code_block = triple_backtick + "json"
    text = text.replace(json_code_block, "")
    text = text.replace(triple_backtick, "")
    return text.strip()

def scrape_daraz_category(url, category_name, client):
    try:
        proxied_url = f"https://corsproxy.io/?{url}"
        response = requests.get(proxied_url, timeout=30)
        response.raise_for_status()
        
        html_content = response.text
        
        prompt = f"""
You are a data extraction expert. Extract ALL products from this Daraz.lk HTML page.

For each product, extract:
- Product Name
- Sold Count (number only, if "1.2k sold" → 1200)
- Reviews Count (number only)
- Rating (number, e.g., 4.5)
- Seller Name
- Price (in Rs., numeric value only)
- Product URL (full link)

Return ONLY a valid JSON array. No markdown formatting, no explanations.
Format:
[
  {{"name": "Product Name", "sold": 120, "reviews": 45, "rating": 4.5, "seller": "Seller Name", "price": 12500, "productUrl": "https://www.daraz.lk/products/..."}}
]

HTML Content (first 50000 chars):
{html_content[:50000]}
"""
        
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data extraction expert. Always return valid JSON without markdown formatting."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        response_text = completion.choices[0].message.content.strip()
        response_text = clean_json_response(response_text)
        products = json.loads(response_text)
        
        scraped_items = []
        for idx, product in enumerate(products):
            sold = product.get('sold', 0)
            reviews = product.get('reviews', 0)
            rating = product.get('rating', 0)
            score = (sold * 0.4) + (reviews * 0.3) + (rating * 20 * 0.3)
            
            item = {
                'id': f"{category_name}_{idx}_{int(time.time())}",
                'darazCat': category_name,
                'name': product.get('name', 'N/A'),
                'sold': sold,
                'reviews': reviews,
                'rating': rating,
                'seller': product.get('seller', 'N/A'),
                'price': f"Rs. {product.get('price', 0):,.0f}",
                'priceValue': product.get('price', 0),
                'productUrl': product.get('productUrl', ''),
                'sourceUrl': url,
                'score': round(score, 2),
                'funnelStage': 'SCRAPED',
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            scraped_items.append(item)
        
        return scraped_items, None
        
    except Exception as e:
        return [], str(e)

def parse_input(input_text):
    lines = input_text.strip().split('\n')
    parsed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ',' in line:
            parts = line.split(',', 1)
            cat = parts[0].strip()
            url = parts[1].strip()
        elif '\t' in line:
            parts = line.split('\t', 1)
            cat = parts[0].strip()
            url = parts[1].strip()
        elif line.startswith('http'):
            url = line
            cat = url.rstrip('/').split('/')[-1].replace('-', ' ').title()
        else:
            continue
        parsed.append({'category': cat, 'url': url})
    return parsed

st.markdown('<div class="main-header">🛍️ Daraz.lk Scraper Pro</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "OpenAI API Key",
        value=st.session_state.get('api_key', ''),
        type="password",
        help="Get your API key from platform.openai.com/api-keys"
    )
    if api_key:
        st.session_state.api_key = api_key
        st.success("✓ OpenAI API Key configured")
    else:
        st.warning("⚠️ Please enter your OpenAI API key")
    
    st.markdown("---")
    
    st.header("🤖 AI Model")
    model_choice = st.selectbox(
        "Choose model:",
        ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        help="gpt-4o-mini is fastest and cheapest"
    )
    st.session_state.model_choice = model_choice
    
    st.markdown("---")
    
    st.header("📊 Funnel Stage Filter")
    selected_stages = st.multiselect(
        "Show stages:",
        ['SCRAPED', 'SELECTED', 'PETTAH_HUB', 'LISTED'],
        default=['SCRAPED']
    )
    
    st.markdown("---")
    
    if st.session_state.scraped_items:
        st.header("💾 Export Data")
        df = pd.DataFrame(st.session_state.scraped_items)
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv,
            f"daraz_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )

tab1, tab2, tab3 = st.tabs(["🔍 Scraper", "📈 Analytics", "💬 AI Chat"])

with tab1:
    st.markdown('<div class="search-box">', unsafe_allow_html=True)
    st.markdown("### 🔎 Auto-Generate Search URLs")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        search_query = st.text_input
