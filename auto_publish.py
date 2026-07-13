#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日汽车热点自动发布脚本
- 抓取汽车行业热点
- 生成5条新闻内容图 + 1张封面
- 发布到小红书
"""

import os
import sys
import json
import base64
import subprocess
import datetime
import requests
from pathlib import Path

# 配置
WORKSPACE = Path("/workspace/car_news_daily")
IMAGES_DIR = WORKSPACE / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

COVER_PATH = IMAGES_DIR / "cover.png"
CONTENT_PATHS = [IMAGES_DIR / f"news_{i}.png" for i in range(1, 6)]

MCP_URL = os.environ.get("MCP_URL", "http://localhost:18060/mcp")


def call_mcp(method: str, params: dict) -> dict:
    """调用小红书 MCP 服务"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    resp = requests.post(MCP_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def search_car_news():
    """搜索汽车热点新闻 (简单模拟，实际可替换为更复杂的抓取逻辑)"""
    # 这里使用预设的5条最新新闻，或者调用搜索接口
    # 由于 WebSearch 是 Agent 工具，脚本中可用简单关键词聚合
    news_list = [
        {
            "title": "比亚迪第1700万辆新能源车下线",
            "summary": "海豹08成里程碑车型",
            "prompt": "小红书风格汽车新闻卡片设计。画面主体为比亚迪海豹08豪华电动轿车，海洋蓝色调。顶部醒目大字标题\"比亚迪第1700万辆新能源车下线\"。下方副标题\"海豹08成里程碑车型\"。现代简约设计风格，科技感。正方形比例。"
        },
        {
            "title": "全新坦克300开启预售",
            "summary": "25.98万起 轴距加长260mm",
            "prompt": "小红书风格汽车新闻卡片设计。画面主体为全新坦克300硬派越野SUV，沙漠山川背景。顶部醒目大字标题\"全新坦克300开启预售\"。下方副标题\"25.98万起 轴距加长260mm\"。硬派越野设计风格。正方形比例。"
        },
        {
            "title": "奔驰纯电GLC SUV上市",
            "summary": "入门29.99万 续航超700km",
            "prompt": "小红书风格汽车新闻卡片设计。画面主体为奔驰纯电GLC SUV，豪华电动SUV，都市背景。顶部醒目大字标题\"奔驰纯电GLC SUV上市\"。下方副标题\"入门29.99万 续航超700km\"。豪华简约设计风格。正方形比例。"
        },
        {
            "title": "腾势Z登陆古德伍德速度节",
            "summary": "中国超跑全球首秀 三电机千匹",
            "prompt": "小红书风格汽车新闻卡片设计。画面主体为腾势Z跑车，炫酷超跑，赛道背景，动感十足。顶部醒目大字标题\"腾势Z登陆古德伍德速度节\"。下方副标题\"中国超跑全球首秀 三电机千匹\"。运动感设计风格。正方形比例。"
        },
        {
            "title": "上半年新能源车产销超700万辆",
            "summary": "6月出口首破100万辆",
            "prompt": "小红书风格汽车新闻卡片设计。画面主体为新能源汽车生产线，展示中国新能源汽车产业规模。顶部醒目大字标题\"上半年新能源车产销超700万辆\"。下方副标题\"6月出口首破100万辆\"。数据可视化风格，科技蓝绿色调。正方形比例。"
        }
    ]
    return news_list


def generate_image(prompt: str, output_path: Path):
    """调用 ImageGen 生成图片（这里假设环境支持）"""
    # 在 Python 中直接调用 deferred 工具较复杂，实际生产环境可通过 API 调用
    # 简化方案：先写入 prompt 文件，后续用 ImageGen 处理
    # 或者使用本地 Pillow 生成简单卡片
    pass


def publish_to_xiaohongshu(title: str, content: str, image_paths: list, tags: list):
    """发布图文笔记到小红书"""
    result = call_mcp("publish_content", {
        "title": title,
        "content": content,
        "images": [str(p) for p in image_paths],
        "tags": tags
    })
    return result


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    print(f"[{today}] 开始生成汽车热点内容...")

    # 1. 抓取新闻
    news = search_car_news()

    # 2. 生成封面和5张内容图
    # 实际使用 ImageGen 时，这里会生成图片
    cover_title = "车圈炸了！7月新车狂潮"

    # 3. 构造正文
    body_lines = [f"每日汽车热点精选 | {today}", ""]
    for i, item in enumerate(news, 1):
        body_lines.append(f"{i}. {item['title']}")
        body_lines.append(f"   {item['summary']}")
    body_lines.append("")
    body_lines.append("#汽车 #新能源���车 #汽车资讯 #新车上市")
    content = "\n".join(body_lines)

    # 4. 发布 (图片路径需要真实存在)
    all_images = [COVER_PATH] + CONTENT_PATHS
    if not all(p.exists() for p in all_images):
        print(f"错误：图片文件未生成，请确保 {IMAGES_DIR} 中有完整图片")
        sys.exit(1)

    print(f"发布封面标题：{cover_title}")
    print(f"使用图片：{[str(p) for p in all_images]}")
    result = publish_to_xiaohongshu(
        title=cover_title,
        content=content,
        image_paths=all_images,
        tags=["汽车", "新能源汽车", "汽车资讯", "新车上市"]
    )
    print("发布结果：", json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
