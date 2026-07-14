#!/usr/bin/env python3
"""
每日汽车热点 - GitHub Actions 云端版 V2
修复: 1) 中文文字用Pillow精确渲染(不依赖AI生图文字)
      2) 优化新闻源,聚焦汽车行业核心资讯
DeepSeek + TokenHub混元生图(背景) + Pillow(中文排版) + QQ邮箱
"""

import os, re, json, html as html_mod, smtplib, datetime, time, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from pathlib import Path
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ==================== 配置 ====================
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SENDER = "740418164@qq.com"
PASSWORD = os.environ["QMAIL_AUTH_CODE"]
RECEIVER = "740418164@qq.com"
DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
TOKENHUB_KEY = os.environ["TOKENHUB_API_KEY"]
TOKENHUB_URL = "https://tokenhub.tencentmaas.com/v1/api/image/lite"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

IMG_W, IMG_H = 1024, 1024

# ==================== 字体 ====================
# 字体路径：优先使用仓库自带Noto Sans SC字体，确保中文在GitHub Actions正确显示
FONT_PATHS = [
    str(Path(__file__).parent.parent / "fonts" / "NotoSansSC-Bold.ttf"),
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

def get_font(size):
    for fp in FONT_PATHS:
        if os.path.exists(fp):
            try: return ImageFont.truetype(fp, size)
            except Exception as e:
                print(f"[WARN] 字体加载失败 {fp}: {e}")
                continue
    print("[ERROR] 没有可用中文字体，文字可能显示为方块")
    return ImageFont.load_default()

# ==================== 新闻抓取(优化源) ====================
def fetch_news():
    """从多个汽车专业媒体抓取"""
    texts = []
    sources = [
        ("汽车之家快讯", "https://www.autohome.com.cn/all/"),
        ("易车网新车", "https://news.yiche.com/"),
        ("IT之家汽车", "https://www.ithome.com/tag/qiche"),
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    for name, url in sources:
        try:
            r = requests.get(url, timeout=15, headers=headers)
            if r.status_code == 200:
                t = re.sub(r'<script[^>]*>.*?</script>', '', r.text, flags=re.DOTALL)
                t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
                t = re.sub(r'<[^>]+>', ' ', t)
                t = re.sub(r'\s+', ' ', t)
                texts.append(f"【{name}】\n{t[:6000]}")
                print(f"[OK] {name}")
        except Exception as e:
            print(f"[WARN] {name}: {e}")
    return "\n\n".join(texts) if texts else ""

# ==================== DeepSeek ====================
def call_deepseek(prompt, system="", temp=0.7):
    try:
        r = requests.post("https://api.deepseek.com/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [{"role":"system","content":system},{"role":"user","content":prompt}],
            "temperature": temp, "max_tokens": 2048,
        }, headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] DeepSeek: {e}")
        return ""

def analyze_news(raw, today):
    system = """你是资深汽车行业编辑。从新闻素材中精选5条最有价值的今日汽车热点。

精选标准：
1. 新车发布/上市/预售(含价格、配置等细节)
2. 热门车型进度(小米SU7、理想L6、问界M9等)
3. 汽车行业新规/政策变化
4. 销量数据/市场动态
5. 技术突破/智能化进展

要求：
- 每条新闻含标题+≤20字概括(必须说清核心信息)
- 封面标题≤10字，要吸引眼球有冲击力
- 内容多元，不全是同一品牌
- 严格JSON输出"""

    prompt = f"""今天是{today}。从以下汽车行业新闻素材中精选5条最有价值热点：

{raw[:6000]}

输出JSON：
```json
{{"cover_title":"≤10字吸引眼球标题","news":[{{"title":"新闻标题","summary":"≤20字核心概括","source":"来源","img_prompt":"英文简短描述,用于AI生成该新闻的背景配图,要具体到车型/场景,photorealistic风格"}}]}}
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

def fallback():
    return {"cover_title":"车圈今日大事件","news":[
        {"title":"比亚迪1700万辆新能源车下线","summary":"海豹08成里程碑续航905km","source":"比亚迪","img_prompt":"BYD Seal 08 luxury electric sedan on coastal highway, photorealistic"},
        {"title":"全新坦克300开启预售","summary":"25.98万起轴距加长260mm","source":"长城汽车","img_prompt":"new Tank 300 offroad SUV in desert mountains, photorealistic"},
        {"title":"奔驰纯电GLC SUV上市","summary":"入门29.99万续航超700km","source":"奔驰","img_prompt":"Mercedes electric GLC SUV in modern city, photorealistic"},
        {"title":"腾势Z登陆古德伍德速度节","summary":"中国超跑全球首秀三电机千匹","source":"腾势","img_prompt":"Denza Z supercar on racetrack, photorealistic"},
        {"title":"上半年新能源车产销超700万辆","summary":"6月出口首破100万辆增75%","source":"中汽协","img_prompt":"EV production line with new cars, photorealistic"},
    ]}

# ==================== 混元生图(生成背景) ====================
def generate_bg_image(prompt):
    """用混元极速版生成照片级背景图"""
    try:
        r = requests.post(TOKENHUB_URL, json={
            "model": "hy-image-lite",
            "prompt": f"{prompt}, photorealistic, high quality, square format",
            "rsp_img_type": "url",
        }, headers={"Authorization": f"Bearer {TOKENHUB_KEY}", "Content-Type": "application/json"}, timeout=90)
        r.raise_for_status()
        img_url = r.json()["data"][0]["url"]
        img_r = requests.get(img_url, timeout=30)
        img_r.raise_for_status()
        return Image.open(BytesIO(img_r.content)).convert("RGB").resize((IMG_W, IMG_H), Image.LANCZOS)
    except Exception as e:
        print(f"[WARN] 生图失败: {e}, 使用纯色背景")
        bg = Image.new('RGB', (IMG_W, IMG_H), '#111122')
        draw = ImageDraw.Draw(bg)
        for y in range(IMG_H):
            r = int(15 + 10 * y / IMG_H)
            g = int(10 + 20 * y / IMG_H)
            b = int(30 + 20 * y / IMG_H)
            draw.line([(0,y),(IMG_W,y)], fill=(r,g,b))
        return bg

# ==================== 图片合成(Pillow精确中文) ====================
def create_cover(bg, title_text, today_str):
    """封面：背景+精确中文排版"""
    draw = ImageDraw.Draw(bg)
    
    # 压暗背景
    overlay = Image.new('RGBA', (IMG_W, IMG_H), (0,0,0,120))
    bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(bg)
    
    # 顶部装饰线
    draw.rectangle([0, 0, IMG_W, 6], fill='#FF6B35')
    
    # 中央半透明卡片
    card_y, card_h = 280, 380
    card_overlay = Image.new('RGBA', (IMG_W, IMG_H), (0,0,0,0))
    cdraw = ImageDraw.Draw(card_overlay)
    cdraw.rounded_rectangle([60, card_y, IMG_W-60, card_y+card_h], radius=24, fill=(15,15,30,200), outline=(255,107,53,160), width=3)
    bg = Image.alpha_composite(bg.convert('RGBA'), card_overlay).convert('RGB')
    draw = ImageDraw.Draw(bg)
    
    # 标题
    font_title = get_font(60)
    bbox = draw.textbbox((0,0), title_text, font=font_title)
    tw = bbox[2]-bbox[0]
    draw.text(((IMG_W-tw)//2, card_y+60), title_text, fill='#FFFFFF', font=font_title)
    
    # 装饰线
    draw.line([(IMG_W//2-60, card_y+170), (IMG_W//2+60, card_y+170)], fill='#FF6B35', width=2)
    
    # 副标题
    font_sub = get_font(32)
    sub = "每日汽车热点精选"
    bbox = draw.textbbox((0,0), sub, font=font_sub)
    sw = bbox[2]-bbox[0]
    draw.text(((IMG_W-sw)//2, card_y+200), sub, fill='#CCCCCC', font=font_sub)
    
    # 日期
    font_date = get_font(26)
    bbox = draw.textbbox((0,0), today_str, font=font_date)
    dw = bbox[2]-bbox[0]
    draw.text(((IMG_W-dw)//2, card_y+260), today_str, fill='#888888', font=font_date)
    
    # 底部标签
    font_tag = get_font(28)
    tags = ["🚗 新车发布", "📊 行业数据", "🔋 新能源", "📋 政策解读", "🌍 全球动态"]
    tag_y = card_y + card_h + 30
    for tag in tags:
        bbox = draw.textbbox((0,0), tag, font=font_tag)
        tw_tag = bbox[2]-bbox[0]
        draw.text(((IMG_W-tw_tag)//2, tag_y), tag, fill='#999999', font=font_tag)
        tag_y += 40
    
    # 底部装饰
    draw.rectangle([0, IMG_H-6, IMG_W, IMG_H], fill='#FF6B35')
    font_wm = get_font(22)
    draw.text((IMG_W-270, IMG_H-40), "WorkBuddy · 每日汽车热点", fill='#555555', font=font_wm)
    
    return bg

def create_card(bg, title, summary, accent_color="#FF6B35"):
    """内容卡片：背景+精确中文标题和概括"""
    draw = ImageDraw.Draw(bg)
    
    # 压暗
    overlay = Image.new('RGBA', (IMG_W, IMG_H), (0,0,0,80))
    bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(bg)
    
    # 顶部色条
    draw.rectangle([0, 0, IMG_W, 6], fill=accent_color)
    
    # 底部渐变遮罩
    for y in range(IMG_H-400, IMG_H):
        alpha = int(180 * (y-(IMG_H-400)) / 400)
        draw.line([(0,y),(IMG_W,y)], fill=(0,0,0,alpha) if hasattr(draw,'rgba') else (0,0,0))
    
    # 实际用叠加层方式
    shade = Image.new('RGBA', (IMG_W, IMG_H), (0,0,0,0))
    sdraw = ImageDraw.Draw(shade)
    for y in range(IMG_H-380, IMG_H):
        a = int(200 * (y-(IMG_H-380)) / 380)
        sdraw.line([(0,y),(IMG_W,y)], fill=(0,0,0,a))
    bg = Image.alpha_composite(bg.convert('RGBA'), shade).convert('RGB')
    draw = ImageDraw.Draw(bg)
    
    # 标题(上方,白色)
    font_title = get_font(44)
    # 自动换行
    max_w = IMG_W - 100
    lines = []
    current = ""
    for ch in title:
        test = current + ch
        bbox = draw.textbbox((0,0), test, font=font_title)
        if bbox[2]-bbox[0] > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    
    title_y = 50
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font_title)
        tw = bbox[2]-bbox[0]
        draw.text(((IMG_W-tw)//2, title_y), line, fill='#FFFFFF', font=font_title)
        # 阴影
        draw.text(((IMG_W-tw)//2+2, title_y+2), line, fill='#000000', font=font_title)
        title_y += 55
    
    # 概括文字(中间大字,彩色背景)
    summary = summary[:20]  # 确保≤20字
    font_summary = get_font(50)
    bbox = draw.textbbox((0,0), summary, font=font_summary)
    sw = bbox[2]-bbox[0]
    sh = bbox[3]-bbox[1]
    
    # 概括文字背景条
    hex_c = accent_color.lstrip('#')
    r, g, b = int(hex_c[0:2],16), int(hex_c[2:4],16), int(hex_c[4:6],16)
    
    tag_bg = Image.new('RGBA', (IMG_W, IMG_H), (0,0,0,0))
    tdraw = ImageDraw.Draw(tag_bg)
    pad_x, pad_y = 24, 16
    tdraw.rounded_rectangle(
        [(IMG_W-sw)//2-pad_x, IMG_H//2+20-pad_y, (IMG_W+sw)//2+pad_x, IMG_H//2+20+sh+pad_y],
        radius=16, fill=(r,g,b,200)
    )
    bg = Image.alpha_composite(bg.convert('RGBA'), tag_bg).convert('RGB')
    draw = ImageDraw.Draw(bg)
    draw.text(((IMG_W-sw)//2, IMG_H//2+20), summary, fill='#FFFFFF', font=font_summary)
    
    # 底部装饰
    draw.rectangle([0, IMG_H-6, IMG_W, IMG_H], fill=accent_color)
    
    return bg

# ==================== 邮件 ====================
def send_email(subject, paths, news, cover_title, today_str):
    msg = MIMEMultipart('related')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    
    colors = ["#f7931e", "#00d2ff", "#ff6b6b", "#48dbfb", "#feca57"]
    items = ""
    for i, n in enumerate(news):
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
</td></tr>
<tr><td style="text-align:center;padding:10px 0"><img src="cid:img_0" style="width:100%;max-width:600px;border-radius:16px"/></td></tr>
{items}
<tr><td style="text-align:center;padding:20px;border-top:1px solid #222;color:#444;font-size:12px">
⏰ 每日10:00自动推送 | ☁️ GitHub Actions云端运行<br>Powered by WorkBuddy 🚀
</td></tr></table></body></html>"""
    
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(html, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    for i, p in enumerate(paths):
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
    print(f"[OK] 邮件已发送 ({len(paths)}张图)")

# ==================== Main ====================
def main():
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")
    ds = today.strftime("%m/%d")
    
    print(f"{'='*50}")
    print(f"🚗 每日汽车热点 V2 (DeepSeek+混元生图+Pillow中文)")
    print(f"📅 {today_str}")
    print(f"{'='*50}")
    
    # 1. 抓取
    print("\n[1/5] 抓取汽车新闻...")
    raw = fetch_news()
    
    # 2. LLM
    result = None
    if raw:
        print("\n[2/5] DeepSeek AI 精选分析...")
        result = analyze_news(raw, today_str)
    if not result:
        result = fallback()
        print("[INFO] 使用备用数据")
    
    ct = result["cover_title"]
    news = result["news"]
    print(f"  封面: {ct} | {len(news)}条")
    
    # 3. 生成背景图+合成中文
    print("\n[3/5] 混元生图+Pillow合成...")
    paths = []
    accent_colors = ["#FF6B35", "#00D2FF", "#FF6B6B", "#48DBFB", "#FECA57"]
    
    # 封面
    cover_bg = generate_bg_image("luxury sports car collage neon city night, photorealistic")
    cover = create_cover(cover_bg, ct, today_str)
    cover_path = OUTPUT_DIR / "cover.png"
    cover.save(str(cover_path), 'PNG', quality=90)
    paths.append(str(cover_path))
    print(f"  [IMG] 封面: {ct}")
    time.sleep(1)
    
    # 5张内容
    for i, item in enumerate(news):
        bg = generate_bg_image(item["img_prompt"])
        card = create_card(bg, item["title"], item["summary"], accent_colors[i])
        card_path = OUTPUT_DIR / f"card_{i+1}.png"
        card.save(str(card_path), 'PNG', quality=90)
        paths.append(str(card_path))
        print(f"  [IMG] 卡片{i+1}: {item['title'][:25]}")
        time.sleep(1)
    
    # 4. 发送
    print("\n[4/5] 构建邮件...")
    subject = f"🚗 每日汽车热点 | {ds} | {ct}"
    
    print("[5/5] 发送邮件...")
    send_email(subject, paths, news, ct, today_str)
    
    print(f"\n{'='*50}")
    print(f"📰 {ct}")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']}")
        print(f"     → {n['summary']}")
    print(f"📸 {len(paths)}张图 | ✅ 完成")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
