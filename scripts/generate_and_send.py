#!/usr/bin/env python3
"""
每日汽车热点 - GitHub Actions 自动执行脚本 (DeepSeek LLM + 图片版)
1. 从多个汽车新闻源实时抓取最新资讯
2. 用 DeepSeek LLM 精选5条 + 生成标题 + 撰写20字概括
3. 用 Pillow 生成小红书风格卡片图片（1封面 + 5内容）
4. 发送含图片的 HTML 邮件到 QQ 邮箱
"""

import os
import re
import io
import json
import html as html_mod
import smtplib
import datetime
import textwrap
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from pathlib import Path

# Pillow
from PIL import Image, ImageDraw, ImageFont

# ========== 配置 ==========
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SENDER = "740418164@qq.com"
PASSWORD = os.environ.get("QMAIL_AUTH_CODE", "")
RECEIVER = "740418164@qq.com"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 图片尺寸 (小红书竖版比例 3:4)
IMG_W, IMG_H = 900, 1200

# 字体路径 (GitHub Actions Ubuntu)
FONT_PATHS = [
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def find_font(size=32):
    """查找可用的中文字体"""
    for fp in FONT_PATHS:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except:
                continue
    # 回退到默认字体
    return ImageFont.load_default()


# ========== 新闻抓取 ==========

def fetch_raw_news():
    raw_texts = []
    sources = [
        {"name": "盖世汽车", "url": "https://auto.gasgoo.com/"},
        {"name": "汽车之家快讯", "url": "https://www.autohome.com.cn/all/"},
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
                print(f"[OK] {src['name']} 抓取成功")
        except Exception as e:
            print(f"[WARN] {src['name']} 失败: {e}")
    return "\n\n".join(raw_texts) if raw_texts else ""


# ========== DeepSeek LLM ==========

def call_deepseek(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    if not DEEPSEEK_API_KEY:
        return ""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(DEEPSEEK_API_URL, json={
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }, headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] DeepSeek: {e}")
        return ""


def analyze_news_with_llm(raw_text: str, today_str: str) -> dict:
    system = """你是资深汽车行业编辑。从新闻素材中精选5条最有价值的今日热点。

要求：
1. 每条新闻生成标题和≤20字概括（说清核心信息）
2. 生成一个≤10字的封面标题，要吸引眼球
3. 优先选：新车发布、行业政策、销量里程碑、技术突破、全球车展
4. 内容多元，不全是同一品牌
5. 严格输出JSON"""

    prompt = f"""今天是{today_str}。精选5条汽车热点：

新闻素材：
{raw_text[:6000]}

严格按JSON输出：
```json
{{"cover_title":"≤10字标题","news":[{{"title":"标题","summary":"≤20字概括","source":"来源"}}]}}
```"""

    result = call_deepseek(prompt, system, temperature=0.8)
    try:
        m = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
        data = json.loads(m.group(1) if m else result)
        news_list = data.get("news", [])[:5]
        for item in news_list:
            item.setdefault("title", "汽车快讯")
            item.setdefault("summary", item["title"][:20])
            item.setdefault("source", "综合资讯")
        print(f"[LLM] 标题: {data.get('cover_title')} | 新闻: {len(news_list)}条")
        return {"cover_title": data.get("cover_title", "车圈今日速递"), "news": news_list}
    except Exception as e:
        print(f"[ERROR] 解析失败: {e}")
        return None


def get_fallback_news():
    return {
        "cover_title": "车圈今日大事件",
        "news": [
            {"title": "比亚迪第1700万辆新能源车下线", "summary": "海豹08成里程碑车型续航905km", "source": "比亚迪"},
            {"title": "全新坦克300开启预售", "summary": "25.98万起轴距加长260mm", "source": "长城汽车"},
            {"title": "奔驰纯电GLC SUV上市", "summary": "入门29.99万续航超700km", "source": "梅赛德斯-奔驰"},
            {"title": "腾势Z登陆古德伍德速度节", "summary": "中国超跑全球首秀三电机千匹", "source": "腾势汽车"},
            {"title": "上半年新能源车产销超700万辆", "summary": "6月出口首破100万辆增75%", "source": "中汽协"},
        ]
    }


# ========== 图片生成 (Pillow) ==========

def create_gradient_bg(draw, w, h, c1, c2):
    """绘制渐变背景"""
    for y in range(h):
        r = int(c1[0] + (c2[0] - c1[0]) * y / h)
        g = int(c1[1] + (c2[1] - c1[1]) * y / h)
        b = int(c1[2] + (c2[2] - c1[2]) * y / h)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def draw_centered_text(draw, text, y, font, fill, w, max_width=None):
    """居中绘制文字，支持自动换行"""
    if max_width is None:
        max_width = w - 60
    
    # 尝试单行
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    
    if tw <= max_width:
        x = (w - tw) // 2
        draw.text((x, y), text, fill=fill, font=font)
        return y + (bbox[3] - bbox[1]) + 10
    else:
        # 自动换行
        lines = []
        chars_per_line = len(text)
        while chars_per_line > 0:
            test = text[:chars_per_line]
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                lines.append(test)
                text = text[chars_per_line:]
                chars_per_line = len(text)
            else:
                chars_per_line -= 1
                if chars_per_line == 0:
                    lines.append(text[:5])
                    text = text[5:]
                    chars_per_line = len(text)
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            draw.text((x, y), line, fill=fill, font=font)
            y += (bbox[3] - bbox[1]) + 8
        return y


def generate_cover_image(cover_title, today_str, save_path):
    """生成小红书风格封面图"""
    img = Image.new('RGB', (IMG_W, IMG_H), '#0d0d0d')
    draw = ImageDraw.Draw(img)
    
    # 渐变背景 (深紫→深蓝)
    create_gradient_bg(draw, IMG_W, IMG_H, (25, 10, 40), (10, 15, 40))
    
    # 装饰圆
    for cx, cy, r, alpha in [(150, 200, 180, 20), (750, 900, 250, 15), (450, 600, 300, 10)]:
        overlay = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 150, 50, alpha))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
    
    # 顶部装饰线
    draw.rectangle([0, 0, IMG_W, 6], fill='#f7931e')
    
    # 汽车emoji装饰
    font_emoji = find_font(80)
    draw_centered_text(draw, "🚗", 100, font_emoji, (255, 255, 255, 180), IMG_W)
    
    # 主标题区域 - 渐变卡片
    card_y, card_h = 280, 300
    for y in range(card_y, card_y + card_h):
        ratio = (y - card_y) / card_h
        r = int(255 * (1 - ratio) + 255 * ratio)
        g = int(107 * (1 - ratio) + 147 * ratio)
        b = int(53 * (1 - ratio) + 30 * ratio)
        draw.line([(40, y), (IMG_W - 40, y)], fill=(r, g, b))
    
    # 圆角矩形效果
    draw.rounded_rectangle([40, card_y, IMG_W - 40, card_y + card_h], radius=24, 
                           fill='#1a1a2e', outline='#f7931e', width=2)
    
    # 封面标题
    font_title = find_font(64)
    draw_centered_text(draw, cover_title, card_y + 50, font_title, '#f7931e', IMG_W)
    
    # 副标题
    font_sub = find_font(32)
    draw_centered_text(draw, "每日汽车热点精选", card_y + 160, font_sub, '#ffffff', IMG_W)
    
    # 日期
    font_date = find_font(28)
    draw_centered_text(draw, today_str, card_y + 220, font_date, '#888888', IMG_W)
    
    # 底部5条导航预览
    font_preview = find_font(26)
    preview_y = 640
    previews = ["🔹 新车发布速递", "🔹 行业政策解读", "🔹 销量数据一览", 
                 "🔹 技术前沿突破", "🔹 全球车圈动态"]
    for p in previews:
        draw_centered_text(draw, p, preview_y, font_preview, '#cccccc', IMG_W)
        preview_y += 50
    
    # 底部装饰
    draw.rectangle([0, IMG_H - 6, IMG_W, IMG_H], fill='#f7931e')
    font_footer = find_font(22)
    draw_centered_text(draw, "Powered by WorkBuddy 🚀", IMG_H - 80, font_footer, '#555555', IMG_W)
    
    img.save(save_path, 'PNG', quality=90)
    print(f"[IMG] 封面已生成: {save_path}")
    return save_path


def generate_news_card(news_item, index, save_path):
    """生成单条新闻卡片图"""
    colors = [
        ('#f7931e', '#ff6b35'),   # 橙色
        ('#00d2ff', '#0099cc'),   # 青色
        ('#ff6b6b', '#cc4444'),   # 红色
        ('#48dbfb', '#3399cc'),   # 蓝色
        ('#feca57', '#f0a500'),   # 黄色
    ]
    color_accent, color_grad = colors[index % 5]
    emojis = ["🔴", "🟠", "🟡", "🟢", "🔵"]
    
    img = Image.new('RGB', (IMG_W, IMG_H), '#0d0d0d')
    draw = ImageDraw.Draw(img)
    
    # 深色渐变背景
    create_gradient_bg(draw, IMG_W, IMG_H, (13, 13, 22), (18, 18, 30))
    
    # 顶部色条
    draw.rectangle([0, 0, IMG_W, 6], fill=color_accent)
    
    # 序号圆形
    cx, cy = IMG_W // 2, 160
    r = 50
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color_accent)
    font_num = find_font(48)
    bbox = draw.textbbox((0, 0), str(index + 1), font=font_num)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), str(index + 1), fill='#ffffff', font=font_num)
    
    # 分隔线
    draw.line([(120, 260), (IMG_W - 120, 260)], fill=color_accent, width=2)
    
    # 主标题
    font_title = find_font(44)
    title = news_item['title']
    y = draw_centered_text(draw, title, 320, font_title, '#ffffff', IMG_W, max_width=IMG_W - 100)
    
    # 概括文字 (≤20字)
    font_summary = find_font(56)
    summary = news_item['summary']
    # 确保 ≤20字
    if len(summary) > 20:
        summary = summary[:20]
    y = draw_centered_text(draw, summary, 480, font_summary, color_accent, IMG_W, max_width=IMG_W - 80)
    
    # 引用框
    quote_y = 650
    quote_text = f"「{summary}」" if len(summary) <= 16 else summary
    font_quote = find_font(36)
    draw_centered_text(draw, quote_text, quote_y, font_quote, '#aaaaaa', IMG_W, max_width=IMG_W - 120)
    
    # 来源
    font_src = find_font(26)
    source = news_item.get('source', '')
    draw_centered_text(draw, f"📎 {source}", 780, font_src, '#666666', IMG_W)
    
    # 底部装饰
    draw.rectangle([0, IMG_H - 6, IMG_W, IMG_H], fill=color_accent)
    
    # 装饰点
    for dx in range(100, IMG_W, 100):
        draw.ellipse([dx, IMG_H - 50, dx + 8, IMG_H - 42], fill=(255, 255, 255, 30))
    
    img.save(save_path, 'PNG', quality=90)
    print(f"[IMG] 卡片{index+1}已生成: {save_path}")
    return save_path


