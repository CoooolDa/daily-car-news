#!/usr/bin/env python3
"""
每日汽车热点 - GitHub Actions (DeepSeek + Unsplash + Pillow)
1. 从多个汽车新闻源实时抓取
2. DeepSeek AI 精选5条 + 标题 + 概括
3. 从 Unsplash 搜索真实汽车照片
4. Pillow 合成小红书风格卡片（真实照片+文字排版）
5. 发送含6张图片的HTML邮件
"""

import os, re, io, json, html as html_mod, smtplib, datetime, textwrap, time, random, requests
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
PASSWORD = os.environ.get("QMAIL_AUTH_CODE", "")
RECEIVER = "740418164@qq.com"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 图片尺寸 (小红书竖版 3:4)
IMG_W, IMG_H = 1080, 1440

# ==================== 字体 ====================
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def get_font(size, bold=False):
    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except:
                continue
    return ImageFont.load_default()

# ==================== 新闻抓取 ====================
def fetch_raw_news():
    raw_texts = []
    sources = [
        {"name": "盖世汽车资讯", "url": "https://auto.gasgoo.com/"},
        {"name": "汽车之家", "url": "https://www.autohome.com.cn/all/"},
        {"name": "IT之家汽车", "url": "https://www.ithome.com/tag/qiche"},
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    for src in sources:
        try:
            resp = requests.get(src["url"], timeout=15, headers=headers)
            if resp.status_code == 200:
                text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text)
                raw_texts.append(f"【来源：{src['name']}】\n{text[:5000]}")
                print(f"[OK] {src['name']}")
        except Exception as e:
            print(f"[WARN] {src['name']}: {e}")
    return "\n\n".join(raw_texts) if raw_texts else ""

# ==================== DeepSeek ====================
def call_deepseek(prompt, system="", temperature=0.7):
    if not DEEPSEEK_API_KEY:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(DEEPSEEK_API_URL, json={
            "model": "deepseek-chat", "messages": messages,
            "temperature": temperature, "max_tokens": 2048,
        }, headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] DeepSeek: {e}")
        return ""

def analyze_news(raw_text, today_str):
    system = """你是资深汽车行业编辑。从新闻素材中精选5条最有价值热点。
要求：
1. 每条生成标题 + ≤20字概括（说清核心信息）
2. 生成≤10字封面标题，要吸引眼球、有冲击力
3. 为每条新闻提供2-3个英文搜索关键词（用于搜索汽车图片）
4. 优先选：新车发布、行业政策、销量里程碑、技术突破
5. 内容多元，不全是同一品牌
6. 严格输出JSON"""

    prompt = f"""今天是{today_str}。精选5条汽车热点：

{raw_text[:6000]}

严格JSON输出：
```json
{{"cover_title":"≤10字吸引眼球标题","news":[{{"title":"标题","summary":"≤20字概括","source":"来源","keywords":["英文关键词1","英文关键词2"]}}]}}
```"""
    
    result = call_deepseek(prompt, system, 0.8)
    try:
        m = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
        data = json.loads(m.group(1) if m else result)
        for item in data.get("news", [])[:5]:
            item.setdefault("title", "快讯")
            item.setdefault("summary", item["title"][:20])
            item.setdefault("source", "综合")
            item.setdefault("keywords", ["car", "automotive"])
        print(f"[LLM] 标题:{data.get('cover_title')} | {len(data['news'])}条")
        return {"cover_title": data.get("cover_title", "车圈今日速递"), "news": data["news"][:5]}
    except Exception as e:
        print(f"[ERROR] 解析: {e}")
        return None

def get_fallback():
    return {
        "cover_title": "车圈今日大事件",
        "news": [
            {"title": "比亚迪第1700万辆新能源车下线", "summary": "海豹08成里程碑车型续航905km", "source": "比亚迪", "keywords": ["BYD seal car", "BYD electric car"]},
            {"title": "全新坦克300开启预售", "summary": "25.98万起轴距加长260mm", "source": "长城汽车", "keywords": ["Tank 300 SUV", "GWM Tank offroad"]},
            {"title": "奔驰纯电GLC SUV上市", "summary": "入门29.99万续航超700km", "source": "梅赛德斯-奔驰", "keywords": ["Mercedes GLC electric", "Mercedes EQE SUV"]},
            {"title": "腾势Z登陆古德伍德速度节", "summary": "中国超跑全球首秀三电机千匹", "source": "腾势汽车", "keywords": ["Denza Z supercar", "Chinese sports car"]},
            {"title": "上半年新能源车产销超700万辆", "summary": "6月出口首破100万辆增75%", "source": "中汽协", "keywords": ["China EV factory", "electric car production"]},
        ]
    }

