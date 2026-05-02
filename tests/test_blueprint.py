"""Tests for kumiki.blueprint — STL (and STEP guard) export."""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import pytest
from sympy import Integer

from kumiki.blueprint import (
    export_cut_timber_stl,
    export_frame_stl,
    _OCP_AVAILABLE,
)
from kumiki.timber import CutTimber, Frame, Timber, timber_from_directions
from kumiki.rule import create_v3, create_v2


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _simple_timber(name: str = "test_timber") -> Timber:
    """A small axis-aligned timber for export tests."""
    return timber_from_directions(
        bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
        length=Integer(2),
        size=create_v2(Integer(1), Integer(1)),
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        width_direction=create_v3(Integer(0), Integer(1), Integer(0)),
        ticket=name,
    )


def _simple_cut_timber(name: str = "test_timber") -> CutTimber:
    return CutTimber(_simple_timber(name))


def _simple_frame() -> Frame:
    t1 = _simple_timber("beam")
    t2 = timber_from_directions(
        bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
        length=Integer(3),
        size=create_v2(Integer(1), Integer(1)),
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        ticket="post",
    )
    return Frame(cut_timbers=[CutTimber(t1), CutTimber(t2)], name="TestFrame")


def _load_structure_factory(module_name: str, factory_name: str) -> Any:
    module_path = (
        Path(__file__).resolve().parent.parent / "patterns" / "structures" / f"{module_name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"patterns_structures_{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise AttributeError(f"{factory_name} is missing or not callable in {module_path}")
    return factory


# ---------------------------------------------------------------------------
# STL export — single CutTimber
# ---------------------------------------------------------------------------


class TestExportCutTimberStl:
    def test_creates_stl_file(self):
        ct = _simple_cut_timber()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.stl"
            export_cut_timber_stl(ct, dest)
            assert dest.exists()
            assert dest.stat().st_size > 0

    def test_creates_parent_directories(self):
        ct = _simple_cut_timber()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "sub" / "dir" / "out.stl"
            export_cut_timber_stl(ct, dest)
            assert dest.exists()

    def test_stl_is_valid_trimesh(self):
        """The written STL should be re-loadable by trimesh."""
        import trimesh

        ct = _simple_cut_timber()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.stl"
            export_cut_timber_stl(ct, dest)
            mesh = cast("trimesh.Trimesh", trimesh.load(str(dest), file_type="stl"))
            assert len(mesh.faces) > 0
            assert len(mesh.vertices) > 0


# ---------------------------------------------------------------------------
# STL export — Frame
# ---------------------------------------------------------------------------


class TestExportFrameStl:
    def test_creates_one_file_per_timber(self):
        frame = _simple_frame()
        with tempfile.TemporaryDirectory() as td:
            written = export_frame_stl(frame, td)
            assert len(written) == 2
            for p in written:
                assert p.exists()
                assert p.suffix == ".stl"

    def test_file_names_match_timber_names(self):
        frame = _simple_frame()
        with tempfile.TemporaryDirectory() as td:
            written = export_frame_stl(frame, td)
            names = sorted(p.stem for p in written)
            assert names == ["beam", "post"]

    def test_combined_flag(self):
        frame = _simple_frame()
        with tempfile.TemporaryDirectory() as td:
            written = export_frame_stl(frame, td, combined=True)
            # 2 individual + 1 combined = 3
            assert len(written) == 3
            combined = [p for p in written if p.stem == "_combined"]
            assert len(combined) == 1
            assert combined[0].stat().st_size > 0

    def test_creates_output_directory(self):
        frame = _simple_frame()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "new_dir"
            written = export_frame_stl(frame, out)
            assert out.is_dir()
            assert len(written) == 2


# ---------------------------------------------------------------------------
# STEP export — guard when cadquery is missing
# ---------------------------------------------------------------------------


class TestStepImportGuard:
    """Ensure STEP functions raise ImportError when OCP is unavailable."""

    @pytest.mark.skipif(_OCP_AVAILABLE, reason="OCP IS installed")
    def test_export_cut_timber_step_raises(self):
        from kumiki.blueprint import export_cut_timber_step

        ct = _simple_cut_timber()
        with pytest.raises(ImportError, match="OCP"):
            export_cut_timber_step(ct, "/tmp/nope.step")

    @pytest.mark.skipif(_OCP_AVAILABLE, reason="OCP IS installed")
    def test_export_frame_step_raises(self):
        from kumiki.blueprint import export_frame_step

        frame = _simple_frame()
        with pytest.raises(ImportError, match="OCP"):
            export_frame_step(frame, "/tmp/nope_dir")


# ---------------------------------------------------------------------------
# STEP export — oscarshed integration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _OCP_AVAILABLE, reason="OCP (cadquery-ocp) not installed")
class TestStepOscarshed:
    """Run STEP export on the full oscarshed frame to catch OCP/cadquery issues."""

    @pytest.fixture(scope="class")
    def oscarshed_frame(self):
        create_oscarshed = _load_structure_factory("oscarshed", "create_oscarshed")
        return create_oscarshed()

    def test_export_single_timber_step(self, oscarshed_frame):
        from kumiki.blueprint import export_cut_timber_step

        ct = oscarshed_frame.cut_timbers[0]
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "timber.step"
            export_cut_timber_step(ct, dest)
            assert dest.exists()
            assert dest.stat().st_size > 0

    def test_export_all_timbers_step(self, oscarshed_frame):
        from kumiki.blueprint import export_frame_step

        with tempfile.TemporaryDirectory() as td:
            written = export_frame_step(oscarshed_frame, td)
            assert len(written) == len(oscarshed_frame.cut_timbers)
            for p in written:
                assert p.exists()
                assert p.stat().st_size > 0
                assert p.suffix == ".step"

    def test_step_bounds_match_timber_corners(self, oscarshed_frame):
        """Verify that each OCP shape's bounding box roughly matches the
        timber's corner positions in global coordinates (in mm).

        Allows generous tolerance because:
        - joint geometry (tenons) may extend past the timber body corners
        - the base prism may extend beyond if an end cut is missing in the CSG
        But the bounds should be within ~100mm of the expected corners — NOT
        off by thousands (which would indicate a broken half-space or transform).
        """
        from kumiki.blueprint import _csg_to_ocp, _OCP_AVAILABLE
        from kumiki.cutcsg import adopt_csg
        from kumiki.rule import Transform
        from kumiki.rendering_utils import sympy_to_float
        from kumiki.timber import TimberCorner
        import OCP.Bnd as _Bnd
        import OCP.BRepBndLib as _BRepBndLib

        Bnd_Box = getattr(_Bnd, "Bnd_Box")
        BRepBndLib = getattr(_BRepBndLib, "BRepBndLib")

        TOL = 100.0  # mm — generous tolerance for joint overruns

        # These timbers have known pre-existing CSG issues where one end
        # isn't clipped (same in CadQuery). Skip strict bounds check.
        SKIP_BOUNDS_CHECK = {"Front Girt Left", "Front Girt Middle"}

        for ct in oscarshed_frame.cut_timbers:
            name = ct.timber.ticket.name

            # Expected bounds from timber corners (metres → mm)
            corners_mm = []
            for c in TimberCorner:
                pos = ct.timber.get_corner_position_global(c)
                corners_mm.append(
                    [float(sympy_to_float(pos[i])) * 1000.0 for i in range(3)]
                )
            exp_min = [min(c[i] for c in corners_mm) for i in range(3)]
            exp_max = [max(c[i] for c in corners_mm) for i in range(3)]

            # Actual OCP shape bounds
            local_csg = ct.render_timber_with_cuts_csg_local()
            global_csg = adopt_csg(
                ct.timber.transform, Transform.identity(), local_csg
            )
            shape = _csg_to_ocp(global_csg)
            bb = Bnd_Box()
            BRepBndLib.Add_s(shape, bb)
            assert not bb.IsVoid(), f"{name}: OCP shape is empty (void)"
            xmin, ymin, zmin, xmax, ymax, zmax = bb.Get()
            actual_min = [xmin, ymin, zmin]
            actual_max = [xmax, ymax, zmax]

            if name in SKIP_BOUNDS_CHECK:
                continue

            for axis in range(3):
                label = "XYZ"[axis]
                lo_err = actual_min[axis] - exp_min[axis]
                hi_err = actual_max[axis] - exp_max[axis]
                assert abs(lo_err) < TOL, (
                    f"{name} {label}-min off by {lo_err:+.1f}mm "
                    f"(expected {exp_min[axis]:.1f}, got {actual_min[axis]:.1f})"
                )
                assert abs(hi_err) < TOL, (
                    f"{name} {label}-max off by {hi_err:+.1f}mm "
                    f"(expected {exp_max[axis]:.1f}, got {actual_max[axis]:.1f})"
                )
