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

# ... [get_youdao_translation, get_youdao_collocations, translate_batch, get_word_image, get_real_news_example, get_wiki_example, get_guaranteed_example, fetch_word_details, build_list_html 等函数保持不变] ...

def get_youdao_translation(word):
    try:
        url = f"https://dict.youdao.com/jsonapi?q={word}"
        res = requests.get(url, timeout=5).json()
        if 'ec' in res and 'word' in res['ec']:
            trs = res['ec']['word'][0]['trs']
            zh_defs = [tr['tr'][0]['l']['i'][0] for tr in trs]
            return "；".join(zh_defs)
    except: return None

def get_youdao_collocations(word):
    try:
        url = f"https://dict.youdao.com/jsonapi?q={word}"
        res = requests.get(url, timeout=5).json()
        collocations = []
        if 'phrs' in res and 'phrs' in res['phrs']:
            for item in res['phrs']['phrs']:
                en = item.get('phr', {}).get('headword', {}).get('l', {}).get('i', '')
                zh = item.get('phr', {}).get('trs', [{}])[0].get('tr', {}).get('l', {}).get('i', '')
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
        pages = res.get('query', {}).get('pages', {})
        for _, page_data in pages.items():
            if 'thumbnail' in page_data: return page_data['thumbnail']['source']
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
                    s = [x for x in re.split(r'(?<=[.!?]) +', text) if pattern.search(x)][0]
                    return f"\"{pattern.sub(f'<span class=\"hl-word\">{word}</span>', s)}\"", f"🗞️ News: {entry.title[:25]}..."
        except: continue
    return None, None

def get_guaranteed_example(word, dict_example=None):
    ex, src = get_real_news_example(word)
    if ex: return ex, src
    if dict_example:
        hl = re.sub(rf'(\b{re.escape(word)}\b)', r"<span class='hl-word'>\1</span>", dict_example, flags=re.IGNORECASE)
        return f"\"{hl}\"", "📖 Dictionary"
    return None, None

def fetch_word_details(word, translator):
    details = {"word": word, "definition_en": "N/A", "definition_zh": get_youdao_translation(word) or "N/A", "explanation": [], "synonyms": [], "antonyms": [], "collocations": get_youdao_collocations(word), "example": None, "example_source": None, "image_url": get_word_image(word)}
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=8).json()[0]
        details["definition_en"] = res["meanings"][0]["definitions"][0]["definition"]
        raw_ex = res["meanings"][0]["definitions"][0].get("example")
        details["example"], details["example_source"] = get_guaranteed_example(word, raw_ex)
    except: pass
    return details

def build_list_html(items):
    html = '<ul class="vertical-list">'
    for i in items:
        zh = f'<span class="trans-zh">({i["zh"]})</span>' if i.get("zh") else ''
        html += f'<li class="editable-node"><span class="en-word">{i["en"]}</span> {zh}</li>'
    return html + '</ul>'

def generate_index():
    print("⚙️ 正在重新编译日历枢纽 (含未来十年支持)...")
    archive_data = {}
    if os.path.exists(BASE_DIR):
        for year in [d for d in os.listdir(BASE_DIR) if d.isdigit()]:
            archive_data[year] = {}
            for month in [d for d in os.listdir(os.path.join(BASE_DIR, year)) if d.isdigit()]:
                archive_data[year][month] = {}
                for file in sorted([f for f in os.listdir(os.path.join(BASE_DIR, year, month)) if f.endswith('.html')], reverse=True):
                    day = file.split('_')[2]
                    if day not in archive_data[year][month]: archive_data[year][month][day] = []
                    archive_data[year][month][day].append({"time": file.split('_')[3][:2]+":"+file.split('_')[3][2:], "path": f"{year}/{month}/{file}", "title": "🎯 5 词连击任务"})

    json_data = json.dumps(archive_data)
    
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Daily Five Words - 学习日历</title>
    <style>
        :root { --bg: #f5f5f7; --text: #333; --primary: #0066cc; }
        body { font-family: -apple-system, sans-serif; background: var(--bg); margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .calendar-wrapper { background: #fff; padding: 20px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .controls { display: flex; gap: 10px; margin-bottom: 15px; justify-content: center; }
        .day-cell { aspect-ratio: 1; display: flex; justify-content: center; align-items: center; cursor: pointer; border-radius: 8px; font-weight: 600; }
        .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; }
        .has-news { color: var(--primary); background: #eef5ff; }
        .feed-item { background: #fff; padding: 15px; margin-bottom: 10px; border-radius: 12px; display: block; text-decoration: none; color: #333; border-left: 4px solid #d35400; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>Daily Five Words</h1><p>每日 5 词集训</p></div>
        <div class="controls">
            <select id="yearSelect"></select>
            <select id="monthSelect"></select>
        </div>
        <div class="calendar-wrapper">
            <div class="days-grid" id="daysGrid"></div>
        </div>
        <div id="feedList" style="margin-top:20px;"></div>
    </div>
    <script>
        const archiveData = {REPLACEME_JSON_DATA};
        const yearSelect = document.getElementById('yearSelect');
        const monthSelect = document.getElementById('monthSelect');
        const daysGrid = document.getElementById('daysGrid');
        
        function init() {
            const now = new Date();
            const currentYear = now.getFullYear();
            // 生成当前年份及未来10年
            for(let i=0; i<=10; i++) {
                let y = currentYear + i;
                let opt = document.createElement('option'); opt.value = y; opt.textContent = y + ' 年';
                yearSelect.appendChild(opt);
            }
            for(let i=1; i<=12; i++) {
                let opt = document.createElement('option'); opt.value = i; opt.textContent = i + ' 月';
                monthSelect.appendChild(opt);
            }
            yearSelect.value = currentYear;
            monthSelect.value = now.getMonth() + 1;
            render();
        }
        function render() {
            daysGrid.innerHTML = '';
            const y = yearSelect.value, m = monthSelect.value;
            const days = new Date(y, m, 0).getDate();
            for(let i=1; i<=days; i++) {
                const div = document.createElement('div');
                div.className = 'day-cell' + (archiveData[y]?.[m]?.[i] ? ' has-news' : '');
                div.textContent = i;
                div.onclick = () => {
                    const data = archiveData[y]?.[m]?.[i];
                    document.getElementById('feedList').innerHTML = data ? data.map(item => `<a href="${item.path}" class="feed-item">${item.time} ➔ ${item.title}</a>`).join('') : '<p>无记录</p>';
                };
                daysGrid.appendChild(div);
            }
        }
        yearSelect.onchange = monthSelect.onchange = render;
        init();
    </script>
</body>
</html>"""
    
    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_template.replace("{REPLACEME_JSON_DATA}", json_data))

def main():
    # ... [main 函数逻辑保持不变] ...
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        res = requests.get(WORDS_URL).text.splitlines()
        all_words = [w.strip() for w in res if w.strip()]
    except: return
    learned = json.load(open(STATE_FILE))["learned"] if os.path.exists(STATE_FILE) else []
    targets = random.sample([w for w in all_words if w not in learned], DAILY_COUNT)
    translator = GoogleTranslator(source='en', target='zh-CN')
    words_data = [fetch_word_details(w, translator) for w in targets]
    
    # 保存页面 (generate_daily_page 内容同前文)
    # ...
    # 省略部分：generate_daily_page 和 generate_index 调用
    # generate_daily_page(words_data, datetime.now(TZ_UTC_8))
    # learned.extend(targets)
    # json.dump({"learned": learned}, open(STATE_FILE, "w", encoding="utf-8"))
    # generate_index()
    print("Done.")

if __name__ == "__main__":
    main()
