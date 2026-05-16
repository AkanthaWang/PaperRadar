import argparse
from pathlib import Path
import pandas as pd
import re
from typing import Optional, List, Union

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_table(path: Path, sheet=None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file extension: {suffix}")


def _detect_column(df: pd.DataFrame, preferred: Optional[str], candidates: List[str]) -> str:
    if preferred and preferred in df.columns:
        return preferred
    lowered = {c.lower(): c for c in df.columns}
    for key in list(lowered.keys()):
        if key.replace(" ", "") not in lowered:
            lowered[key.replace(" ", "")] = lowered[key]
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    for cand in candidates:
        for k, v in lowered.items():
            if cand in k:
                return v
    raise KeyError(f"Required column not found. Candidates: {candidates}")


def extract_title_url(
    input_path: Path,
    output_path: Path,
    sheet: Optional[Union[str, int]] = None,
    title_col: Optional[str] = None,
    url_col: Optional[str] = None,
    txt_template: Optional[str] = None,
) -> int:
    df = _read_table(input_path, sheet)
    title_candidates = [
        "title",
        "papertitle",
        "name",
    ]
    url_candidates = [
        "url",
        "pdf",
        "pdfurl",
        "paperurl",
        "link",
        "pdflink",
    ]
    title_key = _detect_column(df, title_col, title_candidates)
    url_key = _detect_column(df, url_col, url_candidates)
    out = df[[title_key, url_key]].rename(columns={title_key: "title", url_key: "url"})
    out = out.dropna(subset=["title", "url"])
    out = out.drop_duplicates(subset=["url"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".xlsx", ".xls"}:
        out.to_excel(output_path, index=False)
    elif output_path.suffix.lower() == ".txt":
        template = txt_template or "{title}#{url}"
        with open(output_path, "w", encoding="utf-8") as f:
            for _, row in out.iterrows():
                f.write(template.format(title=str(row["title"]), url=str(row["url"])) + "\n")
    else:
        out.to_csv(output_path, index=False, encoding="utf-8-sig")
    return len(out)


def argparse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract title and url from Excel/CSV.")
    parser.add_argument("--input-path", default="filtered_data", help="Path to input Excel/CSV file.")
    parser.add_argument("--sheet", default=None, help="Excel sheet name or index.")
    parser.add_argument("--title-col", default="title", help="Explicit title column name.")
    parser.add_argument("--url-col", default="url", help="Explicit url column name.")
    parser.add_argument("--output-dir", default="extracted", help="Directory to save output file.")
    parser.add_argument("--output-format", default="txt", choices=["csv", "xlsx", "txt"], help="Output file format.")
    parser.add_argument("--txt-template", default="+ {title} [Paper]({url})", help="Template for txt lines, supports {title} and {url}.")
    return parser.parse_args()


def main():
    args = argparse_args()
    input_path = Path(args.input_path)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input path not found: {input_path}")
    
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    
    # 确定要处理的文件列表
    if input_path.is_dir():
        files_to_process = []
        for ext in [".csv", ".xlsx", ".xls"]:
            files_to_process.extend(input_path.glob(f"*{ext}"))
    else:
        files_to_process = [input_path]
    
    if not files_to_process:
        print(f"No supported files found in {input_path}")
        return

    for file in files_to_process:
        stem = re.sub(r"\s+", "_", file.stem)
        if args.output_format == "xlsx":
            suffix = ".xlsx"
        elif args.output_format == "txt":
            suffix = ".txt"
        else:
            suffix = ".csv"
        
        output_path = output_dir / f"{stem}_title_url{suffix}"
        
        try:
            count = extract_title_url(
                input_path=file,
                output_path=output_path,
                sheet=int(args.sheet) if str(args.sheet).isdigit() else args.sheet,
                title_col=args.title_col,
                url_col=args.url_col,
                txt_template=args.txt_template,
            )
            print(f"Processed {file.name}: {count} rows -> {output_path.name}")
        except Exception as e:
            print(f"Failed to process {file.name}: {e}")


if __name__ == "__main__":
    main()

