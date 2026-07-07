
import os
import json
import requests
import feedparser
import re
import random
from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator

# ================= 配置区 =================
BASE_DIR = "docs"
STATE_FILE = os.path.join(BASE_DIR, "learned.json")
WORDS_URL = "https://raw.githubusercontent.com/moodHappy/DailyFiveWords/refs/heads/main/docs/Collins_1.txt"
TZ_UTC_8 = timezone(timedelta(hours=8))
DAILY_COUNT = 5

RSS_SOURCES = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.npr.org/rss/rss.php?id=1004"
]
# ==========================================

# ... (保持原有的 get_youdao_translation, get_youdao_collocations, translate_batch, get_word_image, get_real_news_example, get_wiki_example, get_guaranteed_example, fetch_word_details 函数不变) ...

def get_youdao_translation(word):
    try:
        url = f"https://dict.youdao.com/jsonapi?q={word}"
        res = requests.get(url, timeout=5).json()
        if 'ec' in res and 'word' in res['ec']:
            trs = res['ec']['word'][0]['trs']
            zh_defs = [tr['tr'][0]['l']['i'][0] for tr in trs]
            return "；".join(zh_defs)
    except: pass
    return None

def get_youdao_collocations(word):
    try:
        url = f"https://dict.youdao.com/jsonapi?q={word}"
        res = requests.get(url, timeout=5).json()
        collocations = []
        if 'phrs' in res and 'phrs' in res['phrs']:
            for item in res['phrs']['phrs']:
                en = item.get('phr', {}).get('headword', {}).get('l', {}).get('i', '')
                try: zh = item['phr']['trs'][0]['tr']['l']['i']
                except: zh = ""
                if en: collocations.append({"en": en, "zh": zh})
                if len(collocations) >= 5: break
        return collocations
    except: return []

def translate_batch(text_list, translator):
    if not text_list: return []
    try:
        combined = " | ".join(text_list)
        translated = translator.translate(combined)
        return [t.strip() for t in translated.split("|")]
    except: return text_list

def get_word_image(word):
    try:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={word}&prop=pageimages&format=json&pithumbsize=800"
        res = requests.get(wiki_url, timeout=5).json()
        for p in res.get('query', {}).get('pages', {}).values():
            if 'thumbnail' in p: return p['thumbnail']['source']
    except: pass
    return None

def get_real_news_example(word):
    pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                text = re.sub(r'<[^>]+>', '', f"{entry.title}. {entry.get('summary', '')}")
                if pattern.search(text):
                    s = next((s for s in re.split(r'(?<=[.!?]) +', text) if pattern.search(s)), None)
                    if s: return f"\"{pattern.sub(f'<span class=\"hl-word\">{word}</span>', s.strip())}\"", f"🗞️ News: {entry.title[:30]}..."
        except: continue
    return None, None

def get_guaranteed_example(word, dict_example=None):
    ex, src = get_real_news_example(word)
    if ex: return ex, src
    if dict_example: return f"\"{dict_example}\"", "📖 Dictionary"
    return None, None

def fetch_word_details(word, translator):
    details = {"word": word, "definition_en": "暂无英文释义", "definition_zh": "暂无中文释义", "explanation": [], "synonyms": [], "antonyms": [], "collocations": [], "example": None, "example_source": None, "image_url": None}
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=8).json()[0]
        details["definition_en"] = res["meanings"][0]["definitions"][0]["definition"]
        dict_ex = res["meanings"][0]["definitions"][0].get("example")
        details["synonyms"] = [{"en": s, "zh": "..."} for s in res["meanings"][0].get("synonyms", [])[:3]]
    except: pass
    details["definition_zh"] = get_youdao_translation(word) or "..."
    details["collocations"] = get_youdao_collocations(word)
    details["example"], details["example_source"] = get_guaranteed_example(word, dict_ex if 'dict_ex' in locals() else None)
    details["image_url"] = get_word_image(word)
    return details

def build_list_html(items):
    html = '<ul class="vertical-list">'
    for item in items:
        html += f'<li class="editable-node"><span class="en-word">{item["en"]}</span></li>'
    return html + '</ul>'

def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        res = requests.get(WORDS_URL, timeout=10)
        all_words = [w.strip() for w in res.text.splitlines() if w.strip()]
    except: return
    
    learned = json.load(open(STATE_FILE, "r", encoding="utf-8"))["learned"] if os.path.exists(STATE_FILE) else []
    unlearned = [w for w in all_words if w not in learned]
    if not unlearned: return
    
    today_words = random.sample(unlearned, min(DAILY_COUNT, len(unlearned)))
    translator = GoogleTranslator(source='en', target='zh-CN')
    words_data = [fetch_word_details(w, translator) for w in today_words]
    
    generate_daily_page(words_data, datetime.now(TZ_UTC_8))
    
    learned.extend(today_words)
    json.dump({"learned": learned}, open(STATE_FILE, "w", encoding="utf-8"), indent=2)
    generate_index()

def generate_daily_page(words_data, now_obj):
    # ... (generate_daily_page 函数逻辑保持与你原代码一致) ...
    pass

def generate_index():
    print("⚙️ 正在重新编译日历枢纽...")
    archive_data = {}
    if os.path.exists(BASE_DIR):
        for year in [d for d in os.listdir(BASE_DIR) if d.isdigit()]:
            archive_data[year] = {}
            for month in [d for d in os.listdir(os.path.join(BASE_DIR, year)) if d.isdigit()]:
                archive_data[year][month] = {file.split('_')[2]: [{"time": f"{file.split('_')[3][:2]}:{file.split('_')[3][2:]}", "path": f"{year}/{month}/{file}", "title": "🎯 5 词连击"}] 
                                            for file in os.listdir(os.path.join(BASE_DIR, year, month)) if file.endswith('.html')}

    json_data = json.dumps(archive_data)
    html_template = """
    <script>
        const archiveData = {REPLACEME_JSON_DATA};
        const today = new Date();
        // 核心修改：生成未来 10 年
        function initDropdowns() {
            let startYear = today.getFullYear();
            for (let i = 0; i <= 10; i++) {
                let y = startYear + i;
                const opt = document.createElement('option');
                opt.value = y; opt.textContent = y + ' 年';
                yearSelect.appendChild(opt);
            }
            yearSelect.value = today.getFullYear();
            monthSelect.value = today.getMonth() + 1;
        }
        // ... 其余 JS 逻辑 ...
    </script>
    """
    # ... 写入 index.html ...
