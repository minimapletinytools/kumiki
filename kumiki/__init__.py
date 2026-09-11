"""
Kumiki - Timber framing CAD system
Based on the API specification in morenotes.md

This is the main entry point that imports and re-exports all kumiki functionality.
"""

__version__ = "0.6.0"

# Import everything from the organized modules
from .rule import *
from .cutcsg import *
from .ticket import (
    AccessoryTicket,
    BoardTicket,
    GenericTag,
    JointTicket,
    Member,
    MemberTag,
    SliceTag,
    Ticket,
    TimberTag,
    TimberTicket,
    as_timber_tag,
    normalize_timber_tags,
)
from .identity import (
    DerivedFeaturePath,
    DrawingId,
    FeaturePath,
    FeatureRef,
    Identifier,
    MeasurementId,
    ResolvedTimberPath,
    SingleFeaturePath,
    TimberPath,
    ViewportId,
)
from .layout import PlacedViewport, resolve_drawing, resolve_viewports
from .drawing import (Drawing, ELEVATION_IDS, Length, Page, Portion, Share,
                      SHOP_DRAWING_IDS, SplitDirection, Subdivision, Viewport,
                      columns, covering_page, default_viewports_for,
                      elevation_viewports, rows, shop_drawing_viewports,
                      Measure, MeasurementDirection, MeasurementFeature,
                      MeasurementKind, MeasurementOperation, MeasurementPlacement,
                      MeasurementSpace, kinds_for)
from .timber import *
from .footprint import *
from .construction import *
from .pathcsg import *
from .joints.workshop.shavings import *
from .joints.workshop.butt import *
from .joints.workshop.corner import *
from .joints.workshop.cross import *
from .joints.workshop.splice import *
from .joints.workshop.board import *
from .joints.workshop.decorative import *
from .joints.workshop.free import *
from .joints.workshop.mixed import *
from .joints.workshop.basic_joints import *
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
