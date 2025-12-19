import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import pandas as pd
import json
import time
from datetime import datetime
import re

# Configure page
st.set_page_config(
    page_title="Daraz.lk Scraper Pro",
    page_icon="🛍️",
    layout="wide"
)

# Custom CSS for Daraz branding
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

# Initialize session state
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

# Configure OpenAI
def init_openai():
    api_key = st.session_state.get('api_key', '')
    if api_key:
        return OpenAI(api_key=api_key)
    return None

# Generate search URLs based on query
def generate_search_urls(query, num_pages):
    """Generate Daraz search URLs with pagination"""
    urls = []
    category_name = query.title()
    
    for page in range(1, num_pages + 1):
        url = f"https://www.daraz.lk/catalog/?page={page}&q={query}"
        urls.append({
            'category': f"{category_name} (Page {page})",
            'url': url
        })
    
    return urls

# Scraping function with OpenAI
def scrape_daraz_category(url, category_name, client):
    try:
        # Use CORS proxy
        proxied_url = f"https://corsproxy.io/?{url}"
        response = requests.get(proxied_url, timeout=30)
        response.raise_for_status()
        
        html_content = response.text
        
        # Use OpenAI to extract product data
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

Return ONLY a valid JSON array like:
[
  {{
    "name": "Product Name",
    "sold": 120,
    "reviews": 45,
    "rating": 4.5,
    "seller": "Seller Name",
    "price": 12500,
    "productUrl": "https://www.daraz.lk/products/..."
  }}
]

HTML Content (first 50000 chars):
{html_content[:50000]}
"""
        
        # Call OpenAI API
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data extraction expert. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        # Extract JSON from markdown code blocks if present
        if "```
            response_text = response_text.split("```json").split("```
        elif "```" in response_text:
            response_text = response_text.split("``````")[0].strip()
        
        products = json.loads(response_text)
        
        # Process and score products
        scraped_items = []
        for idx, product in enumerate(products):
            # Calculate product score (weighted formula)
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

# Parse input URLs
def parse_input(input_text):
    lines = input_text.strip().split('\n')
    parsed = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Format: "Category Name, URL" or "Category\tURL" or just "URL"
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
            # Extract category from URL
            cat = url.rstrip('/').split('/')[-1].replace('-', ' ').title()
        else:
            continue
        
        parsed.append({'category': cat, 'url': url})
    
    return parsed

# Main UI
st.markdown('<div class="main-header">🛍️ Daraz.lk Scraper Pro</div>', unsafe_allow_html=True)

# Sidebar - API Key
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
    
    # Model selection
    st.header("🤖 AI Model")
    model_choice = st.selectbox(
        "Choose model:",
        ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        help="gpt-4o-mini is fastest and cheapest"
    )
    st.session_state.model_choice = model_choice
    
    st.markdown("---")
    
    # Funnel filter
    st.header("📊 Funnel Stage Filter")
    selected_stages = st.multiselect(
        "Show stages:",
        ['SCRAPED', 'SELECTED', 'PETTAH_HUB', 'LISTED'],
        default=['SCRAPED']
    )
    
    st.markdown("---")
    
    # Export
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

# Main content
tab1, tab2, tab3 = st.tabs(["🔍 Scraper", "📈 Analytics", "💬 AI Chat"])

with tab1:
    # NEW SEARCH QUERY GENERATOR
    st.markdown('<div class="search-box">', unsafe_allow_html=True)
    st.markdown("### 🔎 Auto-Generate Search URLs")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        search_query = st.text_input(
            "Enter search query:",
            placeholder="e.g., racks, laptops, phones",
            help="Enter a keyword to search on Daraz"
        )
    
    with col2:
        num_pages = st.number_input(
            "Number of pages:",
            min_value=1,
            max_value=50,
            value=3,
            help="How many result pages to scrape?"
        )
    
    if st.button("🎯 Generate URLs", type="primary", use_container_width=True):
        if search_query:
            generated = generate_search_urls(search_query, num_pages)
            url_text = "\n".join([f"{item['category']}\t{item['url']}" for item in generated])
            st.session_state.generated_urls = url_text
            st.success(f"✅ Generated {num_pages} URLs for '{search_query}'")
        else:
            st.error("⚠️ Please enter a search query")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # MANUAL URL INPUT
    st.markdown("### 📋 Input Category URLs")
    st.caption("Paste your category links below OR use the auto-generator above")
    
    sample_input = """Smartphones\thttps://www.daraz.lk/smartphones/
