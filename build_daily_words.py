import os
import json
import requests
import feedparser
import re
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

def translate_batch(text_list, translator):
    if not text_list: return []
    try:
        combined = " | ".join(text_list)
        translated = translator.translate(combined)
        if translated:
            return [t.strip() for t in translated.split("|")]
    except Exception as e:
        print(f"翻译失败: {e}")
    return text_list

def get_word_image(word):
    """自动获取单词相关的高清配图，优先维基百科，兜底维基共享资源"""
    try:
        # 1. 尝试获取维基百科词条的首图
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={word}&prop=pageimages&format=json&pithumbsize=800"
        res = requests.get(wiki_url, timeout=5).json()
        pages = res.get('query', {}).get('pages', {})
        for page_id, page_data in pages.items():
            if 'thumbnail' in page_data:
                return page_data['thumbnail']['source']
    except: pass

    try:
        # 2. 尝试从维基共享资源中搜索图片
        commons_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={word}&gsrnamespace=6&gsrlimit=1&prop=imageinfo&iiprop=url&format=json"
        res = requests.get(commons_url, timeout=5).json()
        pages = res.get('query', {}).get('pages', {})
        for page_id, page_data in pages.items():
            image_info = page_data.get('imageinfo', [])
            if image_info:
                return image_info[0].get('url')
    except: pass

    return None

def get_real_news_example(word):
    pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                text_to_check = f"{entry.title}. {entry.get('summary', '')}"
                clean_text = re.sub(r'<[^>]+>', '', text_to_check)
                if pattern.search(clean_text):
                    sentences = re.split(r'(?<=[.!?]) +', clean_text)
                    for sentence in sentences:
                        if pattern.search(sentence):
                            hl_sentence = pattern.sub(f"<span class='hl-word'>{word}</span>", sentence.strip())
                            return f"\"{hl_sentence}\"", f"🗞️ News: {entry.title[:35]}..."
        except:
            continue
    return None, None

def get_wiki_example(word):
    try:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=%22{word}%22&utf8=&format=json&srlimit=3"
        res = requests.get(wiki_url, timeout=5).json()
        for item in res.get('query', {}).get('search', []):
            snippet = re.sub(r'<[^>]+>', '', item['snippet'])
            sentences = re.split(r'(?<=[.!?]) +', snippet)
            for s in sentences:
                if re.search(rf'\b{re.escape(word)}\b', s, re.IGNORECASE):
                    hl_sentence = re.sub(rf'(\b{re.escape(word)}\b)', r"<span class='hl-word'>\1</span>", s.strip(), flags=re.IGNORECASE)
                    return f"\"{hl_sentence}...\"", f"📚 Wikipedia: {item['title']}"
    except: pass
    return None, None

def get_guaranteed_example(word, dict_example=None):
    ex, src = get_real_news_example(word)
    if ex: return ex, src

    ex, src = get_wiki_example(word)
    if ex: return ex, src

    if dict_example and dict_example != "No example available.":
        hl_sentence = re.sub(rf'(\b{re.escape(word)}\b)', r"<span class='hl-word'>\1</span>", dict_example, flags=re.IGNORECASE)
        return f"\"{hl_sentence}\"", "📖 Dictionary Example"

    return None, None

