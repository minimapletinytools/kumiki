"""Names shown to people, in one language or several.

A name is a string (English) or a ``{language: text}`` dict, e.g.
``{"en": "Corner joints", "ja": "隅の仕口"}``. Kigumi shows the viewer's language,
else English, else the path or file name.

A pattern book names its pattern folders with :func:`pattern_folders`; a file names
itself in the sidebar with a literal ``__title__ = ...`` at the top level.
"""

import sys
from typing import Any, Dict, Mapping, Union

__all__ = ["Names", "pattern_folders"]

Names = Union[str, Mapping[str, str]]

# Where pattern_folders keeps a module's folder names.
FOLDERS_ATTRIBUTE = "__kumiki_pattern_folders__"


def names_of(value: Names, what: str) -> Dict[str, str]:
    """Return `value` as ``{language: text}``.

    Raise TypeError, naming `what`, if it is not a string or a dict of language to non-empty text.
    """
    if isinstance(value, str):
        value = {"en": value}
    if not isinstance(value, Mapping) or not value:
        raise TypeError(f"{what} must be a string or a {{language: name}} dict, "
                        f"e.g. {{'en': 'Corner joints', 'ja': '隅の仕口'}}; got {value!r}")
    for language, text in value.items():
        if not isinstance(language, str) or not isinstance(text, str) or not text.strip():
            raise TypeError(f"{what}: each name must be non-empty text under a language code; got {language!r}: {text!r}")
    return dict(value)


def pattern_folders(folders: Mapping[str, Names]) -> None:
    """Name the pattern folders of the module that calls it: ``{folder path: name}``.

    A folder path is a pattern path's leading segments, e.g. "basic_joints/mortise_and_tenon".
    Calling it again adds to the names already given.
    """
    if not isinstance(folders, Mapping):
        raise TypeError(f"pattern_folders takes a {{folder path: name}} dict, not {type(folders).__name__}")
    module_globals = sys._getframe(1).f_globals
    named = dict(module_globals.get(FOLDERS_ATTRIBUTE, {}))
    for path, names in folders.items():
        if not isinstance(path, str) or not path.strip("/"):
            raise TypeError(f"pattern_folders: a folder path must be text like 'corner_joints', got {path!r}")
        named[path.strip("/")] = names_of(names, f"pattern folder {path!r}")
    module_globals[FOLDERS_ATTRIBUTE] = named


def module_folder_names(module: Any) -> Dict[str, Dict[str, str]]:
    """Return the folder names `module` gave with pattern_folders."""
    return dict(getattr(module, FOLDERS_ATTRIBUTE, None) or {})