Watches, https://www.daraz.lk/mens-watches/
https://www.daraz.lk/laptops/"""
    
    # Use generated URLs if available, otherwise show sample
    default_input = st.session_state.generated_urls if st.session_state.generated_urls else sample_input
    
    input_text = st.text_area(
        "Enter URLs (one per line)",
        value=default_input,
        height=150,
        help="Format: 'Category Name, URL' or 'Category\\tURL' or just 'URL'"
    )
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        start_scrape = st.button("▶️ Start Scraping", type="primary", use_container_width=True)
    with col2:
        clear_data = st.button("🗑️ Clear Data", use_container_width=True)
    
    if clear_data:
        st.session_state.scraped_items = []
        st.session_state.generated_urls = ""
        st.session_state.scrape_stats = {
            'total_urls': 0,
            'processed_urls': 0,
            'items_found': 0,
            'success_count': 0,
            'fail_count': 0
        }
        st.rerun()
    
    # Stats display
    st.markdown("### 📊 Scraping Progress")
    stats = st.session_state.scrape_stats
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("URLs", f"{stats['processed_urls']}/{stats['total_urls']}")
    col2.metric("Items Found", stats['items_found'])
    col3.metric("Success", stats['success_count'])
    col4.metric("Failed", stats['fail_count'])
    col5.metric("Total Scraped", len(st.session_state.scraped_items))
    
    # Scraping logic
    if start_scrape:
        if not st.session_state.get('api_key'):
            st.error("⚠️ Please enter your OpenAI API key in the sidebar")
        else:
            client = init_openai()
            parsed_urls = parse_input(input_text)
            
            if not parsed_urls:
                st.error("❌ No valid URLs found. Please check your input.")
            else:
                st.session_state.scrape_stats['total_urls'] = len(parsed_urls)
                st.session_state.scrape_stats['processed_urls'] = 0
                st.session_state.scrape_stats['success_count'] = 0
                st.session_state.scrape_stats['fail_count'] = 0
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, url_data in enumerate(parsed_urls):
                    status_text.text(f"Scraping {url_data['category']}...")
                    
                    items, error = scrape_daraz_category(
                        url_data['url'],
                        url_data['category'],
                        client
                    )
                    
                    if error:
                        st.session_state.scrape_stats['fail_count'] += 1
                        st.error(f"❌ Failed to scrape {url_data['category']}: {error}")
                    else:
                        st.session_state.scraped_items.extend(items)
                        st.session_state.scrape_stats['items_found'] += len(items)
                        st.session_state.scrape_stats['success_count'] += 1
                        st.success(f"✓ Scraped {len(items)} items from {url_data['category']}")
                    
                    st.session_state.scrape_stats['processed_urls'] += 1
                    progress_bar.progress((idx + 1) / len(parsed_urls))
                    
                    time.sleep(1)  # Rate limiting
                
                status_text.text("✅ Scraping complete!")
                st.rerun()
    
    # Display scraped items
    st.markdown("### 🛒 Scraped Products")
    
    if st.session_state.scraped_items:
        filtered_items = [
            item for item in st.session_state.scraped_items
            if item['funnelStage'] in selected_stages
        ]
        
        # Sort options
        sort_by = st.selectbox(
            "Sort by:",
            ['score', 'sold', 'reviews', 'rating', 'priceValue'],
            format_func=lambda x: x.replace('Value', '').title()
        )
        
        sorted_items = sorted(filtered_items, key=lambda x: x.get(sort_by, 0), reverse=True)
        
        # Display items
        for item in sorted_items[:50]:  # Limit to 50 for performance
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"**{item['name']}**")
                    st.caption(f"Category: {item['darazCat']} | Seller: {item['seller']}")
                
                with col2:
                    st.write(f"💰 {item['price']}")
                    st.write(f"⭐ {item['rating']} | 📦 {item['sold']} sold | 💬 {item['reviews']} reviews")
                
                with col3:
                    st.markdown(f'<div class="score-badge">Score: {item["score"]}</div>', unsafe_allow_html=True)
                    st.write(f"Stage: {item['funnelStage']}")
                
                st.markdown(f"[View Product]({item['productUrl']})")
                st.markdown("---")
    else:
        st.info("📭 No data available. Run a scrape to see results here.")

with tab2:
    st.markdown("### 📈 Product Analytics")
    
    if st.session_state.scraped_items:
        df = pd.DataFrame(st.session_state.scraped_items)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Top 10 Products by Score")
            top_products = df.nlargest(10, 'score')[['name', 'score', 'sold', 'rating']]
            st.dataframe(top_products, use_container_width=True, hide_index=True)
        
        with col2:
            st.markdown("#### Category Distribution")
            cat_counts = df['darazCat'].value_counts()
            st.bar_chart(cat_counts)
        
        st.markdown("#### Price vs Score Analysis")
        chart_data = df[['priceValue', 'score', 'name']].head(50)
        st.scatter_chart(chart_data, x='priceValue', y='score')
        
    else:
        st.info("📭 No data available. Run a scrape to see analytics.")

with tab3:
    st.markdown("### 💬 AI Product Insights")
    
    if not st.session_state.get('api_key'):
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar")
    else:
        # Chat interface
        for msg in st.session_state.chat_history:
            with st.chat_message(msg['role']):
                st.write(msg['text'])
        
        user_input = st.chat_input("Ask about your scraped products...")
        
        if user_input:
            st.session_state.chat_history.append({'role': 'user', 'text': user_input})
            
            with st.chat_message('user'):
                st.write(user_input)
            
            # Generate AI response
            client = init_openai()
            
            context = f"""
You are a data analysis assistant. The user has scraped {len(st.session_state.scraped_items)} products from Daraz.lk.

Sample data (first 5 products):
{json.dumps(st.session_state.scraped_items[:5], indent=2)}

User question: {user_input}

Provide insights based on the data.
"""
            
            completion = client.chat.completions.create(
                model=st.session_state.get('model_choice', 'gpt-4o-mini'),
                messages=[
                    {"role": "system", "content": "You are a helpful data analysis assistant."},
                    {"role": "user", "content": context}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            ai_text = completion.choices[0].message.content
            
            st.session_state.chat_history.append({'role': 'assistant', 'text': ai_text})
            
            with st.chat_message('assistant'):
                st.write(ai_text)
