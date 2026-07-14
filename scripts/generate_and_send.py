#!/usr/bin/env python3
"""
每日汽车热点 - GitHub Actions 云端版
DeepSeek 抓新闻 + TokenHub 混元生图 + QQ邮箱发送
电脑关机也能跑，每天10:00自动推送
"""

import os, re, json, html as html_mod, smtplib, datetime, time, requests, base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from pathlib import Path
from io import BytesIO

# ==================== 配置 ====================
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SENDER = "740418164@qq.com"
PASSWORD = os.environ["QMAIL_AUTH_CODE"]
RECEIVER = "740418164@qq.com"

DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
TOKENHUB_KEY = os.environ["TOKENHUB_API_KEY"]
TOKENHUB_IMAGE_URL = "https://tokenhub.tencentmaas.com/v1/api/image/lite"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ==================== 新闻抓取 ====================
def fetch_raw_news():
    texts = []
    sources = [
        ("盖世汽车", "https://auto.gasgoo.com/"),
        ("汽车之家", "https://www.autohome.com.cn/all/"),
        ("IT之家汽车", "https://www.ithome.com/tag/qiche"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "zh-CN,zh;q=0.9"}
    for name, url in sources:
        try:
            r = requests.get(url, timeout=15, headers=headers)
            if r.status_code == 200:
                t = re.sub(r'<script[^>]*>.*?</script>', '', r.text, flags=re.DOTALL)
                t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
                t = re.sub(r'<[^>]+>', ' ', t)
                t = re.sub(r'\s+', ' ', t)
                texts.append(f"【{name}】\n{t[:5000]}")
                print(f"[OK] {name}")
        except Exception as e:
            print(f"[WARN] {name}: {e}")
    return "\n\n".join(texts) if texts else ""

# ==================== DeepSeek ====================
def call_deepseek(prompt, system="", temp=0.7):
    try:
        r = requests.post("https://api.deepseek.com/chat/completions", json={
            "model": "deepseek-chat", "messages": [{"role":"system","content":system},{"role":"user","content":prompt}],
            "temperature": temp, "max_tokens": 2048,
        }, headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] DeepSeek: {e}")
        return ""

def analyze_news(raw, today):
    system = """你是资深汽车编辑。精选5条最有价值的今日汽车热点。要求：
1. 每条新闻标题清晰 + ≤20字概括
2. 封面标题≤10字，要吸引眼球
3. 内容多元，优先新车/政策/销量/技术
4. 严格JSON输出"""

    prompt = f"""今天是{today}。精选5条汽车热点：
{raw[:6000]}

JSON格式：
```json
{{"cover_title":"≤10字","news":[{{"title":"标题","summary":"≤20字概括","source":"来源","img_prompt":"英文,用于AI生成该新闻的图片配图,要具体到车型/场景,真实照片风格,小红书卡片"}}]}}
```"""

    result = call_deepseek(prompt, system, 0.8)
    try:
        m = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
        data = json.loads(m.group(1) if m else result)
        for item in data.get("news", [])[:5]:
            item.setdefault("title", "快讯")
            item.setdefault("summary", item["title"][:20])
            item.setdefault("source", "综合")
            item.setdefault("img_prompt", "luxury car on road, photorealistic")
        return {"cover_title": data.get("cover_title","车圈速递"), "news": data["news"][:5]}
    except:
        return None

def fallback_news():
    return {
        "cover_title": "车圈今日大事件",
        "news": [
            {"title":"比亚迪1700万辆新能源车下线","summary":"海豹08成里程碑续航905km","source":"比亚迪","img_prompt":"BYD Seal 08 luxury electric sedan on coastal highway, photorealistic, car magazine style"},
            {"title":"全新坦克300开启预售","summary":"25.98万起轴距加长260mm","source":"长城汽车","img_prompt":"Tank 300 offroad SUV in desert mountain landscape, photorealistic, rugged style"},
            {"title":"奔驰纯电GLC SUV上市","summary":"入门29.99万续航超700km","source":"奔驰","img_prompt":"Mercedes-Benz electric GLC SUV in modern city, photorealistic, luxury style"},
            {"title":"腾势Z登陆古德伍德速度节","summary":"中国超跑全球首秀三电机千匹","source":"腾势","img_prompt":"Denza Z Chinese supercar on racetrack, photorealistic, sports car photography"},
            {"title":"上半年新能源车产销超700万辆","summary":"6月出口首破100万辆增75%","source":"中汽协","img_prompt":"electric vehicle production line with new cars, photorealistic, industrial photography"},
        ]
    }

# ==================== 混元生图 ====================
def generate_image(prompt, save_path):
    """调用TokenHub混元生图极速版"""
    try:
        r = requests.post(TOKENHUB_IMAGE_URL, json={
            "model": "hy-image-lite",
            "prompt": prompt,
            "rsp_img_type": "url",
        }, headers={"Authorization": f"Bearer {TOKENHUB_KEY}", "Content-Type": "application/json"}, timeout=90)
        r.raise_for_status()
        data = r.json()
        img_url = data["data"][0]["url"]
        # 下载图片
        img_r = requests.get(img_url, timeout=30)
        img_r.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(img_r.content)
        print(f"[IMG] {save_path} ({len(img_r.content)}B)")
        return True
    except Exception as e:
        print(f"[ERROR] 生图失败: {e}")
        return False

# ==================== 邮件 ====================
def send_email(subject, image_paths, news_list, cover_title, today_str):
    msg = MIMEMultipart('related')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    
    colors = ["#f7931e", "#00d2ff", "#ff6b6b", "#48dbfb", "#feca57"]
    items = ""
    for i, n in enumerate(news_list):
        items += f"""<tr><td style="padding:6px 0">
<img src="cid:img_{i+1}" style="width:100%;max-width:600px;border-radius:12px;margin-bottom:2px"/>
<table width="100%" style="background:#1a1a2e;border-radius:0 0 12px 12px;border-left:4px solid {colors[i]}">
<tr><td style="padding:12px 18px">
<span style="color:{colors[i]};font-weight:bold">{'①②③④⑤'[i]}</span>
<span style="color:#fff;font-size:15px;margin-left:8px">{html_mod.escape(n['title'])}</span>
<p style="color:#aaa;margin:4px 0 0;font-size:12px">{html_mod.escape(n['summary'])} | {html_mod.escape(n.get('source',''))}</p>
</td></tr></table></td></tr>"""
    
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'PingFang SC',sans-serif;max-width:640px;margin:0 auto;background:#0d0d0d;color:#fff">
<table width="100%">
<tr><td style="background:linear-gradient(135deg,#ff6b35,#f7931e);border-radius:16px;padding:28px 16px;text-align:center">
<h1 style="font-size:28px;margin:0;color:#fff">🔥 {html_mod.escape(cover_title)}</h1>
<p style="margin:8px 0 0;opacity:0.85">{today_str} · 每日汽车热点精选</p>
<p style="color:#444;font-size:11px;margin:4px 0 0">🤖 DeepSeek AI精选 + 混元生图</p>
</td></tr>
<tr><td style="text-align:center;padding:10px 0"><img src="cid:img_0" style="width:100%;max-width:600px;border-radius:16px"/></td></tr>
{items}
<tr><td style="text-align:center;padding:20px;border-top:1px solid #222;color:#444;font-size:12px">
⏰ 每日10:00自动推送 | ☁️ 云端运行，无需电脑开机<br>Powered by WorkBuddy 🚀
</td></tr></table></body></html>"""
    
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(html, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    for i, p in enumerate(image_paths):
        if os.path.exists(p):
            with open(p, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-ID', f'<img_{i}>')
                img.add_header('Content-Disposition', 'inline', filename=f'car_{i+1}.png')
                msg.attach(img)
    
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    server.starttls()
    server.login(SENDER, PASSWORD)
    server.sendmail(SENDER, [RECEIVER], msg.as_string())
    server.quit()
    print(f"[OK] 邮件已发送 ({len(image_paths)}张图)")

# ==================== Main ====================
def main():
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")
    ds = today.strftime("%m/%d")
    
    print(f"{'='*50}")
    print(f"🚗 每日汽车热点 (DeepSeek + TokenHub混元)")
    print(f"📅 {today_str}")
    print(f"{'='*50}")
    
    # 1. 抓取
    print("\n[1/4] 抓取新闻...")
    raw = fetch_raw_news()
    
    # 2. LLM分析
    result = None
    if raw:
        print("\n[2/4] DeepSeek AI 分析...")
        result = analyze_news(raw, today_str)
    if not result:
        result = fallback_news()
        print("[INFO] 使用备用数据")
    
    ct = result["cover_title"]
    news = result["news"]
    print(f"  封面: {ct} | {len(news)}条新闻")
    
    # 3. 生成图片
    print("\n[3/4] 混元生图...")
    paths = []
    
    # 封面图
    cover_path = OUTPUT_DIR / "cover.png"
    cover_prompt = f"Xiaohongshu social media cover design. A photorealistic collage of luxury sports cars and new electric vehicles in neon city night. Overlay bold Chinese title text \"{ct}\" in large white font at center. Below it \"每日汽车热点精选\". Dark background with orange neon glow. Modern Chinese social media card style. Square format."
    generate_image(cover_prompt, str(cover_path))
    paths.append(str(cover_path))
    time.sleep(1)
    
    # 5张内容图
    for i, item in enumerate(news):
        card_path = OUTPUT_DIR / f"card_{i+1}.png"
        prompt = f"Xiaohongshu style car news card. A photorealistic photo of {item['img_prompt']}. Overlay Chinese title \"{item['title']}\" at top in white bold font. Bottom overlay \"{item['summary']}\" in large orange text. Dark cinematic color grading. Modern social media card design. Square format. Real car photography style."
        generate_image(prompt, str(card_path))
        paths.append(str(card_path))
        time.sleep(1)
    
    # 4. 发送
    print("\n[4/4] 发送邮件...")
    subject = f"🚗 每日汽车热点 | {ds} | {ct}"
    send_email(subject, paths, news, ct, today_str)
    
    print(f"\n{'='*50}")
    print(f"📰 {ct}")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']} → {n['summary']}")
    print(f"📸 {len(paths)}张 | ✅ 完成")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
