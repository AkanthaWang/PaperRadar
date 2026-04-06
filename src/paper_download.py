import os
import re
import argparse
import pandas as pd
import requests
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 添加常见的浏览器请求头，避免 403 Forbidden 错误
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

def sanitize_filename(filename: str) -> str:
    """
    清洗文件名，移除操作系统不支持的非法字符。
    """
    # 移除非法字符: \ / : * ? " < > |
    filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
    # 移除文件名末尾的句号或空格（Windows下可能导致问题）
    filename = filename.strip().rstrip('.')
    # 限制长度，防止某些系统下的路径过长
    return filename[:200]

def download_paper(row: pd.Series, output_dir: Path, conference_name: str, year: str) -> bool:
    """
    下载单篇论文。
    """
    title = row.get('title', 'unknown_title')
    url = row.get('url')
    
    if not url or pd.isna(url):
        # print(f"Skipping: {title} (No URL found)")
        return False
        
    # 针对不同平台的链接进行优化
    # 1. OpenReview: forum 链接转换为 pdf 链接
    if 'openreview.net/forum' in url:
        url = url.replace('forum', 'pdf')
    # 2. AAAI/OJS 平台: article/view 链接转换为 article/download 链接 (如果适用)
    elif 'ojs.aaai.org' in url and '/article/view/' in url:
        # 尝试将 view 替换为 download，这在某些 OJS 配置中是直接下载链接
        url = url.replace('/article/view/', '/article/download/')
        
    sanitized_title = sanitize_filename(title)
    filename = f"{year}_{conference_name}_{sanitized_title}.pdf"
    file_path = output_dir / filename
    
    if file_path.exists():
        # print(f"Already exists: {filename}")
        return True
        
    try:
        # 使用 DEFAULT_HEADERS 发起请求，规避反爬虫策略
        response = requests.get(url, stream=True, timeout=30, headers=DEFAULT_HEADERS)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Failed to download {filename}: {str(e)}")
        return False

def paper_download(csv_path: str, output_dir: str, conference_name: str, year: str, max_workers: int = 5):
    """
    主下载函数：从 CSV 中读取论文并批量下载。
    """
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
    df = pd.read_csv(csv_path)
    if 'url' not in df.columns:
        raise ValueError("CSV file must contain a 'url' column.")
    
    print(f"Starting download for {len(df)} papers from {csv_path}...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 使用 list 让 tqdm 能够正确显示进度
        list(tqdm(executor.map(lambda row: download_paper(row[1], output_dir, conference_name, year), df.iterrows()), 
                  total=len(df), unit="paper"))

    print(f"\nDownload task completed. Papers are saved in: {output_dir}")


def argparse_args() -> argparse.Namespace:
    """
    解析命令行参数。
    :return: 包含解析后的参数的 argparse.Namespace 对象。
    """
    parser = argparse.ArgumentParser(description="Download papers from metadata CSV files.")
    parser.add_argument("--csv-path", required=True, help="Path to the source CSV file (e.g., data/neurips2025_metadata.csv)")
    parser.add_argument("--output-dir", default="downloads", help="Directory to save downloaded PDFs.")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent download workers.")
    return parser.parse_args()


def main():
    args = argparse_args()
    
    # 转换相对路径为绝对路径
    csv_path = Path(args.csv_path)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
        
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return

    # 从文件名中自动提取会议名称和年份 (例如: neurips2025_metadata.csv)
    # 匹配模式：字母部分为会议名，数字部分为年份
    match = re.search(r'([a-zA-Z]+)(\d{4})', csv_path.name)
    if not match:
        print(f"Error: Could not extract conference and year from filename '{csv_path.name}'.")
        print("Expected format: {conference}{year}_metadata.csv (e.g., neurips2025_metadata.csv)")
        return
    
    conference_name = match.group(1).upper()
    year = match.group(2)
    
    print(f"Detected Conference: {conference_name}, Year: {year}")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
        
    paper_download(
        csv_path=str(csv_path),
        output_dir=str(output_dir),
        conference_name=conference_name,
        year=year,
        max_workers=args.workers
    )

if __name__ == "__main__":
    main()