def get_collocations(word):
    try:
        res = requests.get(f"https://api.datamuse.com/words?rel_bga={word}&max=30", timeout=5)
        if res.status_code == 200:
            valid_collocs = []
            stop_words = {'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'by', 'of', 'for', 'with', 'is', 'are'}
            for item in res.json():
                cw = item['word'].strip()
                if re.match(r'^[a-zA-Z]+$', cw) and len(cw) > 2 and cw.lower() not in stop_words:
                    valid_collocs.append(cw)
                if len(valid_collocs) >= 5:
                    break
            return valid_collocs
    except: pass
    return []

def fetch_word_details(word, translator):
    details = {
        "word": word,
        "phonetic": "",
        "definition_en": "暂无英文释义",
        "definition_zh": "暂无中文释义",
        "explanation": [], 
        "synonyms": [],
        "antonyms": [],
        "collocations": [],
        "example": None,
        "example_source": None,
        "image_url": None
    }

    dict_example_raw = None
    extra_meanings = []

    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=8)
        if res.status_code == 200:
            data = res.json()[0]
            details["phonetic"] = data.get("phonetics", [{}])[0].get("text", "")

            for meaning in data.get("meanings", []):
                pos = meaning.get("partOfSpeech", "unknown")
                for i, def_obj in enumerate(meaning.get("definitions", [])):
                    if details["definition_en"] == "暂无英文释义":
                        details["definition_en"] = def_obj.get("definition", "")
                    else:
                        extra_meanings.append(f"As {pos}: {def_obj.get('definition', '')}")

                    if "example" in def_obj and not dict_example_raw:
                        dict_example_raw = def_obj['example']

                details["synonyms"].extend(meaning.get("synonyms", []))
                details["antonyms"].extend(meaning.get("antonyms", []))

            details["synonyms"] = list(set(details["synonyms"]))[:5]
            details["antonyms"] = list(set(details["antonyms"]))[:5]

            if extra_meanings:
                details["explanation"] = extra_meanings[:2]
    except: pass

    if details["definition_en"] != "暂无英文释义":
        try:
            details["definition_zh"] = translator.translate(details["definition_en"])
        except: pass

    if details["explanation"]:
        try:
            exp_zh = translate_batch(details["explanation"], translator)
            details["explanation"] = exp_zh
        except: pass
    else:
        details["explanation"] = ["该词含义较单一，多在固定搭配中直接使用。"]

    if details["synonyms"]:
        syn_zh = translate_batch(details["synonyms"], translator)
        details["synonyms"] = [{"en": en, "zh": zh} for en, zh in zip(details["synonyms"], syn_zh)]

    if details["antonyms"]:
        ant_zh = translate_batch(details["antonyms"], translator)
        details["antonyms"] = [{"en": en, "zh": zh} for en, zh in zip(details["antonyms"], ant_zh)]

    collocs_words = get_collocations(word)
    if collocs_words:
        phrases = [f"{word} {c}" for c in collocs_words]
        phrases_zh = translate_batch(phrases, translator)
        details["collocations"] = [{"en": p, "zh": zh} for p, zh in zip(phrases, phrases_zh)]

    details["example"], details["example_source"] = get_guaranteed_example(word, dict_example_raw)

    # 获取图片
    details["image_url"] = get_word_image(word)

    return details

def build_list_html(items):
    if not items:
        return ""
    html = '<ul class="vertical-list">'
    for item in items:
        zh_text = f'<span class="trans-zh">({item["zh"]})</span>' if item.get("zh") and item["zh"] != item["en"] else ''
        html += f'<li><span class="en-word">{item["en"]}</span> {zh_text}</li>'
    html += '</ul>'
    return html

def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    now_obj = datetime.now(TZ_UTC_8)

    print("📥 正在拉取 Collins 词库...")
    try:
        res = requests.get(WORDS_URL, timeout=10)
        res.raise_for_status()
        all_words = [w.strip() for w in res.text.splitlines() if w.strip()]
    except Exception as e:
        print(f"❌ 词库加载失败: {e}")
        return

    learned_words = []
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            learned_words = json.load(f).get("learned", [])

    today_words = []
    for w in all_words:
        if w not in learned_words:
            today_words.append(w)
        if len(today_words) >= DAILY_COUNT:
            break

    if not today_words:
        print("🎉 恭喜！词库已经全部学完！")
        return

    print(f"🎯 今日目标词汇: {', '.join(today_words)}")
    translator = GoogleTranslator(source='en', target='zh-CN')
    words_data = [fetch_word_details(w, translator) for w in today_words]

    generate_daily_page(words_data, now_obj)

    learned_words.extend(today_words)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"learned": learned_words}, f, ensure_ascii=False, indent=2)

    generate_index()

