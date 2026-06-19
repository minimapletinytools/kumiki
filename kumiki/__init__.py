"""
Kumiki - Timber framing CAD system
Based on the API specification in morenotes.md

This is the main entry point that imports and re-exports all kumiki functionality.
"""

__version__ = "0.2.8"

# Import everything from the organized modules
from .rule import *
from .cutcsg import *
from .timber import *
from .footprint import *
from .construction import *
from .joints.workshop.shavings import *
from .joints.workshop.plain_joints import *
from .joints.workshop.basic_joints import *
from .joints.workshop.mortise_and_tenon_joint import *
from .joints.workshop.japanese_joints import *
from .joints.workshop.double_butt_joints import *
from .measuring import *
from .patternbook import *
from .librarian import Param

# Optional heavy mesh/export modules.
# FreeCAD's bundled Python may not have trimesh installed; keep base imports usable.
try:
    from .triangles import *
except ModuleNotFoundError as exc:
    if exc.name != "trimesh":
        raise

try:
    from .blueprint import *
except ModuleNotFoundError as exc:
    if exc.name != "trimesh":
        raise

# Explicitly import private helper functions that are used by tests
# These start with _ so they won't be included in "import *" by default
from .timber import (
    _create_timber_prism_csg_local
)
