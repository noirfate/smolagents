#!/usr/bin/env python3
import os
import re
import logging
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
import time
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def firecrawler_get(url: str, retries: int = 3, backoff_seconds: float = 1.0) -> str:
    try:
        api_key = os.getenv("FIRECRAWL_API_KEY")
        api_url = os.getenv("FIRECRAWL_API_URL")
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY 环境变量未设置")

        # 如果未设置 API_URL，使用官方默认地址（不传 api_url 参数）
        if api_url:
            logger.info(f"使用自定义 Firecrawl API: {api_url}")
            app = FirecrawlApp(api_key=api_key, api_url=api_url)
        else:
            logger.info("使用 Firecrawl 官方 API")
            app = FirecrawlApp(api_key=api_key)
    except Exception as e:
        logger.error(f"初始化Firecrawl失败: {e}")
        raise

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"开始抓取网页(第{attempt}/{retries}次): {url}")
            #result = app.scrape(url, formats=['markdown'])
            result = app.scrape(url, formats=['markdown'], wait_for=10000)
            print(result.metadata_dict)
            # 兼容不同返回结构，尽量提取markdown文本
            if isinstance(result, dict):
                if 'markdown' in result and isinstance(result['markdown'], str):
                    return result['markdown']
                if 'data' in result and isinstance(result['data'], dict) and isinstance(result['data'].get('markdown'), str):
                    return result['data']['markdown']
                if 'content' in result and isinstance(result['content'], str):
                    return result['content']
                # 非标准结构，转字符串兜底
                return str(result)
            return str(result)
        except Exception as e:
            last_error = e
            logger.error(f"抓取过程中发生错误(第{attempt}次): {str(e)}")
            if attempt < retries:
                sleep_for = backoff_seconds * (2 ** (attempt - 1))
                logger.info(f"等待 {sleep_for:.1f}s 后重试...")
                time.sleep(sleep_for)

    # 重试用尽仍失败
    assert last_error is not None
    raise last_error



def sanitize_filename(name):
    # Remove invalid characters for a filename
    name = re.sub(r'[\'\"]', '', name)  # remove quotes
    name = re.sub(r'[\\/*?:"<>|]', "", name)  # remove illegal characters
    name = re.sub(r'\s+', '_', name)  # replace spaces with underscores
    return name



def save_markdown(content: str, base_title: str, index: int, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = sanitize_filename(f"{base_title}__ref{index+1}") + ".md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath



if __name__ == '__main__':
    # main()
    OUTPUT_DIR = "./"

    #url = "https://support.huaweicloud.com/productdesc-bcs/bcs-productdesc-pdf.pdf"
    url = 'https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf'
    filename = url.split("/")[-1]
    md = firecrawler_get(url, retries=3)
    # print(md)
    save_markdown(md, filename, 0, OUTPUT_DIR)