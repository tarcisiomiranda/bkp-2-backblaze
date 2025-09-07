from typing import List, Optional
from pathlib import Path
import tarfile

from .utils import ensure_parent


def tar_directory(
    source_dir: Path, output_file: Path, exclude_globs: Optional[List[str]] = None
) -> Path:
    ensure_parent(output_file)
    exclude_globs = exclude_globs or []

    def is_excluded(p: Path) -> bool:
        for pat in exclude_globs or []:
            if p.match(pat):
                return True
        return False

    with tarfile.open(output_file, "w:gz") as tar:
        for item in source_dir.rglob("*"):
            if is_excluded(item):
                continue
            tar.add(item, arcname=item.relative_to(source_dir))
    return output_file


def tar_single_file(source_file: Path, output_file: Path) -> Path:
    ensure_parent(output_file)
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(source_file, arcname=source_file.name)
    return output_file
