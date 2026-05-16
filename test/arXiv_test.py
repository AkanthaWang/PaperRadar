# import arxiv

# # 搜索并下载
# search = arxiv.Search(query="", max_results=1)
# paper = next(search.results())
# paper.download_pdf(filename="")
# print(f"下载完成: {paper.title}")


# import arxiv

# # 创建 Client 实例
# client = arxiv.Client()

# # 创建 Search 对象（只定义查询条件，不直接执行）
# search = arxiv.Search(
#     query="Learning How and What to Memorize: Cognition-Inspired Two-Stage Optimization for Evolving Memory",
#     max_results=1
# )

# # 通过 client.results() 获取结果
# paper = next(client.results(search))

# print(paper.title)
# paper.download_pdf(filename="Learning How and What to Memorize: Cognition-Inspired Two-Stage Optimization for Evolving Memory.pdf")




# import arxiv
# import time

# client = arxiv.Client(
#     page_size=100,           # 每页结果数
#     delay_seconds=3.0,       # 请求间隔（默认 3 秒，可增大）
#     num_retries=3            # 重试次数
# )

# search = arxiv.Search(
#     query="Learning How and What to Memorize: Cognition-Inspired Two-Stage Optimization for Evolving Memory",
#     max_results=1
# )

# try:
#     paper = next(client.results(search))
#     print(paper.title)
#     paper.download_pdf(filename="paper.pdf")
# except Exception as e:
#     print(f"下载失败: {e}")




import requests

arxiv_id = "2605.00702"  # 替换为实际 ID
pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

r = requests.get(pdf_url)
with open("paper.pdf", "wb") as f:
    f.write(r.content)
print("下载完成")