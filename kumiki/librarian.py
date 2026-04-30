"""
Librarian utilities for dynamically discovering and loading pattern/example modules.

This module scans a folder recursively, imports Python files with error handling,
and extracts module-level `patternbook` and `example` entries (with function-based
fallbacks when those entries are missing).
"""

from dataclasses import dataclass, field
from pathlib import Path
import importlib.util
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

from .patternbook import PatternBook


_DYNAMIC_MODULE_PREFIX = "giraffe_librarian_dynamic"


@dataclass
class LibrarianModuleRecord:
    relative_path: str
    module_name: str
    patternbook: Optional[PatternBook] = None
    example: Optional[Any] = None
    warnings: List[str] = field(default_factory=list)
    load_error: Optional[str] = None
    load_error_traceback: Optional[str] = None


@dataclass
class LibrarianScanResult:
    root_folder: str
    modules: List[LibrarianModuleRecord] = field(default_factory=list)

    @property
    def errors(self) -> List[str]:
        return [
            f"{module.relative_path}: {module.load_error}"
            for module in self.modules
            if module.load_error is not None
        ]

    @property
    def pattern_books(self) -> List[PatternBook]:
        return [
            module.patternbook
            for module in self.modules
            if module.patternbook is not None
        ]

    @property
    def examples(self) -> Dict[str, Any]:
        return {
            module.relative_path: module.example
            for module in self.modules
            if module.example is not None
        }


def _discover_python_files(root_folder: Path) -> List[Path]:
    python_files: List[Path] = []
    for path in sorted(root_folder.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        if "__pycache__" in path.parts:
            continue
        python_files.append(path)
    return python_files


def _make_dynamic_module_name(root_folder: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root_folder).with_suffix("")
    flattened = "_".join(relative.parts)
    return f"{_DYNAMIC_MODULE_PREFIX}_{flattened}"


def _load_module_from_path(root_folder: Path, file_path: Path) -> Tuple[Optional[Any], Optional[str], Optional[str], str]:
    module_name = _make_dynamic_module_name(root_folder, file_path)
    attempted_file = str(file_path)

    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None, f"{attempted_file}: Could not create import spec", None, module_name

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module, None, None, module_name
    except Exception as exc:
        if module_name in sys.modules:
            del sys.modules[module_name]
        tb = traceback.format_exc()
        return None, f"{attempted_file}: {type(exc).__name__}: {exc}", tb, module_name


def _resolve_patternbook(module: Any, warnings: List[str]) -> Optional[PatternBook]:
    if hasattr(module, "patternbook"):
        candidate = getattr(module, "patternbook")
        if isinstance(candidate, PatternBook):
            return candidate
        warnings.append(
            f"module.patternbook exists but is {type(candidate).__name__}, expected PatternBook"
        )

    factory_names = [
        name
        for name in dir(module)
        if name.startswith("create_") and name.endswith("_patternbook")
    ]

    for name in sorted(factory_names):
        factory = getattr(module, name)
        if not callable(factory):
            continue
        try:
            result = factory()
        except Exception as exc:
            warnings.append(f"{name}() failed: {type(exc).__name__}: {exc}")
            continue
        if isinstance(result, PatternBook):
            return result
        warnings.append(f"{name}() returned {type(result).__name__}, expected PatternBook")

    return None


def _resolve_example(module: Any, warnings: List[str]) -> Optional[Any]:
    """Return the module-level ``example`` attribute if present.

    The value may be a concrete object (legacy) **or** a callable that will
    produce the object when invoked (preferred — avoids heavy work at import
    time).  The librarian stores whatever the module provides without calling
    it; callers who need the concrete value should check ``callable()`` and
    invoke it themselves.
    """
    if hasattr(module, "example"):
        return getattr(module, "example")

    if any(
        name.startswith("create_") and not name.endswith("_patternbook")
        for name in dir(module)
    ):
        warnings.append(
            "No module-level example found; skipping example factory execution during scan"
        )

    return None


def scan_library_folder(folder_path: str) -> LibrarianScanResult:
    root_folder = Path(folder_path).resolve()
    if not root_folder.exists() or not root_folder.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")

    result = LibrarianScanResult(root_folder=str(root_folder))
    python_files = _discover_python_files(root_folder)

    for file_path in python_files:
        relative_path = str(file_path.relative_to(root_folder))
        module, load_error, load_error_traceback, module_name = _load_module_from_path(root_folder, file_path)

        record = LibrarianModuleRecord(
            relative_path=relative_path,
            module_name=module_name,
            load_error=load_error,
            load_error_traceback=load_error_traceback,
        )

        if module is not None:
            record.patternbook = _resolve_patternbook(module, record.warnings)
            record.example = _resolve_example(module, record.warnings)

        result.modules.append(record)

    return result


def create_anthology_pattern_book_from_folder(folder_path: str) -> Tuple[PatternBook, LibrarianScanResult]:
    scan_result = scan_library_folder(folder_path)
    if not scan_result.pattern_books:
        raise ValueError(
            "No valid PatternBook objects discovered. "
            f"Import errors: {len(scan_result.errors)}"
        )

    anthology = PatternBook.merge_multiple(scan_result.pattern_books)
    return anthology, scan_result
