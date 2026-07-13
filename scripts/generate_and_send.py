#!/usr/bin/env python3
"""
每日汽车热点 - GitHub Actions 自动执行脚本 (DeepSeek LLM 版)
1. 从多个汽车新闻源实时抓取最新资讯
2. 用 DeepSeek LLM 精选5条 + 生成标题 + 撰写20字概括
3. 生成精美 HTML 邮件发送到 QQ 邮箱
"""

import os
import re
import json
import html as html_mod
import smtplib
import datetime
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path

# ========== 配置 ==========
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SENDER = "740418164@qq.com"
PASSWORD = os.environ.get("QMAIL_AUTH_CODE", "")
RECEIVER = "740418164@qq.com"

# DeepSeek API
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ========== 新闻抓取 ==========

def fetch_raw_news():
    """
    从多个汽车新闻源抓取原始内容
    """
    raw_texts = []
    
    sources = [
        {
            "name": "盖世汽车",
            "url": "https://auto.gasgoo.com/",
            "pattern": r'<a[^>]*href="([^"]*)"[^>]*title="([^"]*)"[^>]*>',
        },
        {
            "name": "汽车之家快讯",
            "url": "https://www.autohome.com.cn/all/",
            "pattern": None,
        },
        {
            "name": "IT之家汽车",
            "url": "https://www.ithome.com/tag/qiche",
            "pattern": None,
        },
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    for src in sources:
        try:
            resp = requests.get(src["url"], timeout=15, headers=headers)
            if resp.status_code == 200:
                # 简单提取文本（去除 HTML 标签）
                text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text)
                # 只取前 5000 字符
                snippet = text[:5000]
                raw_texts.append(f"【来源：{src['name']}】\n{snippet}")
                print(f"[OK] {src['name']} 抓取成功, 内容长度: {len(text)}")
            else:
                print(f"[WARN] {src['name']} 返回 {resp.status_code}")
        except Exception as e:
            print(f"[WARN] {src['name']} 抓取失败: {e}")
    
    return "\n\n".join(raw_texts) if raw_texts else ""


# ========== DeepSeek LLM 调用 ==========

