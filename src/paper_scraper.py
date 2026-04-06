'''
支持抓取以下会议的论文数据：ICCV、CVPR、AAAI、ACMMM、ECCV、
'''

import pandas as pd
import re
import os
import time
import requests
import bs4
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium import webdriver
import argparse

DBLP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
    "Connection": "keep-alive",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
}
DBLP_VISION_SECTION_INDEXES = [2, 3, 4]
RETRIEVE_WITH_YEAR = {"ECCV", "CVPR", "ICLR"}
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _normalize_paper_ids(paper_ids, total):
    if paper_ids is None:
        return list(range(1, total + 1))

    normalized = []
    used_ids = set()
    next_id = 1
    for raw_id in paper_ids:
        current_id = None
        if pd.notna(raw_id):
            try:
                parsed_id = int(raw_id)
                if parsed_id > 0 and parsed_id not in used_ids:
                    current_id = parsed_id
            except (ValueError, TypeError):
                current_id = None

        if current_id is None:
            while next_id in used_ids:
                next_id += 1
            current_id = next_id

        used_ids.add(current_id)
        normalized.append(current_id)
    return normalized


def _build_papers_dataframe(pdfnamelist, pdfurllist,
                            paper_types=None, keywords_list=None,
                            abstracts=None, paper_ids=None):
    total = len(pdfnamelist)
    if len(pdfurllist) != total:
        raise ValueError("The number of titles and urls must match.")

    paper_ids = _normalize_paper_ids(paper_ids, total)
    paper_types = paper_types if paper_types is not None else [""] * total
    keywords_list = keywords_list if keywords_list is not None else [""] * total
    abstracts = abstracts if abstracts is not None else [""] * total

    if not (len(paper_types) == len(keywords_list) == len(abstracts) == total):
        raise ValueError("paper_types, keywords_list and abstracts must have same length as titles.")

    return pd.DataFrame({
        "paper_id": paper_ids,
        "title": pdfnamelist,
        "type": paper_types,
        "keywords": keywords_list,
        "abstract": abstracts,
        "url": pdfurllist,
    })


def _extract_matched_keywords(title, patterns):
    if not patterns:
        return ""
    matched = []
    for pattern in patterns:
        if re.search(pattern, title):
            matched.append(pattern)
    return ", ".join(matched)


def _retrieve_from_dblp_proceedings(driver, target_list=None):
    pdfurllist = []
    pdfnamelist = []

    soup = bs4.BeautifulSoup(driver.page_source, features="lxml")
    ele_list = soup.select('ul.publ-list')

    if target_list is None:
        target_indexes = DBLP_VISION_SECTION_INDEXES
    elif isinstance(target_list, str) and target_list.lower() == "all":
        target_indexes = range(len(ele_list))
    else:
        target_indexes = target_list

    for idx in target_indexes:
        if idx >= len(ele_list):
            continue
        papers_info = ele_list[idx].select("li.entry.inproceedings")
        for paper in papers_info:
            title_node = paper.select_one(".title")
            head_node = paper.select_one("div.head a")
            if title_node is None or head_node is None:
                continue

            title = title_node.text.strip()
            paper_from_link = head_node.get('href')
            if not paper_from_link:
                continue

            try:
                paper_response = requests.get(paper_from_link, headers=DBLP_HEADERS, timeout=30)
                paper_response.raise_for_status()
            except requests.RequestException:
                continue

            paper_soup = bs4.BeautifulSoup(paper_response.text, features='lxml')
            pdf_node = paper_soup.select_one("a.obj_galley_link.pdf")
            if pdf_node is None:
                continue

            pdf_href = pdf_node.get('href')
            if not pdf_href:
                continue

            pdfnamelist.append(title)
            pdfurllist.append(urljoin(paper_response.url, pdf_href))

    return pdfurllist, pdfnamelist


def _print_export_preview(df, preview_rows=5):
    print(f"The Number of Paper ALL: {len(df)}")
    if len(df) == 0:
        print("No papers found.")
        return

    print("Preview of metadata:")
    preview = df[["paper_id", "title", "keywords"]].head(preview_rows)
    print(preview.to_string(index=False))


