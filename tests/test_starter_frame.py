"""The frame kigumi writes into every new project has to build.

kigumi keeps a copy of it in project-initializer.js, and a kigumi unit test
holds that copy to this file.
"""

import runpy
from pathlib import Path

from kumiki.triangles import triangulate_cutcsg

STARTER_FRAME = Path(__file__).resolve().parent.parent / "patterns" / "structures" / "my_cute_frame.py"


def test_starter_frame_builds_and_meshes():
    frame = runpy.run_path(str(STARTER_FRAME))["build_frame"]()

    assert frame.name == "My Cute Frame"
    assert len(frame.cut_timbers) == 4
    for cut_timber in frame.cut_timbers:
        assert triangulate_cutcsg(cut_timber.render_timber_with_cuts_csg_local()) is not None
