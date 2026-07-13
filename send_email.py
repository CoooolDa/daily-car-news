#!/usr/bin/env python3
"""
每日汽车热点邮件发送脚本
通过 QQ 邮箱 SMTP 发送精美 HTML 邮件
"""

import smtplib
import os
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from datetime import date

# 配置
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SENDER = "740418164@qq.com"
PASSWORD = "wiqakxqpwuorbdda"
RECEIVER = "740418164@qq.com"
IMG_DIR = "/workspace/car_news_images"

def build_html(news_list, cover_title, today_str):
    """构建精美HTML邮件"""
    items_html = ""
    for i, news in enumerate(news_list, 1):
        items_html += f"""
<div style="background:#1a1a2e; border-radius:12px; padding:20px; margin-bottom:12px;">
<h3 style="color:#f7931e; margin:0 0 8px;">{'①②③④⑤'[i-1]} {news['title']}</h3>
<p style="color:#aaa; margin:0;">{news['summary']}</p>
</div>"""

    return f"""<html><body style="font-family: -apple-system, 'PingFang SC', sans-serif; max-width:600px; margin:0 auto; padding:20px; background:#111; color:#fff;">
<div style="background: linear-gradient(135deg, #ff6b35, #f7931e); border-radius:16px; padding:30px; text-align:center; margin-bottom:20px;">
<h1 style="font-size:28px; margin:0; color:#fff;">{cover_title}</h1>
<p style="margin:10px 0 0; opacity:0.85; color:#fff;">{today_str} · 每日汽车热点精选</p>
</div>
{items_html}
<div style="text-align:center; padding:20px; color:#555; font-size:12px; border-top:1px solid #222; margin-top:20px;">
<p>📸 6张小红书风格卡片已生成（含封面+5内容图）</p>
<p>⏰ 每日上午10:00 自动推送</p>
<p>Powered by WorkBuddy 🚀</p>
</div>
</body></html>"""

def send_email(subject, html_body, img_dir):
    """发送HTML邮件（嵌入图片）"""
    msg = MIMEMultipart('related')
    msg['From'] = SENDER
    msg['To'] = RECEIVER
    msg['Subject'] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    # 嵌入图片
    if os.path.isdir(img_dir):
        img_files = sorted(glob.glob(f"{img_dir}/*.png"))
        for i, fpath in enumerate(img_files):
            with open(fpath, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-ID', f'<img{i}>')
                img.add_header('Content-Disposition', 'inline', filename=f'car_news_{i+1}.png')
                msg.attach(img)

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    server.starttls()
    server.login(SENDER, PASSWORD)
    server.sendmail(SENDER, [RECEIVER], msg.as_string())
    server.quit()
    print("✅ 邮件发送成功！")

if __name__ == "__main__":
    # 示例：由 Agent 调用时传入参数
    today_str = date.today().strftime("%Y年%m月%d日")
    news = [
        {"title": "示例新闻", "summary": "请由Agent动态填充"}
    ]
    cover = "车圈每日热点"
    html = build_html(news, cover, today_str)
    print(f"准备发送: {cover}")
    # send_email(f"🚗 每日汽车热点 | {today_str} | {cover}", html, IMG_DIR)