def call_deepseek(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    """调用 DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        print("[ERROR] 未设置 DEEPSEEK_API_KEY!")
        return ""
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 2048,
            },
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] DeepSeek 调用失败: {e}")
        return ""


def analyze_news_with_llm(raw_text: str, today_str: str) -> dict:
    """
    用 DeepSeek 分析新闻内容：
    1. 精选5条最有价值的汽车新闻
    2. 为每条生成 ≤20字 的概括
    3. 生成一个 ≤10字 的封面标题
    """
    
    system = """你是一位资深汽车行业编辑，精通全球汽车资讯。你的任务是从新闻素材中精选最有价值的5条热点新闻。

要求：
1. 每条新闻生成一个清晰标题和不超过20字的概括（说清核心信息）
2. 生成一个≤10字的封面标题，要吸引眼球、有冲击力
3. 优先选择：新车发布、重大行业政策、销量里程碑、技术突破、全球车展动态
4. 内容覆盖尽量多元（不要5条都是同一个品牌）
5. 严格按 JSON 格式输出"""

    prompt = f"""今天是 {today_str}。请从以下汽车行业新闻素材中，精选5条今日最有价值的热点。

新闻素材：
{raw_text[:6000]}

请严格按以下 JSON 格式输出（不要输出其他内容）：
```json
{{
  "cover_title": "≤10字的吸引眼球标题",
  "news": [
    {{
      "title": "新闻标题",
      "summary": "≤20字的核心概括",
      "source": "新闻来源"
    }}
  ]
}}
```

注意：
- cover_title 必须 ≤10个汉字，要有冲击力，让人想点进来看
- summary 必须 ≤20个汉字，说清核心信息
- 每条 news 的 source 尽量标注来源
- 必须是今天的新闻，如果新闻素材不新鲜，从中挑最有价值的即可"""

    result = call_deepseek(prompt, system, temperature=0.8)
    
    # 解析 JSON
    try:
        # 提取 JSON 块
        json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = result
        
        data = json.loads(json_str)
        cover_title = data.get("cover_title", "今日车圈重磅速递")
        news_list = data.get("news", [])
        
        # 确保 ≤5条
        news_list = news_list[:5]
        
        # 验证每条数据完整
        for item in news_list:
            if "title" not in item or not item["title"]:
                item["title"] = "汽车行业快讯"
            if "summary" not in item or not item["summary"]:
                item["summary"] = item["title"][:20]
            if "source" not in item or not item["source"]:
                item["source"] = "综合资讯"
        
        print(f"[LLM] 封面标题: {cover_title}")
        print(f"[LLM] 精选新闻: {len(news_list)} 条")
        
        return {
            "cover_title": cover_title,
            "news": news_list,
        }
    
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] LLM 输出解析失败: {e}")
        print(f"[DEBUG] LLM 原始输出:\n{result[:500]}")
        return None


# ========== 备用数据 ==========

def get_fallback_news():
    """当 LLM 不可用时的备用数据"""
    today = datetime.date.today()
    return {
        "cover_title": "车圈今日大事件",
        "news": [
            {"title": "比亚迪第1700万辆新能源车下线", "summary": "海豹08成里程碑车型，续航905km", "source": "比亚迪"},
            {"title": "全新坦克300开启预售", "summary": "25.98万起，轴距加长260mm", "source": "长城汽车"},
            {"title": "奔驰纯电GLC SUV上市", "summary": "入门29.99万，续航超700km", "source": "梅赛德斯-奔驰"},
            {"title": "腾势Z登陆古德伍德速度节", "summary": "中国超跑全球首秀三电机千匹", "source": "腾势汽车"},
            {"title": "上半年新能源车产销超700万辆", "summary": "6月出口首破100万辆增75%", "source": "中汽协"},
        ]
    }


# ========== HTML 邮件生成 ==========

def build_html(news_list, cover_title, today_str, source_info=""):
    """构建深色主题精美 HTML 邮件"""
    items_html = ""
    emojis = ["①", "②", "③", "④", "⑤"]
    colors = ["#f7931e", "#00d2ff", "#ff6b6b", "#48dbfb", "#feca57"]
    
    for i, news in enumerate(news_list):
        items_html += f"""
<tr>
  <td style="padding: 8px 0;">
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
  
  <tr><td style="height:20px;"></td></tr>
  {items_html}
  
  <tr><td style="height:24px;"></td></tr>
  <tr>
    <td style="text-align:center; padding:20px 0; border-top:1px solid #222;">
      <p style="color:#444; font-size:12px; margin:0;">
        ⏰ 每日上午10:00 自动推送 &nbsp;|&nbsp; 🤖 由 DeepSeek AI 分析生成<br>
        Powered by <span style="color:#f7931e;">WorkBuddy</span> 🚀
      </p>
    </td>
  </tr>
  
</table>
</body>
</html>"""


# ========== 邮件发送 ==========

def send_email(subject, html_body):
    if not PASSWORD:
        print("[ERROR] 未设置 QMAIL_AUTH_CODE!")
        return False
    
    msg = MIMEMultipart('alternative')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        server.starttls()
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, [RECEIVER], msg.as_string())
        server.quit()
        print(f"[OK] 邮件发送成功 → {RECEIVER}")
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
    print(f"🚗 每日汽车热点生成器 (DeepSeek AI)")
    print(f"📅 {today_str}")
    print(f"{'='*50}")
    
    # 1. 抓取新闻
    print("\n[1/4] 抓取实时新闻...")
    raw_text = fetch_raw_news()
    news_count = len(raw_text.split("【来源：")) - 1 if raw_text else 0
    print(f"  获取到 {news_count} 个新闻源")
    
    # 2. LLM 分析
    result = None
    source_info = ""
    
    if raw_text and DEEPSEEK_API_KEY:
        print("\n[2/4] DeepSeek AI 分析中...")
        result = analyze_news_with_llm(raw_text, today_str)
        if result:
            source_info = "🤖 实时抓取 + AI 精选分析"
        else:
            print("[WARN] LLM 分析失败，使用备用数据")
    
    if not result:
        print("\n[2/4] 使用备用精选数据...")
        result = get_fallback_news()
        source_info = "📋 今日精选备用数据"
    
    cover_title = result["cover_title"]
    news = result["news"]
    
    # 3. 构建邮件
    print("\n[3/4] 构建邮件...")
    subject = f"🚗 每日汽车热点 | {date_short} | {cover_title}"
    html_content = build_html(news, cover_title, today_str, source_info)
    
    # 保存文件
    report_path = OUTPUT_DIR / f"car_news_{today.strftime('%Y%m%d')}.html"
    report_path.write_text(html_content, encoding='utf-8')
    print(f"  报告已保存: {report_path}")
    
    data_path = OUTPUT_DIR / f"news_{today.strftime('%Y%m%d')}.json"
    data_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 4. 发送
    print("\n[4/4] 发送邮件...")
    success = send_email(subject, html_content)
    
    print(f"\n{'='*50}")
    print(f"📰 封面标题: {cover_title}")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']}")
        print(f"     → {n['summary']}")
    print(f"{'='*50}")
    print(f"{'✅ 完成!' if success else '⚠️ 邮件发送失败，但报告已生成'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