# ==================== Unsplash 图片搜索 ====================
def search_car_image(keywords):
    """从 Unsplash 搜索汽车照片"""
    if not UNSPLASH_ACCESS_KEY:
        return None
    
    query = " ".join(keywords[:2]) + " car automotive"
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 5, "orientation": "squarish"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            # 选最高质量的图
            url = results[0]["urls"]["regular"]
            img_resp = requests.get(url, timeout=15)
            if img_resp.status_code == 200:
                return Image.open(BytesIO(img_resp.content)).convert("RGB")
    except Exception as e:
        print(f"[WARN] Unsplash搜索失败 ({query}): {e}")
    return None

def get_placeholder_car_image(keywords):
    """获取占位汽车图片 - 使用纯色渐变背景 + 装饰元素"""
    img = Image.new('RGB', (IMG_W, IMG_H), '#111122')
    draw = ImageDraw.Draw(img)
    
    # 动态渐变
    colors = [
        ((25, 15, 45), (15, 20, 50)),  # 紫色
        ((20, 25, 40), (10, 15, 35)),  # 蓝色
        ((30, 15, 20), (15, 10, 25)),  # 红色
        ((20, 30, 25), (10, 20, 20)),  # 绿色
        ((35, 25, 10), (20, 15, 10)),  # 橙色
    ]
    c1, c2 = colors[hash("".join(keywords)) % len(colors)]
    
    for y in range(IMG_H):
        r = int(c1[0] + (c2[0] - c1[0]) * y / IMG_H)
        g = int(c1[1] + (c2[1] - c1[1]) * y / IMG_H)
        b = int(c1[2] + (c2[2] - c1[2]) * y / IMG_H)
        draw.line([(0, y), (IMG_W, y)], fill=(r, g, b))
    
    # 装饰性光晕
    for cx, cy, r, alpha in [(300, 400, 200, 15), (800, 1000, 300, 10), (500, 700, 250, 8)]:
        overlay = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 150, 50, alpha))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
    
    # 汽车emoji作为装饰
    font_emoji = get_font(120)
    emojis = ["🚗", "🏎️", "🚙", "🏍️", "🚐"]
    emoji = emojis[hash("".join(keywords)) % len(emojis)]
    bbox = draw.textbbox((0, 0), emoji, font=font_emoji)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text((IMG_W//2 - tw//2, IMG_H//2 - th//2 - 100), emoji, fill=(255,255,255,40), font=font_emoji)
    
    return img

# ==================== 图片生成 ====================
def create_xiaohongshu_style_image(bg_image, title_text, subtitle_text, accent_color="#FF6B35", is_cover=False):
    """在真实照片上叠加小红书风格文字排版"""
    # 调整背景图尺寸
    bg = bg_image.resize((IMG_W, IMG_H), Image.LANCZOS)
    
    # 稍微压暗背景
    enhancer = ImageEnhance.Brightness(bg)
    bg = enhancer.enhance(0.5)
    
    draw = ImageDraw.Draw(bg)
    
    if is_cover:
        # ===== 封面布局 =====
        # 顶部渐变条
        for y in range(8):
            alpha = 1 - y/8
            r = int(255 * alpha)
            g = int(107 * alpha)
            b = int(53 * alpha)
            draw.line([(0, y), (IMG_W, y)], fill=(r, g, b))
        
        # 中央半透明卡片
        card_w, card_h = IMG_W - 120, 360
        card_x, card_y = 60, (IMG_H - card_h) // 2 - 40
        
        # 毛玻璃效果卡片
        overlay = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rounded_rectangle([card_x, card_y, card_x+card_w, card_y+card_h], 
                                radius=30, fill=(20, 20, 40, 200), outline=(255, 107, 53, 180), width=3)
        bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(bg)
        
        # 主标题
        font_title = get_font(72, bold=True)
        text_bbox = draw.textbbox((0,0), title_text, font=font_title)
        tw = text_bbox[2] - text_bbox[0]
        draw.text(((IMG_W-tw)//2, card_y + 60), title_text, fill='#FFFFFF', font=font_title)
        
        # 装饰线
        draw.line([(IMG_W//2-80, card_y+170), (IMG_W//2+80, card_y+170)], fill='#FF6B35', width=3)
        
        # 副标题
        font_sub = get_font(38)
        sub_bbox = draw.textbbox((0,0), subtitle_text, font=font_sub)
        sw = sub_bbox[2] - sub_bbox[0]
        draw.text(((IMG_W-sw)//2, card_y + 200), subtitle_text, fill='#CCCCCC', font=font_sub)
        
        # 底部标签
        font_tag = get_font(30)
        tags = ["🚗 新车发布", "📊 行业数据", "🔋 新能源", "🏭 政策解读", "🌍 全球动态"]
        tag_y = card_y + card_h + 30
        for tag in tags:
            tag_bbox = draw.textbbox((0,0), tag, font=font_tag)
            tw_tag = tag_bbox[2] - tag_bbox[0]
            draw.text(((IMG_W-tw_tag)//2, tag_y), tag, fill='#999999', font=font_tag)
            tag_y += 42
        
        # 底部装饰
        for y in range(IMG_H-8, IMG_H):
            alpha = (y - (IMG_H-8)) / 8
            r = int(255 * alpha)
            g = int(107 * alpha)
            b = int(53 * alpha)
            draw.line([(0, y), (IMG_W, y)], fill=(r, g, b))
        
        font_watermark = get_font(24)
        draw.text((IMG_W-280, IMG_H-50), "WorkBuddy · 每日汽车热点", fill='#555555', font=font_watermark)
    
    else:
        # ===== 内容卡片布局 =====
        # 顶部色条
        draw.rectangle([0, 0, IMG_W, 8], fill=accent_color)
        
        # 底部渐变文字背景
        overlay = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        # 底部渐变黑色遮罩
        for y in range(IMG_H-500, IMG_H):
            alpha = int(200 * (y - (IMG_H-500)) / 500)
            odraw.line([(0, y), (IMG_W, y)], fill=(0, 0, 0, alpha))
        bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(bg)
        
        # 主标题（上方区域）
        font_title = get_font(52, bold=True)
        lines = textwrap.wrap(title_text, width=14)
        title_y = 60
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font_title)
            tw = bbox[2] - bbox[0]
            draw.text(((IMG_W-tw)//2, title_y), line, fill='#FFFFFF', font=font_title)
            # 文字阴影
            draw.text(((IMG_W-tw)//2+2, title_y+2), line, fill='#000000', font=font_title)
            title_y += 65
        
        # 分隔线
        sep_y = title_y + 20
        draw.line([(IMG_W//2-60, sep_y), (IMG_W//2+60, sep_y)], fill=accent_color, width=3)
        
        # 核心概括（大字突出显示）
        font_summary = get_font(58, bold=True)
        summary_text = subtitle_text[:20]
        bbox = draw.textbbox((0,0), summary_text, font=font_summary)
        sw = bbox[2] - bbox[0]
        # 文字底色
        pad = 20
        overlay2 = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw2 = ImageDraw.Draw(overlay2)
        hex_color = accent_color.lstrip('#')
        r, g, b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
        odraw2.rounded_rectangle(
            [(IMG_W-sw)//2-pad, sep_y+40, (IMG_W+sw)//2+pad, sep_y+40+80],
            radius=15, fill=(r, g, b, 200)
        )
        bg = Image.alpha_composite(bg.convert('RGBA'), overlay2).convert('RGB')
        draw = ImageDraw.Draw(bg)
        draw.text(((IMG_W-sw)//2, sep_y+45), summary_text, fill='#FFFFFF', font=font_summary)
        
        # 底部装饰线
        draw.rectangle([0, IMG_H-8, IMG_W, IMG_H], fill=accent_color)

    return bg


# ==================== 邮件 ====================
def send_email_with_images(subject, html_body, image_paths):
    if not PASSWORD:
        print("[ERROR] 未设置 QMAIL_AUTH_CODE!")
        return False
    
    msg = MIMEMultipart('related')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    for i, img_path in enumerate(image_paths):
        if os.path.exists(img_path):
            with open(img_path, 'rb') as f:
                mime_img = MIMEImage(f.read())
                mime_img.add_header('Content-ID', f'<img_{i}>')
                mime_img.add_header('Content-Disposition', 'inline', filename=os.path.basename(img_path))
                msg.attach(mime_img)
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        server.starttls()
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, [RECEIVER], msg.as_string())
        server.quit()
        print(f"[OK] 邮件发送成功 → {RECEIVER} ({len(image_paths)}图)")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件: {e}")
        return False

def build_html(news_list, cover_title, today_str, source_info):
    items = ""
    colors = ["#f7931e", "#00d2ff", "#ff6b6b", "#48dbfb", "#feca57"]
    for i, news in enumerate(news_list):
        items += f"""
<tr><td style="padding:8px 0">
<img src="cid:img_{i+1}" style="width:100%;max-width:600px;border-radius:12px;margin-bottom:4px" />
<table width="100%" style="background:#1a1a2e;border-radius:0 0 12px 12px;border-left:4px solid {colors[i]}"><tr><td style="padding:14px 20px">
<span style="color:{colors[i]};font-weight:bold">{['①','②','③','④','⑤'][i]}</span>
<span style="color:#fff;font-size:16px;margin-left:8px">{html_mod.escape(news['title'])}</span>
<p style="color:#aaa;margin:4px 0 0;font-size:13px">{html_mod.escape(news['summary'])} | {html_mod.escape(news.get('source',''))}</p>
</td></tr></table></td></tr>"""
    
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'PingFang SC',sans-serif;max-width:640px;margin:0 auto;background:#0d0d0d;color:#fff;padding:0">
<table width="100%" style="background:#0d0d0d">
<tr><td style="background:linear-gradient(135deg,#ff6b35,#f7931e);border-radius:16px;padding:30px 20px;text-align:center">
<h1 style="font-size:28px;margin:0;color:#fff">🔥 {html_mod.escape(cover_title)}</h1>
<p style="margin:10px 0 0;opacity:0.85">{today_str} · 每日汽车热点</p>
<p style="color:#444;font-size:11px;margin:4px 0 0">{source_info}</p>
</td></tr>
<tr><td style="text-align:center;padding:12px 0"><img src="cid:img_0" style="width:100%;max-width:600px;border-radius:16px" /></td></tr>
{items}
<tr><td style="text-align:center;padding:20px;border-top:1px solid #222;color:#444;font-size:12px">
⏰ 每日10:00自动推送 | 🤖 DeepSeek AI | Powered by WorkBuddy 🚀
</td></tr></table></body></html>"""


# ==================== Main ====================
def main():
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")
    date_short = today.strftime("%m/%d")
    
    print(f"{'='*50}")
    print(f"🚗 每日汽车热点 (DeepSeek + Unsplash + Pillow)")
    print(f"📅 {today_str}")
    print(f"{'='*50}")
    
    # 1. 抓取
    print("\n[1/6] 抓取新闻...")
    raw_text = fetch_raw_news()
    
    # 2. LLM
    result = None
    source_info = ""
    if raw_text and DEEPSEEK_API_KEY:
        print("\n[2/6] DeepSeek AI 分析...")
        result = analyze_news(raw_text, today_str)
        if result:
            source_info = "🤖 实时抓取 + AI精选"
    
    if not result:
        print("\n[2/6] 备用数据...")
        result = get_fallback()
        source_info = "📋 精选数据"
    
    cover_title = result["cover_title"]
    news = result["news"]
    
    # 3. 获取图片
    print("\n[3/6] 获取汽车照片...")
    images = []
    # 封面图 - 用通用跑车图片
    cover_bg = search_car_image(["luxury", "sports", "car", "night"]) or get_placeholder_car_image(["supercar"])
    images.append(cover_bg)
    
    # 5条新闻图
    accent_colors = ["#FF6B35", "#00D2FF", "#FF6B6B", "#48DBFB", "#FECA57"]
    for i, item in enumerate(news):
        kw = item.get("keywords", ["car", "automotive"])
        car_img = search_car_image(kw) or get_placeholder_car_image(kw)
        images.append(car_img)
        time.sleep(0.5)  # API 限速
    
    # 4. 生成卡片
    print("\n[4/6] 生成小红书风格卡片...")
    paths = []
    
    # 封面
    cover_img = create_xiaohongshu_style_image(images[0], cover_title, "每日汽车热点精选", is_cover=True)
    cover_path = OUTPUT_DIR / "cover.png"
    cover_img.save(str(cover_path), 'PNG', quality=90)
    paths.append(str(cover_path))
    print(f"[IMG] 封面: {cover_title}")
    
    # 5张内容图
    for i, (item, bg_img) in enumerate(zip(news, images[1:])):
        card = create_xiaohongshu_style_image(
            bg_img, item["title"], item["summary"], 
            accent_color=accent_colors[i], is_cover=False
        )
        card_path = OUTPUT_DIR / f"card_{i+1}.png"
        card.save(str(card_path), 'PNG', quality=90)
        paths.append(str(card_path))
        print(f"[IMG] 卡片{i+1}: {item['title'][:20]}")
    
    # 5. 构建邮件
    print("\n[5/6] 构建邮件...")
    subject = f"🚗 每日汽车热点 | {date_short} | {cover_title}"
    html_content = build_html(news, cover_title, today_str, source_info)
    
    # 保存
    (OUTPUT_DIR / f"news_{today.strftime('%Y%m%d')}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 6. 发送
    print("\n[6/6] 发送邮件...")
    success = send_email_with_images(subject, html_content, paths)
    
    print(f"\n{'='*50}")
    print(f"📰 {cover_title}")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']} → {n['summary']}")
    print(f"📸 {len(paths)}张图片 | {'✅' if success else '❌'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
