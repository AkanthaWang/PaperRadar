python -m src.pipeline.cli parse \
  --pdf-dir "data/pdfs" \
  --outputs-dir "data/parsed" \

python -m src.pipeline.cli summarize \
  --pdf-dir "data/pdfs" \
  --outputs-dir "data/parsed" \
  --reports-dir "data/reports" \
  --parse-missing \
  --llm-provider ecnu \
  --ecnu-model ecnu-max \
  --overwrite