def build_conference_url(conference, year):
    """
    some variables needed to be set up by users
    conference urls examples:
    ICCV: https://openaccess.thecvf.com/ICCV2023?day=all (ICCV 2023)
    CVPR: https://openaccess.thecvf.com/CVPR2021?day=all (CVPR 2021)
    ECCV: https://www.ecva.net/papers.php (ECCV 2020) (changed in 2020)
    CVPR: https://openaccess.thecvf.com/CVPR2020 (CVPR before 2020)
    AAAI: https://dblp.uni-trier.de/db/conf/aaai/aaai2022.html
    Blow are not tested, may need some modify in retrieve_titles_urls_from_websites.py
    siggraph: https://dl.acm.org/toc/tog/2020/39/4 (SIGGRAPH 2021)
    
    """
    if conference in ["CVPR", "ICCV"]:
        return f"https://openaccess.thecvf.com/{conference}{year}?day=all"
    if conference == "ECCV":
        return "https://www.ecva.net/papers.php"
    if conference == "AAAI":
        return f"https://dblp.uni-trier.de/db/conf/aaai/aaai{year}.html"
    if conference == "ACMMM":
        return f"https://dblp.uni-trier.de/db/conf/mm/mm{year}.html"
    raise ValueError(f"Unsupported conference for URL building: {conference}")



def retrieve_from_siggraph(driver):
    pdfurllist = []
    pdfnamelist = []
    import time
    elementllist = driver.find_elements_by_class_name('accordion-tabbed')[1].find_elements_by_class_name('toc__section')
    for i, section in enumerate(elementllist):
        section.click()
        time.sleep(3)
        print('\n', section.text)
        for j, paper_element in enumerate(section.find_elements_by_class_name('issue-item__content')):
            paper_name = paper_element.find_element_by_xpath('div/h5').text
            pdf_url = paper_element.find_element_by_class_name('red').get_attribute('href')
            print('\t', paper_name)
            pdfnamelist.append(paper_name)
            pdfurllist.append(pdf_url)
    return pdfurllist, pdfnamelist

def retrieve_from_CVPR(driver, year):
    pdfurllist = []
    pdfnamelist = []
    if int(year) > 2020:  # 2020年以后
        title_element_list = driver.find_elements(by=By.CLASS_NAME, value='ptitle')
        url_element_list = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value='pdf')
        for i, element in enumerate(url_element_list):
            pdfnamelist.append(title_element_list[i].text)
            pdfurllist.append(url_element_list[i].get_attribute('href'))
    else:  # 2020年之前
        for day in range(3):
            driver.find_elements(by=By.XPATH, value='//body/div[3]/dl/dd/a')[day].click()
            title_element_list = driver.find_elements(by=By.CLASS_NAME, value='ptitle')
            url_element_list = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value='pdf')
            for i, element in enumerate(url_element_list):
                pdfnamelist.append(title_element_list[i].text)
                pdfurllist.append(url_element_list[i].get_attribute('href'))
            driver.back()
    return pdfurllist, pdfnamelist


def retrieve_from_ICCV(driver):
    pdfurllist = []
    pdfnamelist = []

    title_element_list = driver.find_elements(by=By.CLASS_NAME, value='ptitle')
    url_element_list = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value='pdf')
    for i, element in enumerate(url_element_list):
        pdfnamelist.append(title_element_list[i].text)
        pdfurllist.append(url_element_list[i].get_attribute('href'))
    return pdfurllist, pdfnamelist


