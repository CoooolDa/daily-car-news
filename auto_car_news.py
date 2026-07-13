#!/usr/bin/env python3
"""
每日汽车热点 - 小红书内容生成器
用法: python3 auto_car_news.py
输出: /workspace/car_news_daily/images/ 下生成6张图片 + report.md 报告
"""

import os
import json
import shutil
import datetime
from pathlib import Path

WORKSPACE = Path("/workspace/car_news_daily")
IMAGES_DIR = WORKSPACE / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y年%m月%d日")
OUTPUT_REPORT = WORKSPACE / "report.md"

# ============================================================
# 每日新闻模板 - 实际运行时会由 Agent 抓取最新新闻填充
# 这里保留结构，Agent 执行时会动态替换内容
# ============================================================

def generate_report(news_list: list, cover_title: str, image_files: list):
    """生成每日报告"""
    lines = [
        f"# 每日汽车热点 - {TODAY}",
        "",
        f"## 封面标题：{cover_title}",
        "",
        "## 今日精选",
        ""
    ]
    for i, news in enumerate(news_list, 1):
        lines.append(f"### {i}. {news['title']}")
        lines.append(f"> {news['summary']}")
        lines.append("")

    lines.append("## 生成文件")
    for f in image_files:
        lines.append(f"- `{f}`")

    report = "\n".join(lines)
    OUTPUT_REPORT.write_text(report, encoding="utf-8")
    print(f"报告已保存到: {OUTPUT_REPORT}")
    return report


if __name__ == "__main__":
    print(f"🚗 每日汽车热点生成器 - {TODAY}")
    print(f"📁 输出目录: {IMAGES_DIR}")
    print()
    print("此脚本由 Agent 定时任务驱动。")
    print("Agent 将在每天 10:07 自动运行完整流程：")
    print("  1. 搜索最新汽车新闻 → 精选5条")
    print("  2. 生成小红书封面图 x1")
    print("  3. 生成新闻内容图 x5")
    print("  4. 发送通知到 WorkBuddy 手机端")
