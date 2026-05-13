from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class FigureInfo:
    path: str
    page: int
    width: int
    height: int
    caption: str = ""
    context: str = ""


@dataclass
class ParsedPaper:
    pdf_path: str
    stem: str
    title: str
    venue: str
    year: str
    page_count: int
    metadata: dict[str, str]
    full_text: str
    page_texts: list[str]
    figures: list[FigureInfo]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["figures"] = [asdict(figure) for figure in self.figures]
        return data


def sanitize_name(value: str, max_length: int = 120) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "_", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    value = value or "paper"
    return value[:max_length]


def safe_stem_for_path(pdf_path: Path) -> str:
    return sanitize_name(pdf_path.stem)


def infer_metadata_from_filename(pdf_path: Path) -> tuple[str, str, str]:
    stem = pdf_path.stem
    match = re.match(r"^(?P<year>20\d{2})_(?P<venue>[^_]+)_(?P<title>.+)$", stem)
    if not match:
        return "", "", stem
    title = match.group("title").replace("_", ": ").strip()
    return match.group("year"), match.group("venue"), title


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_figure_labels_from_text(text: str) -> dict[str, tuple[int, str]]:
    """
    扫描全文，提取所有 Figure/Table 标题及其完整说明。
    返回 {"Figure 1": (line_index, "Figure 1: ... description..."), ...}
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    labels = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # 匹配 "Figure X:", "Table X:", "Fig. X:" 等
        match = re.match(
            r"^((?:fig(?:ure)?\.?|table)\s*\d+[\s:]*)",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            label_key = match.group(1).strip(":").strip().lower()
            # 收集该标题及后续最多 5 行作为 Caption（直到遇到新的标题或空行）
            caption_lines = [line]
            j = i + 1
            while j < len(lines) and j < i + 6:
                next_line = lines[j]
                # 如果遇到新的标题或清晰的段落开头，停止
                if re.match(r"^(fig(?:ure)?\.?|table|abstract|introduction|conclusion)", next_line, flags=re.IGNORECASE):
                    break
                caption_lines.append(next_line)
                j += 1
            caption = " ".join(caption_lines)[:600]
            labels[label_key] = (i, caption)
            i = j
        else:
            i += 1
    return labels


def find_closest_caption(page_index: int, labels: dict[str, tuple[int, str]]) -> str:
    """
    根据页码找到最接近的 Figure/Table 标题。
    假设标题行索引大致反映在 PDF 中的位置。
    """
    if not labels:
        return ""
    # 简单启发式：假设每页约 30-50 行文本，找最接近的标题
    estimated_page_line_start = page_index * 40
    estimated_page_line_end = (page_index + 1) * 40
    
    best_label = ""
    best_distance = float("inf")
    for label_key, (line_idx, caption) in labels.items():
        # 优先匹配同页或相邻页的标题
        if estimated_page_line_start <= line_idx < estimated_page_line_end + 50:
            distance = abs(line_idx - (estimated_page_line_start + 20))
            if distance < best_distance:
                best_distance = distance
                best_label = caption
    return best_label


def is_valid_image(pix) -> bool:
    """
    检查图像是否有效（不是全白、全黑或其他垃圾图）。
    """
    try:
        # 采样图像的几个点，检查是否都是单一颜色
        if pix.width < 50 or pix.height < 50:
            return False
        # 简单检查：采样中心像素，避免纯色图
        center_x, center_y = pix.width // 2, pix.height // 2
        center_pixel = pix.pixel(center_x, center_y)
        # 检查四个角
        corners = [
            pix.pixel(10, 10),
            pix.pixel(pix.width - 10, 10),
            pix.pixel(10, pix.height - 10),
            pix.pixel(pix.width - 10, pix.height - 10),
        ]
        # 如果所有采样点颜色完全相同（可能是纯白或纯黑），跳过
        if len(set(corners + [center_pixel])) <= 1:
            return False
        return True
    except Exception:
        return True  # 采样失败时当作有效


def score_image(
    page_index: int, width: int, height: int, has_caption: bool = False
) -> float:
    """给图像打分，有 Caption 的优先级更高。"""
    area = width * height
    score = min(area / 100000.0, 10.0)
    if has_caption:
        score += 8.0  # Caption 加分
    if page_index <= 1:
        score -= 1.0  # 首页图像可能是 logo
    return score


def parse_pdf(
    pdf_path: str | Path,
    assets_root: str | Path,
    max_images: int = 8,
    min_image_size: int = 160,
) -> ParsedPaper:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Missing dependency: pymupdf. Install it with `pip install pymupdf`.") from exc

    pdf_path = Path(pdf_path).resolve()
    assets_root = Path(assets_root).resolve()
    paper_stem = safe_stem_for_path(pdf_path)
    paper_assets_dir = assets_root / paper_stem
    paper_assets_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    metadata = {key: str(value or "") for key, value in (doc.metadata or {}).items()}
    year, venue, filename_title = infer_metadata_from_filename(pdf_path)
    title = metadata.get("title") or filename_title

    page_texts: list[str] = []
    candidates: list[tuple[float, int, int, int, int, str]] = []
    seen_xrefs: set[int] = set()
    seen_hashes: set[str] = set()

    # 第一遍：收集所有页面文本并提取全局 Figure/Table 标题
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_text = normalize_text(page.get_text("text", sort=True))
        page_texts.append(page_text)

    full_text = "\n\n".join(page_texts)
    figure_labels = extract_figure_labels_from_text(full_text)

    # 第二遍：抽取图像，并用全局标题关联
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_text = page_texts[page_index] if page_index < len(page_texts) else ""

        for image_info in page.get_images(full=True):
            xref = int(image_info[0])
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            try:
                extracted = doc.extract_image(xref)
                digest = hashlib.sha256(extracted.get("image", b"")).hexdigest()
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)

                pix = fitz.Pixmap(doc, xref)
                width, height = pix.width, pix.height
                
                # 检查图像有效性
                if not is_valid_image(pix):
                    pix = None
                    continue
                pix = None
            except Exception:
                continue

            if width < min_image_size or height < min_image_size:
                continue

            # 查找最接近的 Caption
            caption = find_closest_caption(page_index, figure_labels)
            has_caption = len(caption) > 20  # 有意义的 Caption 长度
            score = score_image(page_index, width, height, has_caption)
            candidates.append((score, xref, page_index + 1, width, height, caption))

    candidates = sorted(candidates, key=lambda item: item[0], reverse=True)[:max_images]
    candidates = sorted(candidates, key=lambda item: (item[2], -item[3] * item[4]))

    figures: list[FigureInfo] = []
    for figure_index, (_, xref, page_number, width, height, context) in enumerate(candidates, start=1):
        out_path = paper_assets_dir / f"figure_{figure_index:02d}.png"
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            pix.save(str(out_path))
            pix = None
        except Exception:
            continue

        figures.append(
            FigureInfo(
                path=str(out_path),
                page=page_number,
                width=width,
                height=height,
                caption=context,
                context=context,
            )
        )

    full_text = normalize_text("\n\n".join(page_texts))
    doc.close()

    return ParsedPaper(
        pdf_path=str(pdf_path),
        stem=paper_stem,
        title=title,
        venue=venue,
        year=year,
        page_count=len(page_texts),
        metadata=metadata,
        full_text=full_text,
        page_texts=page_texts,
        figures=figures,
    )