def generate_all_images(news_list, cover_title, today_str):
    """生成所有图片，返回路径列表"""
    paths = []
    
    # 封面图
    cover_path = OUTPUT_DIR / "cover.png"
    generate_cover_image(cover_title, today_str, str(cover_path))
    paths.append(str(cover_path))
    
    # 5张内容图
    for i, news in enumerate(news_list):
        card_path = OUTPUT_DIR / f"card_{i+1}.png"
        generate_news_card(news, i, str(card_path))
        paths.append(str(card_path))
    
    return paths


# ========== HTML 邮件 ==========

def build_html(news_list, cover_title, today_str, source_info="", image_cids=None):
    """构建含图片的HTML邮件"""
    items_html = ""
    emojis = ["①", "②", "③", "④", "⑤"]
    colors = ["#f7931e", "#00d2ff", "#ff6b6b", "#48dbfb", "#feca57"]
    
    for i, news in enumerate(news_list):
        img_tag = ""
        if image_cids and i + 1 < len(image_cids):
            img_tag = f'<img src="cid:{image_cids[i+1]}" style="width:100%; max-width:560px; border-radius:12px; margin:8px 0;" />'
        
        items_html += f"""
<tr>
  <td style="padding: 8px 0;">
    {img_tag}
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a2e; border-radius:12px; border-left:4px solid {colors[i]};">
      <tr>
        <td style="padding: 20px;">
          <span style="color:{colors[i]}; font-size:13px; font-weight:bold;">{emojis[i]}</span>
          <h3 style="color:#fff; margin:6px 0; font-size:17px;">{html_mod.escape(news['title'])}</h3>
          <p style="color:#aaa; margin:4px 0 0; font-size:14px; line-height:1.5;">{html_mod.escape(news['summary'])}</p>
          <p style="color:#555; margin:6px 0 0; font-size:11px;">📎 {html_mod.escape(news.get('source', ''))}</p>
        </td>
      </tr>
    </table>
  </td>
</tr>"""

    source_note = f'<p style="color:#444; font-size:11px; margin:4px 0 0;">{source_info}</p>' if source_info else ""
    
    cover_img_tag = ""
    if image_cids and len(image_cids) > 0:
        cover_img_tag = f'<img src="cid:{image_cids[0]}" style="width:100%; max-width:560px; border-radius:16px; margin:0 auto 16px; display:block;" />'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif; max-width:620px; margin:0 auto; padding:0; background:#0d0d0d; color:#fff;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;">
  <tr>
    <td style="background:linear-gradient(135deg,#ff6b35,#f7931e); border-radius:16px; padding:35px 25px; text-align:center;">
      <h1 style="font-size:30px; margin:0; color:#fff; letter-spacing:2px;">🔥 {html_mod.escape(cover_title)}</h1>
      <p style="margin:12px 0 0; opacity:0.85; color:#fff; font-size:14px;">{today_str} · 每日汽车热点精选</p>
      {source_note}
    </td>
  </tr>
  <tr><td style="height:16px;"></td></tr>
  <tr><td style="text-align:center;">{cover_img_tag}</td></tr>
  <tr><td style="height:8px;"></td></tr>
  {items_html}
  <tr><td style="height:24px;"></td></tr>
  <tr>
    <td style="text-align:center; padding:20px 0; border-top:1px solid #222;">
      <p style="color:#444; font-size:12px; margin:0;">
        ⏰ 每日上午10:00 自动推送 &nbsp;|&nbsp; 🤖 DeepSeek AI 分析生成<br>
        Powered by <span style="color:#f7931e;">WorkBuddy</span> 🚀
      </p>
    </td>
  </tr>
