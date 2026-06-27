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
WORDS_URL = "https://raw.githubusercontent.com/moodHappy/DailyFiveWords/refs/heads/main/Collins_1.txt"
TZ_UTC_8 = timezone(timedelta(hours=8))
DAILY_COUNT = 5

RSS_SOURCES = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.npr.org/rss/rss.php?id=1004"
]
# ==========================================

def get_real_news_example(word):
    """扫描今日全球新闻 RSS，寻找包含该单词的真实鲜活例句"""
    pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:  # 每个源扫描前15条
                # 检查标题或摘要
                text_to_check = f"{entry.title}. {entry.get('summary', '')}"
                # 清理 HTML 标签
                clean_text = re.sub(r'<[^>]+>', '', text_to_check)
                if pattern.search(clean_text):
                    # 找到后，截取包含该词的完整句子
                    sentences = re.split(r'(?<=[.!?]) +', clean_text)
                    for sentence in sentences:
                        if pattern.search(sentence):
                            # 高亮单词
                            highlighted = pattern.sub(f"<span class='hl-word'>{word}</span>", sentence)
                            return f"\"{highlighted}\"", entry.title
        except:
            continue
    return None, None

def get_collocations(word):
    """利用 Datamuse API 获取相关固定搭配 (经常跟在该词后面的词)"""
    try:
        res = requests.get(f"https://api.datamuse.com/words?rel_bga={word}&max=5", timeout=5)
        if res.status_code == 200 and res.json():
            return [item['word'] for item in res.json()]
    except: pass
    return []

def fetch_word_details(word, translator):
    """综合查词引警"""
    details = {
        "word": word,
        "phonetic": "",
        "definition_en": "暂无英文释义",
        "definition_zh": "暂无中文释义",
        "synonyms": "无",
        "antonyms": "无",
        "collocations": "无",
        "example": "暂无例句",
        "example_source": "Dictionary"
    }
    
    # 1. 字典 API (释义、音标、同反义词)
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=8)
        if res.status_code == 200:
            data = res.json()[0]
            details["phonetic"] = data.get("phonetics", [{}])[0].get("text", "")
            
            for meaning in data.get("meanings", []):
                for def_obj in meaning.get("definitions", []):
                    details["definition_en"] = def_obj.get("definition", "")
                    if "example" in def_obj:
                        details["example"] = f"\"{def_obj['example']}\""
                    break
                if details["definition_en"] != "暂无英文释义":
                    break
                    
            # 提取同义词和反义词
            syns, ants = [], []
            for meaning in data.get("meanings", []):
                syns.extend(meaning.get("synonyms", []))
                ants.extend(meaning.get("antonyms", []))
            if syns: details["synonyms"] = ", ".join(list(set(syns))[:4])
            if ants: details["antonyms"] = ", ".join(list(set(ants))[:4])
    except: pass

    # 2. 翻译释义
    if details["definition_en"] != "暂无英文释义":
        try:
            details["definition_zh"] = translator.translate(details["definition_en"])
        except: pass

    # 3. 抓取固定搭配
    collocs = get_collocations(word)
    if collocs:
        details["collocations"] = ", ".join([f"{word} {c}" for c in collocs])

    # 4. 尝试抓取真实例句（覆盖字典例句）
    news_ex, news_src = get_real_news_example(word)
    if news_ex:
        details["example"] = news_ex
        details["example_source"] = f"🗞️ News Source: {news_src}"
        
    return details

