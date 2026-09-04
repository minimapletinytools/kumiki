"""What a frame asks to have drawn.

A drawing names itself and the timbers it is of, and never a layout: where the
views go on the page, which way their cameras face and at what scale are worked
out from the timbers themselves. So a frame says what it wants drawn and never
how to draw it, and the same drawing is as right on a small sheet as on a large
one.

Measurements hang off the viewport they are drawn in, because a drawing is a
projection and a dimension only means anything in the plane it is projected
onto. The same two features measured in the front elevation and in the plan view
are two dimensions with two numbers, and either may be meaningless while the
other is fine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple

from .identity import DrawingId, FeaturePath, MeasurementId, TimberPath


# TODO we will turn this enum into a bit more complicated of a class
class MeasurementFeature(Enum):
    AREA = 2
    LINE = 1
    POINT = 0


# the type of measurement, including projected to a 2d drawing viewport and full 3d cases.
class MeasurementKind(Enum):
    """What a dimension is measuring.

    A pair of features may admit more than one measurement kind
    A measurement may be interpreted in 3d or projectd to a 2d drawing

    A 2d drawing is a projection

        feature   projects to   when
        -------   -----------   ----------------------------------------------
        point     point         always
        edge      point         its direction runs along the line of sight
        edge      line          otherwise
        face      line          its normal is square to the line of sight,
                                which is to say the face is seen edge-on
        face      area          otherwise

    projects pairs admit the following measurements

        projected pair            admits
        ----------------------    ----------------------------------------
        point, point              PERPENDICULAR, HORIZONTAL, VERTICAL
        point, line               PERPENDICULAR (HORIZONTAL, VERTICAL  technically allowed but not used in practice)
        line, line (parallel)     PERPENDICULAR (HORIZONTAL, VERTICAL  technically allowed but not used in practice)
        line, line (crossing)     ANGLE
        anything, area            nothing
        coincident or degenerate  nothing

    in 3D we admit additional measurements:

    TODO finish

    TODO Worth adding later, and listed here so the shape leaves room for them:
    RADIUS and DIAMETER of a circular feature, once features name one; ARC
    LENGTH; a distance ALONG a named direction rather than the sheet's -- along
    the piece, say, which is the same as HORIZONTAL in a face view but not in a
    plan; and chains and baselines, which are several measurements sharing a
    reference rather than a kind of their own.
    """
        
    # requires 2 features to not be parallel (points are parallel to nothing so neither can be a point
    ANGLE
    PROJECTED_ANGLE

    # requires 2 features to be parallel (or one of them to be a point)
    PERENDICULAR_DISTANCE
    PROJECTED_PERPENDICULAR_DISTANCE
    PROJECTED_HORIZONTAL_DISTANCE
    PROJECTED_VERTICAL_DISTANCE

class MeasurementKindDebugInformation:
    original_feature_A: MeasurementFeature
    original_feature_B: MeasurementFeature

    projected_feature_A: MeasurementFeature
    projected_feature_B: MeasurementFeature

    mesaurement_kind: MeasurementKind

    def measurement_kind_name(self) -> string:
        # starts with feature_to_feature
        # or "projected_feature" for each feature that's projected
        # then we have measurement kind at the end

# TODO DELETE-RELPACE this class with the above
class MeasureKind(Enum):
    """What a dimension is measuring.

    A pair of features usually admits more than one, and which is wanted cannot
    be inferred: two points admit the direct distance and either component along
    the sheet, and the same two edge-on faces give a separation when they are
    parallel and an angle when they are not. So a measurement says which it is.

    Which apply is decided by what the two features *project to* in the
    viewport, not by what they are. A drawing is a projection, so that is the
    only thing the sheet can carry:

        feature   projects to   when
        -------   -----------   ----------------------------------------------
        point     point         always
        edge      point         its direction runs along the line of sight
        edge      line          otherwise
        face      line          its normal is square to the line of sight,
                                which is to say the face is seen edge-on
        face      area          otherwise

    Then by projected pair:

        projected pair            admits
        ----------------------    ----------------------------------------
        point, point              ALIGNED, HORIZONTAL, VERTICAL
        point, line               PERPENDICULAR
        line, line (parallel)     PERPENDICULAR, HORIZONTAL, VERTICAL
        line, line (crossing)     ANGLE
        anything, area            nothing
        coincident or degenerate  nothing

    Worth adding later, and listed here so the shape leaves room for them:
    RADIUS and DIAMETER of a circular feature, once features name one; ARC
    LENGTH; a distance ALONG a named direction rather than the sheet's -- along
    the piece, say, which is the same as HORIZONTAL in a face view but not in a
    plan; and chains and baselines, which are several measurements sharing a
    reference rather than a kind of their own.
    """

    # TODO prefix these ones with POINT_TO_POINT
    #: The direct distance between two projected points.   TODO rename to direct
    ALIGNED = "aligned"
    #: point to point component across the sheet.
    HORIZONTAL = "horizontal"
    #: point to point component up the sheet.
    VERTICAL = "vertical"

    # TODO are these really necessary? I think it's nice becasue we have an enum to describe the measurement kind, but it's not actually useful for setting the kind as they are not compatible
    #: Point to line, or between two parallel lines.
    PERPENDICULAR = "perpendicular"
    #: Between two lines that are not parallel. 
    ANGLE = "angle"


@dataclass(frozen=True)
class Measure:
    """A dimension between two features, drawn in one viewport.

    TODO identity should include kind as well
    TODO should we enforce canonical ordering on anchor_a / anchor_b, we can create a new class CanonicalFeaturePathPair or something
    Identity is the anchors, plus `measure_id` when the same pair is measured
    more than once in the same viewport -- deliberately not a position in a
    list, so that a measurement generated by an algorithm keeps whatever the
    drawings file has said about it when the algorithm next runs and emits a
    different number of them. It is scoped to the viewport, since that is where
    a measurement lives.
    """

    anchor_a: FeaturePath
    anchor_b: FeaturePath
    # the measurement kind to use or None to use the default
    kind: Optional[MeasureKind] = None
    # the measurementId which allows multiple measurements with the same anchors and kind
    measure_id: Optional[MeasurementId] = None

    def __post_init__(self):
        if isinstance(self.measure_id, str):
            object.__setattr__(self, 'measure_id', MeasurementId(self.measure_id))
        if isinstance(self.kind, str):
            object.__setattr__(self, 'kind', MeasureKind(self.kind))

    def identity(self) -> Tuple[Tuple, Tuple, str]:
        """What makes this measurement itself, within its viewport.

        The anchors unordered, since measuring A to B is measuring B to A.
        """
        first, second = sorted((self.anchor_a.identity(), self.anchor_b.identity()))
        return (first, second, str(self.measure_id or ""))


@dataclass(frozen=True)
class Drawing:
    """A drawing the frame asks for: a name, and which timbers it is of.

    Timbers are named by path, the same name they carry everywhere else, and by
    path alone -- which of two timbers sharing a path is not a question a name
    can answer, and a drawing of "the front left post" should not have to know
    whether one was made twice. A path naming no timber is not an error either:
    a drawing of a timber a later edit removed is worth keeping and showing as
    empty, rather than failing to raise the frame it belongs to.

    `drawing_id` is what an override in the drawings file names, so it has to
    survive editing the code around it. It defaults to the name, which is stable
    as long as the name is.
    """

    name: str
    timber_paths: Tuple[TimberPath, ...] = ()
    drawing_id: Optional[DrawingId] = None
    # Dimensions the frame asks for, under the viewport each is drawn in --
    # 'front', 'top', 'left' and so on, the viewports the layout produces.
    # Written out by hand today; expected to be mostly generated by algorithm
    # later, which is what the identity rules on Measure are for.
    measurements: Mapping[str, Tuple[Measure, ...]] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'timber_paths', tuple(
            TimberPath(path) if isinstance(path, str) else path
            for path in (self.timber_paths or ())
        ))
        if not self.drawing_id:
            object.__setattr__(self, 'drawing_id', DrawingId(self.name))
        elif isinstance(self.drawing_id, str):
            object.__setattr__(self, 'drawing_id', DrawingId(self.drawing_id))
        object.__setattr__(self, 'measurements', {
            str(viewport): tuple(measures)
            for viewport, measures in dict(self.measurements or {}).items()
        })