</table>
</body>
</html>"""


# ========== 邮件发送（含图片附件） ==========

def send_email_with_images(subject, html_body, image_paths):
    """发送含嵌入图片的HTML邮件"""
    if not PASSWORD:
        print("[ERROR] 未设置 QMAIL_AUTH_CODE!")
        return False
    
    msg = MIMEMultipart('related')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    
    # HTML 正文
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    # 嵌入图片
    cids = []
    for i, img_path in enumerate(image_paths):
        if os.path.exists(img_path):
            cid = f"img_{i}"
            cids.append(cid)
            with open(img_path, 'rb') as f:
                mime_img = MIMEImage(f.read())
                mime_img.add_header('Content-ID', f'<{cid}>')
                mime_img.add_header('Content-Disposition', 'inline', 
                                    filename=os.path.basename(img_path))
                msg.attach(mime_img)
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        server.starttls()
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, [RECEIVER], msg.as_string())
        server.quit()
        print(f"[OK] 邮件发送成功 → {RECEIVER} (含{len(cids)}张图片)")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}")
        return False


# ========== Main ==========

def main():
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")
    date_short = today.strftime("%m/%d")
    
    print(f"{'='*50}")
    print(f"🚗 每日汽车热点生成器 (DeepSeek + Pillow)")
    print(f"📅 {today_str}")
    print(f"{'='*50}")
    
    # 1. 抓取新闻
    print("\n[1/5] 抓取实时新闻...")
    raw_text = fetch_raw_news()
    
    # 2. LLM 分析
    result = None
    source_info = ""
    if raw_text and DEEPSEEK_API_KEY:
        print("\n[2/5] DeepSeek AI 分析中...")
        result = analyze_news_with_llm(raw_text, today_str)
        if result:
            source_info = "🤖 实时抓取 + AI 精选分析"
    
    if not result:
        print("\n[2/5] 使用备用精选数据...")
        result = get_fallback_news()
        source_info = "📋 今日精选数据"
    
    cover_title = result["cover_title"]
    news = result["news"]
    
    # 3. 生成图片
    print("\n[3/5] 生成小红书风格图片...")
    image_paths = generate_all_images(news, cover_title, today_str)
    
    # 4. 构建邮件
    print("\n[4/5] 构建邮件...")
    subject = f"🚗 每日汽车热点 | {date_short} | {cover_title}"
    cids = [f"img_{i}" for i in range(len(image_paths))]
    html_content = build_html(news, cover_title, today_str, source_info, cids)
    
    # 保存
    report_path = OUTPUT_DIR / f"car_news_{today.strftime('%Y%m%d')}.html"
    report_path.write_text(html_content, encoding='utf-8')
    data_path = OUTPUT_DIR / f"news_{today.strftime('%Y%m%d')}.json"
    data_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 5. 发送
    print("\n[5/5] 发送邮件（含图片）...")
    success = send_email_with_images(subject, html_content, image_paths)
    
    print(f"\n{'='*50}")
    print(f"📰 封面标题: {cover_title}")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']}")
        print(f"     → {n['summary']}")
    print(f"📸 图片: {len(image_paths)} 张")
    print(f"{'='*50}")
    print(f"{'✅ 完成!' if success else '⚠️ 邮件发送失败'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