def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    now_obj = datetime.now(TZ_UTC_8)
    
    # 1. 读取远端总词库
    print("📥 正在拉取 Collins 词库...")
    try:
        res = requests.get(WORDS_URL, timeout=10)
        res.raise_for_status()
        all_words = [w.strip() for w in res.text.splitlines() if w.strip()]
    except Exception as e:
        print(f"❌ 词库加载失败: {e}")
        return

    # 2. 读取本地学习进度
    learned_words = []
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            learned_words = json.load(f).get("learned", [])

    # 3. 挑选今日新词
    today_words = []
    for w in all_words:
        if w not in learned_words:
            today_words.append(w)
        if len(today_words) >= DAILY_COUNT:
            break
            
    if not today_words:
        print("🎉 恭喜！Collins 词库已经全部学完！")
        return

    # 4. 获取多维单词数据
    print(f"🎯 今日目标词汇: {', '.join(today_words)}")
    translator = GoogleTranslator(source='en', target='zh-CN')
    words_data = [fetch_word_details(w, translator) for w in today_words]

    # 5. 生成每日详情页
    generate_daily_page(words_data, now_obj)
    
    # 6. 更新进度并保存
    learned_words.extend(today_words)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"learned": learned_words}, f, ensure_ascii=False, indent=2)
        
    # 7. 重建日历枢纽
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
        cards_html += f"""
        <div class="word-card">
            <div class="word-header">
                <span class="word-index">#{idx+1}</span>
                <h2 class="word-title">{item['word']}</h2>
                <span class="phonetic">{item['phonetic']}</span>
            </div>
            
            <div class="definition-box">
                <div class="def-zh">{item['definition_zh']}</div>
                <div class="def-en">{item['definition_en']}</div>
            </div>
            
            <div class="grid-layout">
                <div class="meta-item"><span class="meta-label">近义词 (Synonyms)</span>{item['synonyms']}</div>
                <div class="meta-item"><span class="meta-label">反义词 (Antonyms)</span>{item['antonyms']}</div>
            </div>
            
            <div class="collocations">
                <span class="meta-label">🔗 常见搭配 (Collocations)</span>
                {item['collocations']}
            </div>
            
            <div class="example-box">
                <span class="meta-label">📰 真实语境 (In Context)</span>
                <div class="sentence">{item['example']}</div>
                <div class="source">{item['example_source']}</div>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Daily 5 Words | {now_str}</title>
    <style>
        :root {{ --bg: #f5f5f7; --card: #ffffff; --text: #1d1d1f; --muted: #86868b; --accent: #0066cc; --border: #e5e5ea; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .nav-back {{ padding: 15px; text-align: center; background: var(--card); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 5px rgba(0,0,0,0.02); }}
        .nav-back a {{ text-decoration: none; color: white; background: var(--accent); padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }}
        
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; box-sizing: border-box; }}
        .header {{ text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px dashed var(--border); }}
        .header h1 {{ margin: 0 0 5px 0; font-size: 1.8rem; color: #1a252f; }}
        .header p {{ margin: 0; color: var(--muted); font-size: 0.9rem; font-weight: bold; }}
        
        .word-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); }}
        .word-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 15px; flex-wrap: wrap; }}
        .word-index {{ background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; }}
        .word-title {{ font-size: 2rem; margin: 0; color: #d35400; text-transform: lowercase; font-family: Georgia, serif; }}
        .phonetic {{ font-size: 1.1rem; color: var(--muted); font-family: monospace; }}
        
        .definition-box {{ background: #fdfbf7; border-left: 4px solid var(--accent); padding: 12px 15px; border-radius: 0 8px 8px 0; margin-bottom: 15px; }}
        .def-zh {{ font-size: 1.1rem; font-weight: bold; color: #2c3e50; margin-bottom: 5px; }}
        .def-en {{ font-size: 0.95rem; color: var(--muted); font-style: italic; }}
        
        .meta-label {{ display: block; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); font-weight: bold; margin-bottom: 4px; }}
        
        .grid-layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }}
        .meta-item {{ background: #f8f9fa; padding: 10px; border-radius: 8px; font-size: 0.9rem; color: #34495e; font-weight: 500; border: 1px solid #f0f0f0; }}
        
        .collocations {{ background: #f0f7ff; padding: 12px; border-radius: 8px; margin-bottom: 15px; font-size: 0.95rem; color: #0050a0; font-weight: 500; }}
        
        .example-box {{ border-top: 1px dashed var(--border); padding-top: 15px; }}
        .sentence {{ font-size: 1.05rem; line-height: 1.6; color: var(--text); margin-bottom: 8px; font-family: Georgia, serif; }}
        .hl-word {{ color: var(--accent); font-weight: bold; text-decoration: underline; text-decoration-color: rgba(0,102,204,0.3); text-decoration-thickness: 3px; }}
        .source {{ font-size: 0.8rem; color: var(--muted); text-align: right; }}
    </style>
</head>
<body>
    <div class="nav-back"><a href="../../index.html">🔙 返回学习日历</a></div>
    <div class="container">
        <div class="header">
            <h1>Daily 5 Words</h1>
            <p>📝 {now_str} · 进阶词汇集训</p>
        </div>
        {cards_html}
    </div>
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
    <title>词汇进阶学习日历</title>
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
        <h1>Collins Vocabulary</h1>
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