def generate_daily_page(words_data, now_obj):
    year_str, month_str = str(now_obj.year), str(now_obj.month)
    target_dir = os.path.join(BASE_DIR, year_str, month_str)
    os.makedirs(target_dir, exist_ok=True)

    filename = f"{now_obj.year}_{now_obj.month}_{now_obj.day}_{now_obj.strftime('%H%M')}.html"
    html_path = os.path.join(target_dir, filename)
    now_str = now_obj.strftime("%Y-%m-%d")

    cards_html = ""
    for idx, item in enumerate(words_data):
        exp_list = "".join([f"<li>💡 <span class='trans-zh'>{e}</span></li>" for e in item['explanation']])
        exp_html = f'<div class="meta-card exp-box"><span class="meta-label">📚 讲解与辨析 (Explanation)</span><ul class="vertical-list exp-list">{exp_list}</ul></div>'

        # 动态图片区块
        img_html = ""
        if item['image_url']:
            img_html = f'<div class="meta-card img-box"><img src="{item["image_url"]}" alt="{item["word"]}"></div>'

        syn_list = build_list_html(item['synonyms'])
        ant_list = build_list_html(item['antonyms'])

        grid_html = ""
        if syn_list or ant_list:
            grid_html += '<div class="grid-layout">'
            if syn_list: grid_html += f'<div class="meta-card"><span class="meta-label">近义词 (Synonyms)</span>{syn_list}</div>'
            if ant_list: grid_html += f'<div class="meta-card"><span class="meta-label">反义词 (Antonyms)</span>{ant_list}</div>'
            grid_html += '</div>'

        col_list = build_list_html(item['collocations'])
        col_html = f'<div class="meta-card collocations-box"><span class="meta-label">🔗 常见搭配 (Collocations)</span>{col_list}</div>' if col_list else ""

        example_html = ""
        if item['example']:
            example_html = f"""
            <div class="example-box">
                <span class="meta-label">📰 真实语境 (In Context)</span>
                <div class="sentence">{item['example']}</div>
                <div class="source">{item['example_source']}</div>
            </div>
            """

        # 默认折叠排版结构
        cards_html += f"""
        <div class="word-card">
            <div class="word-header" onclick="toggleCard({idx})" title="点击展开/折叠">
                <div class="header-left">
                    <span class="word-index">#{idx+1}</span>
                    <h2 class="word-title">{item['word']}</h2>
                    <span class="phonetic">{item['phonetic']}</span>
                </div>
                <div class="header-right" id="arrow-{idx}">▼</div>
            </div>
            
            <div id="content-{idx}" class="word-content" style="display: none;">
                <div class="definition-box">
                    <div class="def-zh">{item['definition_zh']}</div>
                    <div class="def-en">{item['definition_en']}</div>
                </div>
                
                {exp_html}
                {img_html}
                {grid_html}
                {col_html}
                {example_html}
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Daily Five Words | {now_str}</title>
    <style>
        :root {{ --bg: #f5f5f7; --card: #ffffff; --text: #1d1d1f; --muted: #86868b; --accent: #0066cc; --border: #e5e5ea; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .nav-back {{ padding: 15px; text-align: center; background: var(--card); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 5px rgba(0,0,0,0.02); }}
        .nav-back a {{ text-decoration: none; color: white; background: var(--accent); padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }}
        
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; box-sizing: border-box; }}
        .header {{ text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px dashed var(--border); }}
        .header h1 {{ margin: 0 0 5px 0; font-size: 1.8rem; color: #1a252f; }}
        .header p {{ margin: 0; color: var(--muted); font-size: 0.9rem; font-weight: bold; }}
        
        .word-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); transition: all 0.2s ease; }}
        .word-header {{ display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; -webkit-tap-highlight-color: transparent; }}
        .header-left {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
        .header-right {{ font-size: 1.2rem; color: var(--muted); transition: transform 0.3s ease; }}
        
        .word-index {{ background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; }}
        .word-title {{ font-size: 2.2rem; margin: 0; color: #d35400; text-transform: lowercase; font-family: Georgia, serif; }}
        .phonetic {{ font-size: 1.1rem; color: var(--muted); font-family: monospace; }}
        
        .word-content {{ margin-top: 18px; padding-top: 15px; border-top: 1px solid #f0f0f0; }}
        
        .definition-box {{ background: #fdfbf7; border-left: 4px solid var(--accent); padding: 12px 15px; border-radius: 0 8px 8px 0; margin-bottom: 15px; }}
        .def-zh {{ font-size: 1.1rem; font-weight: bold; color: #2c3e50; margin-bottom: 5px; }}
        .def-en {{ font-size: 0.95rem; color: var(--muted); font-style: italic; }}
        
        .meta-label {{ display: block; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
        
        .grid-layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }}
        .meta-card {{ background: #f8f9fa; padding: 12px; border-radius: 8px; border: 1px solid #f0f0f0; margin-bottom: 15px; }}
        .collocations-box {{ background: #f0f7ff; border-color: #e1efff; }}
        .exp-box {{ background: #fffcf0; border-color: #fce8b2; }}
        
        .img-box {{ padding: 0; overflow: hidden; display: flex; justify-content: center; background: #fafafa; border: none; }}
        .img-box img {{ max-width: 100%; height: auto; border-radius: 8px; }}
        
        .vertical-list {{ list-style: none; padding: 0; margin: 0; }}
        .vertical-list li {{ margin-bottom: 6px; font-size: 0.95rem; line-height: 1.4; display: block; }}
        .vertical-list li:last-child {{ margin-bottom: 0; }}
        .exp-list li {{ color: #5c4d22; font-size: 0.9rem; }}
        .en-word {{ color: #2c3e50; font-weight: 600; font-family: Georgia, serif; font-size: 1.05rem; margin-right: 6px; }}
        .trans-zh {{ color: #7f8c8d; font-size: 0.85rem; }}
        
        .example-box {{ border-top: 1px dashed var(--border); padding-top: 15px; margin-top: 15px; }}
        .sentence {{ font-size: 1.05rem; line-height: 1.6; color: var(--text); margin-bottom: 8px; font-family: Georgia, serif; }}
        .hl-word {{ color: var(--accent); font-weight: bold; text-decoration: underline; text-decoration-color: rgba(0,102,204,0.3); text-decoration-thickness: 3px; }}
        .source {{ font-size: 0.8rem; color: var(--muted); text-align: right; font-weight: bold; }}
        
        @media (max-width: 500px) {{
            .grid-layout {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="nav-back"><a href="../../index.html">🔙 返回学习日历</a></div>
    <div class="container">
        <div class="header">
            <h1>Daily Five Words</h1>
            <p>📝 {now_str} · 进阶词汇集训</p>
        </div>
        {cards_html}
    </div>
    
    <script>
        function toggleCard(index) {{
            const content = document.getElementById('content-' + index);
            const arrow = document.getElementById('arrow-' + index);
            if (content.style.display === 'none') {{
                content.style.display = 'block';
                arrow.style.transform = 'rotate(180deg)';
            }} else {{
                content.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            }}
        }}
    </script>
</body>
</html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 每日单词卡片已生成: {html_path}")

def generate_index():
    print("⚙️ 正在重新编译日历枢纽...")
    archive_data = {}
    if os.path.exists(BASE_DIR):
        years = [d for d in os.listdir(BASE_DIR) if d.isdigit()]
        for year in years:
            archive_data[year] = {}
            months = [d for d in os.listdir(os.path.join(BASE_DIR, year)) if d.isdigit()]
            for month in months:
                archive_data[year][month] = {}
                files = sorted([f for f in os.listdir(os.path.join(BASE_DIR, year, month)) if f.endswith('.html')], reverse=True)
                for file in files:
                    try:
                        parts = file.replace(".html", "").split('_')
                        if len(parts) >= 4:
                            day = parts[2]
                            time_str = f"{parts[3][:2]}:{parts[3][2:]}"
                            file_path = f"{year}/{month}/{file}"

                            if day not in archive_data[year][month]:
                                archive_data[year][month][day] = []

                            archive_data[year][month][day].append({
                                "time": time_str,
                                "path": file_path,
                                "title": "🎯 5 词连击任务"
                            })
                    except: pass

    json_data = json.dumps(archive_data)

    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Daily Five Words - 学习日历</title>
    <style>
        :root { --bg: #f5f5f7; --text: #333; --muted: #888; --primary: #0066cc; --border: #e0e0e0; --card: #fff; }
        body, html { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif; -webkit-font-smoothing: antialiased; background: var(--bg); margin: 0; padding: 0; color: var(--text); height: 100%; }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 20px; box-sizing: border-box;}
        
        .header-panel { text-align: center; padding: 35px 20px 20px 20px; border-bottom: 1px solid var(--border); background: var(--card); margin-bottom: 20px;}
        .header-panel h1 { font-size: 2.2rem; font-weight: 800; margin: 0 0 8px 0; color: #1a252f; }
        .header-panel p { margin: 0; font-size: 0.85rem; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); font-weight: 600;}
        
        .controls { background: var(--bg); padding: 0 20px 15px 20px; display: flex; justify-content: center; align-items: center; gap: 10px; }
        .control-btn { background: var(--primary); color: #fff; border: none; border-radius: 8px; padding: 8px 14px; font-size: 14px; cursor: pointer; font-weight: bold; transition: all 0.2s; }
        .control-btn:active { opacity: 0.8; transform: scale(0.95); }
        .select-box { padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 15px; background: #fff; outline: none; font-weight: bold; cursor: pointer; }
        
        .calendar-wrapper { background: var(--card); padding: 20px; margin: 0 15px 20px 15px; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); }
        .weekdays { display: grid; grid-template-columns: repeat(7, 1fr); text-align: center; font-weight: bold; font-size: 13px; color: var(--muted); margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
        .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
        .day-cell { aspect-ratio: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; position: relative; transition: all 0.2s; }
        .day-cell.empty { visibility: hidden; }
        .day-cell.has-news { color: var(--text); }
        .day-cell.no-news { color: #ccc; }
        .day-cell.selected { background: #eef5ff; border: 1px solid var(--primary); color: var(--primary); }
        .day-cell.today { background: #f0f0f0; border: 1px solid #ddd; }
        .dot { width: 5px; height: 5px; background-color: var(--primary); border-radius: 50%; position: absolute; bottom: 6px; display: none; }
        .day-cell.has-news .dot { display: block; }
        
        .feed-list { padding: 0 15px; display: flex; flex-direction: column; gap: 12px; }
        .feed-item { background: var(--card); border-radius: 14px; padding: 18px; display: flex; align-items: center; text-decoration: none; color: var(--text); box-shadow: 0 2px 8px rgba(0,0,0,0.03); border-left: 4px solid #d35400; transition: all 0.2s; }
        .feed-item:active { transform: scale(0.98); background: #fafafa; }
        .feed-time { font-size: 15px; font-weight: bold; color: #d35400; font-family: monospace; }
        .feed-title { font-size: 15px; font-weight: bold; color: #333; margin-left: 15px; flex: 1; }
        .empty-state { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 14px; background: var(--card); border-radius: 14px; border: 1px dashed #ccc;}
    </style>
</head>
<body>
    <div class="header-panel">
        <h1>Daily Five Words</h1>
        <p>每日 5 词集训日历</p>
    </div>
    <div class="container">
        <div class="controls">
            <button class="control-btn" id="prevBtn">&lt;</button>
            <select class="select-box" id="yearSelect"></select>
            <select class="select-box" id="monthSelect">
                <option value="1">01月</option><option value="2">02月</option><option value="3">03月</option>
                <option value="4">04月</option><option value="5">05月</option><option value="6">06月</option>
                <option value="7">07月</option><option value="8">08月</option><option value="9">09月</option>
                <option value="10">10月</option><option value="11">11月</option><option value="12">12月</option>
            </select>
            <button class="control-btn" id="nextBtn">&gt;</button>
            <button class="control-btn" id="todayBtn">今日</button>
        </div>
        <div class="calendar-wrapper">
            <div class="weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
            <div class="days-grid" id="daysGrid"></div>
        </div>
        <div class="feed-list" id="feedList"></div>
    </div>

    <script>
        const archiveData = {REPLACEME_JSON_DATA};
        const today = new Date();
        let selectedYear = today.getFullYear();
        let selectedMonth = today.getMonth() + 1;
        let selectedDay = today.getDate();

        const yearSelect = document.getElementById('yearSelect');
        const monthSelect = document.getElementById('monthSelect');
        const daysGrid = document.getElementById('daysGrid');
        const feedList = document.getElementById('feedList');

        function initDropdowns() {
            const years = Object.keys(archiveData).map(Number).sort((a, b) => b - a);
            if (!years.includes(selectedYear)) years.unshift(selectedYear);
            years.forEach(y => {
                const opt = document.createElement('option'); opt.value = y; opt.textContent = y + ' 年';
                yearSelect.appendChild(opt);
            });
            yearSelect.value = selectedYear; monthSelect.value = selectedMonth;
        }

        function renderCalendar(year, month) {
            daysGrid.innerHTML = '';
            const firstDay = new Date(year, month - 1, 1).getDay();
            const startDay = firstDay === 0 ? 7 : firstDay;
            const daysInMonth = new Date(year, month, 0).getDate();
            
            for (let i = 1; i < startDay; i++) {
                const empty = document.createElement('div'); empty.className = 'day-cell empty';
                daysGrid.appendChild(empty);
            }
            
            const monthData = (archiveData[year] && archiveData[year][month]) ? archiveData[year][month] : {};
            
            for (let day = 1; day <= daysInMonth; day++) {
                const cell = document.createElement('div'); cell.className = 'day-cell'; cell.textContent = day;
                const dot = document.createElement('div'); dot.className = 'dot'; cell.appendChild(dot);
                
                if (monthData[day] && monthData[day].length > 0) cell.classList.add('has-news'); else cell.classList.add('no-news');
                if (year === today.getFullYear() && month === today.getMonth() + 1 && day === today.getDate()) cell.classList.add('today');
                if (year === selectedYear && month === selectedMonth && day === selectedDay) cell.classList.add('selected');
                
                cell.addEventListener('click', () => {
                    selectedYear = year; selectedMonth = month; selectedDay = day;
                    renderCalendar(year, month); renderFeedList(year, month, day);
                });
                daysGrid.appendChild(cell);
            }
        }

        function renderFeedList(year, month, day) {
            feedList.innerHTML = '';
            const monthData = (archiveData[year] && archiveData[year][month]) ? archiveData[year][month] : null;
            const dayData = monthData ? monthData[day] : null;
            
            if (dayData && dayData.length > 0) {
                dayData.forEach(item => {
                    const a = document.createElement('a'); a.href = item.path; a.className = 'feed-item';
                    a.innerHTML = `<span class="feed-time">${item.time}</span><span class="feed-title">${item.title}</span> ➔`;
                    feedList.appendChild(a);
                });
            } else {
                feedList.innerHTML = '<div class="empty-state">今日暂无学习记录</div>';
            }
        }

        yearSelect.addEventListener('change', (e) => { selectedYear = parseInt(e.target.value); renderCalendar(selectedYear, selectedMonth); });
        monthSelect.addEventListener('change', (e) => { selectedMonth = parseInt(e.target.value); renderCalendar(selectedYear, selectedMonth); });
        document.getElementById('prevBtn').addEventListener('click', () => { selectedMonth--; if (selectedMonth < 1) { selectedMonth = 12; selectedYear--; yearSelect.value = selectedYear; } monthSelect.value = selectedMonth; renderCalendar(selectedYear, selectedMonth); });
        document.getElementById('nextBtn').addEventListener('click', () => { selectedMonth++; if (selectedMonth > 12) { selectedMonth = 1; selectedYear++; yearSelect.value = selectedYear; } monthSelect.value = selectedMonth; renderCalendar(selectedYear, selectedMonth); });
        document.getElementById('todayBtn').addEventListener('click', () => { selectedYear = today.getFullYear(); selectedMonth = today.getMonth() + 1; selectedDay = today.getDate(); yearSelect.value = selectedYear; monthSelect.value = selectedMonth; renderCalendar(selectedYear, selectedMonth); renderFeedList(selectedYear, selectedMonth, selectedDay); });

        initDropdowns(); renderCalendar(selectedYear, selectedMonth); renderFeedList(selectedYear, selectedMonth, selectedDay);
    </script>
</body>
</html>"""

    final_html = html_template.replace("{REPLACEME_JSON_DATA}", json_data)
    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(final_html)
    print("🚀 主页日历枢纽 index.html 编译同步完成！")

if __name__ == "__main__":
    main()