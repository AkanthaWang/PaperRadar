import argparse
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def filter_titles_by_keyword(
	input_dir: Path,
	output_file: Path,
	keyword: str = "emotion",
	conference_name: str = "AAAI",
	conference_year: str = "2025",
	type_filter: bool = False,
	allowed_types=None,
) -> int:
	if allowed_types is None:
		allowed_types = ["oral", "poster", "spotlight"]
	allowed_types_set = {t.strip().lower() for t in allowed_types if str(t).strip()}

	conference_key = f"{conference_name}{conference_year}".lower()
	csv_files = sorted(
		path for path in input_dir.glob("*.csv")
		if conference_key in path.stem.lower()
	)
	if not csv_files:
		raise FileNotFoundError(
			f"No csv file matched conference/year: {conference_name}{conference_year} in {input_dir}"
		)

	matched_frames = []
	for csv_path in csv_files:
		df = pd.read_csv(csv_path)
		if "title" not in df.columns:
			continue

		mask = df["title"].astype(str).str.contains(keyword, case=False, na=False)
		matched_df = df.loc[mask].copy()

		if type_filter and ("type" in matched_df.columns):
			type_mask = matched_df["type"].astype(str).str.strip().str.lower().isin(allowed_types_set)
			matched_df = matched_df.loc[type_mask]
		elif type_filter:
			matched_df = matched_df.iloc[0:0]

		if not matched_df.empty:
			matched_df.insert(0, "source_file", csv_path.name)
			matched_frames.append(matched_df)

	output_file.parent.mkdir(parents=True, exist_ok=True)

	if matched_frames:
		result = pd.concat(matched_frames, ignore_index=True)
	else:
		result = pd.DataFrame(columns=["source_file", "title"])

	result.to_csv(output_file, index=False, encoding="utf-8-sig")
	return len(result)

def argparse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Filter papers by keyword in title from csv files.")
	parser.add_argument("--input-dir", default="data", help="Directory containing source csv files (relative to project root by default).")
	parser.add_argument("--output-dir", default="filtered_data", help="Output directory for filtered csv files (relative to project root by default).")
	parser.add_argument("--keyword", default="emotion", help="Keyword to match in title.")
	parser.add_argument("--conference-name", default="AAAI", help="Conference name, e.g. AAAI.")
	parser.add_argument("--conference-year", default="2025", help="Conference year, e.g. 2026.")
	parser.add_argument("--types", default="oral,poster,spotlight", help="Allowed types, comma-separated.")
	return parser.parse_args()

def main():
	args = argparse_args()

	input_dir = Path(args.input_dir)
	if not input_dir.is_absolute():
		input_dir = PROJECT_ROOT / input_dir

	output_dir = Path(args.output_dir)
	if not output_dir.is_absolute():
		output_dir = PROJECT_ROOT / output_dir

	conference_name = args.conference_name
	conference_year = args.conference_year
	conference_key = f"{conference_name}{conference_year}".lower()
	should_filter_type = conference_name.strip().lower() in {"iclr", "icml", "neurips"}
	
	csv_files = sorted(
		path for path in input_dir.glob("*.csv")
		if conference_key in path.stem.lower()
	)
	if not csv_files:
		raise FileNotFoundError(
			f"No csv file matched conference/year: {conference_name}{conference_year} in {input_dir}"
		)

	safe_keyword = args.keyword.strip().replace(" ", "_") or "keyword"
	output_file = output_dir / f"{csv_files[0].stem}_{safe_keyword}.csv"
	allowed_types = [item.strip() for item in args.types.split(",") if item.strip()]

	count = filter_titles_by_keyword(
		input_dir=input_dir,
		output_file=output_file,
		keyword=args.keyword,
		conference_name=conference_name,
		conference_year=conference_year,
		type_filter=should_filter_type,
		allowed_types=allowed_types,
	)
	print(f"Done. Matched rows: {count}")
	print(f"Saved to: {output_file}")


if __name__ == "__main__":
	main()
