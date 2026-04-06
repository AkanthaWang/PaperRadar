'''
支持抓取以下会议的论文数据：ICML、ICLR、NeurIPS
'''

import argparse
import csv
import os
from collections import defaultdict
from typing import Dict, List
import openreview
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class OpenReviewScraper:
    def __init__(self, venue: str, output_csv: str, baseurl: str = 'https://api2.openreview.net'):
        self.venue = venue
        self.output_csv = output_csv
        self.baseurl = baseurl

    def _build_client(self) -> openreview.api.OpenReviewClient:
        username = os.getenv('OPENREVIEW_USERNAME')
        password = os.getenv('OPENREVIEW_PASSWORD')

        if not username or not password:
            raise ValueError('请先在 .env 文件中设置 OPENREVIEW_USERNAME 和 OPENREVIEW_PASSWORD')

        return openreview.api.OpenReviewClient(
            baseurl=self.baseurl,
            username=username,
            password=password
        )

    def _fetch_papers(self, client: openreview.api.OpenReviewClient) -> List[openreview.api.Note]:
        submission_invitation = f'{self.venue}/-/Submission'
        papers = list(openreview.tools.iterget_notes(client, invitation=submission_invitation))
        print(f'抓取到 {len(papers)} 篇论文')
        return papers

    @staticmethod
    def _normalize_paper_type(venue_info: str) -> str:
        venue_info = (venue_info or '').lower()
        if 'oral' in venue_info:
            return 'oral'
        if 'spotlight' in venue_info:
            return 'spotlight'
        if 'poster' in venue_info:
            return 'poster'
        return venue_info or 'unknown'

    def _group_by_type(self, papers: List[openreview.api.Note]) -> Dict[str, List[openreview.api.Note]]:
        by_type = defaultdict(list)
        for note in papers:
            venue_info = note.content.get('venue', {}).get('value', '')
            paper_type = self._normalize_paper_type(venue_info)
            by_type[paper_type].append(note)
        return by_type

    def _write_csv(self, grouped_papers: Dict[str, List[openreview.api.Note]]) -> None:
        output_dir = os.path.dirname(self.output_csv)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(self.output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['paper_id', 'title', 'type', 'keywords', 'abstract', 'url'])

            for paper_type, paper_list in grouped_papers.items():
                for paper in paper_list:
                    paper_id = paper.id
                    title = paper.content.get('title', {}).get('value', '').replace('\n', ' ')
                    keywords = ','.join(paper.content.get('keywords', {}).get('value', []))
                    abstract = paper.content.get('abstract', {}).get('value', '').replace('\n', ' ')
                    url = f'https://openreview.net/pdf?id={paper_id}'
                    writer.writerow([paper_id, title, paper_type, keywords, abstract, url])
        print(f'CSV 已保存至: {self.output_csv}')

    def run(self) -> None:
        client = self._build_client()
        papers = self._fetch_papers(client)
        grouped_papers = self._group_by_type(papers)
        self._write_csv(grouped_papers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='OpenReview 会议论文数据抓取工具')
    parser.add_argument('--conference_name', default='NeurIPS', help='会议名称，例如 ICML')
    parser.add_argument('--conference_year', default='2025', help='会议年份，例如 2025')
    parser.add_argument('--baseurl', default='https://api2.openreview.net', help='OpenReview API Base URL')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    venue = f'{args.conference_name}.cc/{args.conference_year}/Conference'
    output_path = os.path.join(PROJECT_ROOT, "data", f"{args.conference_name.lower()}{args.conference_year}_metadata.csv")  # 输出文件路径
    scraper = OpenReviewScraper(venue=venue, output_csv=output_path, baseurl=args.baseurl)
    scraper.run()

