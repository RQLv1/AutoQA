from pathlib import Path
import importlib.util
import sys


def _resolve_pdf_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    data_pdf_dir = repo_root / "data" / "pdf"

    if len(sys.argv) > 1 and sys.argv[1].strip():
        raw_input = sys.argv[1].strip()
        candidate = Path(raw_input).expanduser()
        if candidate.is_absolute() or candidate.exists():
            return candidate
        data_pdf_candidate = data_pdf_dir / raw_input
        return data_pdf_candidate

    pdf_files = sorted(data_pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {data_pdf_dir}")
    if len(pdf_files) == 1:
        return pdf_files[0]
    pdf_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    chosen = pdf_files[0]
    print(f"Multiple PDFs found, using newest: {chosen}")
    return chosen


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_modules(pdf_path: Path) -> tuple[Path, object, object]:
    base_dir = Path(__file__).parent
    repo_root = base_dir.parent
    pdf2txt_module = _load_module("pdf2txt_module", base_dir / "pdf2txt.py")
    assemble_module = _load_module("assemble_module", base_dir / "assemble.py")
    output_dir = repo_root / "output" / pdf_path.stem
    images_dir = output_dir / "images"

    pdf2txt_module.PDF_PATH = pdf_path
    pdf2txt_module.OUTPUT_DIR = output_dir
    pdf2txt_module.TEXT_PATH = output_dir / "extracted.txt"
    pdf2txt_module.IMAGES_DIR = images_dir

    assemble_module.PDF_PATH = pdf_path
    assemble_module.OUTPUT_DIR = output_dir
    assemble_module.IMAGES_DIR = images_dir

    return output_dir, pdf2txt_module, assemble_module


def _cleanup_output(output_dir: Path, images_dir: Path, text_path: Path) -> None:
    if not output_dir.exists():
        return
    keep_images_dir = images_dir.resolve()
    keep_text = text_path.resolve()
    for path in output_dir.iterdir():
        resolved = path.resolve()
        if resolved == keep_images_dir or resolved == keep_text:
            continue
        if keep_images_dir in resolved.parents:
            continue
        if path.is_dir():
            for sub in path.rglob("*"):
                sub_path = sub.resolve()
                if keep_images_dir in sub_path.parents:
                    continue
                if sub.is_file():
                    sub.unlink()
            for sub in sorted(path.rglob("*"), reverse=True):
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass
            try:
                path.rmdir()
            except OSError:
                pass
        else:
            path.unlink()


def main() -> None:
    pdf_path = _resolve_pdf_path()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    output_dir, pdf2txt_module, assemble_module = _configure_modules(pdf_path)
    print(f"Output dir: {output_dir}")

    pdf2txt_module.main()
    assemble_module.main()
    _cleanup_output(output_dir, pdf2txt_module.IMAGES_DIR, pdf2txt_module.TEXT_PATH)


if __name__ == "__main__":
    main()