def retrieve_from_ECCV(driver, year):
    pdfurllist = []
    pdfnamelist = []

    # 需要click一下按钮才能下载
    button_element = driver.find_elements(by=By.CLASS_NAME, value='accordion')
    pattern = str(year)
    # 点击对应年份的按钮
    time.sleep(2)  # 等待2s，让页面加载一会
    for i, element in enumerate(button_element):
        if re.search(pattern, element.text):
            driver.execute_script("arguments[0].click();", element)
            time.sleep(2)
            break
    # 找到论文和连接列表
    elementllist = driver.find_elements(by=By.CLASS_NAME, value='ptitle')
    url_element_list = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value='pdf')
    # 找到论文的题目
    for i, element in enumerate(elementllist):
        if len(element.text) > 0:
            pdfnamelist.append(element.text)
    # 找论文url
    for i, element in enumerate(url_element_list):
        pdfurllist.append(url_element_list[i].get_attribute('href'))
    return pdfurllist, pdfnamelist


def retrieve_from_AAAI(driver):
    return _retrieve_from_dblp_proceedings(driver, target_list="all")


def retrieve_from_ACMMM(driver):
    return _retrieve_from_dblp_proceedings(driver,target_list="all")



# 获取会议中的全部论文（仅返回，不写中间文件）
def get_all_papers(driver, conference, year):
    retrieve_name = 'retrieve_from_' + conference
    retrieve = globals().get(retrieve_name)
    if retrieve is None:
        raise ValueError(f"Unsupported conference: {conference}. Missing function {retrieve_name}.")

    print('Retrieving pdf urls. This could take some time...')
    if conference in RETRIEVE_WITH_YEAR:
        pdfurllist, pdfnamelist = retrieve(driver, year)
    else:
        pdfurllist, pdfnamelist = retrieve(driver)

    assert len(pdfnamelist) == len(pdfurllist), 'Web Crawler Error:The number of titles and the number of urls are not matched. \
                                                You might solve the problem by checking the HTML code in the \
                                                website yourself or you could ask the author by raising an issue.'
    return pdfnamelist, pdfurllist



# 将论文信息保存到excel中
def save_papers_info(pdfnamelist, pdfurllist, save_root, filename,
                     paper_types=None, keywords_list=None,
                     abstracts=None, paper_ids=None):
    df = _build_papers_dataframe(
        pdfnamelist,
        pdfurllist,
        paper_types=paper_types,
        keywords_list=keywords_list,
        abstracts=abstracts,
        paper_ids=paper_ids,
    )
    if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
        filename = filename + ".xlsx"
    save_filename = os.path.join(save_root, filename)
    if save_filename.endswith(".csv"):
        df.to_csv(save_filename, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(save_filename, index=False)




def export_papers_metadata(conference, year, conference_url, output_path, patterns=None):
    patterns = patterns or []
    output_dir = os.path.dirname(output_path) or "."
    os.makedirs(output_dir, exist_ok=True)

    driver = webdriver.Edge()
    driver.get(conference_url)

    try:
        pdfnamelist, pdfurllist = get_all_papers(driver, conference, year)
    finally:
        driver.quit()

    keywords_list = [_extract_matched_keywords(title, patterns) for title in pdfnamelist]
    abstracts = [""] * len(pdfnamelist)
    paper_types = [conference] * len(pdfnamelist)

    df = _build_papers_dataframe(
        pdfnamelist,
        pdfurllist,
        paper_types=paper_types,
        keywords_list=keywords_list,
        abstracts=abstracts,
        paper_ids=None,
    )
    df = df[["paper_id", "title", "type", "keywords", "abstract", "url"]]
    _print_export_preview(df)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print("Saved paper metadata to:", output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Paper 会议论文数据抓取工具')
    parser.add_argument('--conference_name', default='AAAI', help='会议名称，例如 AAAI')
    parser.add_argument('--conference_year', default='2026', help='会议年份，例如 2025')
    return parser.parse_args()


if __name__ == '__main__':
    # 设置变量 variables to be set
    args = parse_args()
    conference = args.conference_name
    year = args.conference_year
    conference_url = build_conference_url(conference, year)
    output_path = os.path.join(PROJECT_ROOT, "data", f"{conference.lower()}{year}_metadata.csv")  # 输出文件路径
    patterns = []                                                    # 仅用于keywords提取，不会过滤论文
    export_papers_metadata(conference, year, conference_url, output_path, patterns)
