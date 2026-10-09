# Introduction

The assembly system allows frames to be "dissaembled" if possible, determining the dissamebly steps for ecah timber in the frame.

The current system only allows singel step dissassemblies as is temporary and gated behind a beta feature setting. It will not be described here.



## Improved disassembly solver notes

Goal: Expand Kumiki’s current disassembly system from simple one-axis separation into a general system capable of planning and visualizing multi-step disassemblies.

Solver requirements:

Basic: Continue supporting existing single step disassembly.
Multi-step motion: Support joints where one motion unlocks another degree of freedom.
Three-piece interlocking “3D plus” Kumiki puzzle, where a piece must first twist before the others can separate. (3 piece burr puzzle https://www.instructables.com/3-Piece-Burr-Puzzle/)
Kanawa Tsugi and similar joints where pieces must first move along one axis and then separate along another.
Stretch goal — complex Kumiki puzzles: Handle highly interlocking assemblies where the available degrees of freedom change continuously based on the positions of multiple pieces. The constraints may effectively be functions of the geometry/state of several interacting timbers and need to be incorporated into the solver.   (do the gordian knot puzzle and a puzzle box example)
Visualization / UX requirements:

Allow timbers to be grouped into disassembly stages, so an assembly can be demonstrated step-by-step.
Support symmetric disassembly. For example, the four sides of a frame should move outward simultaneously at equal speeds/distances rather than arbitrarily moving one at a time.
Ideally symmetry can be auto-discovered.
Users could also explicitly specify symmetry/grouping when necessary.
Once a piece has moved far enough to become unconstrained, continue moving it a little farther to create a visually clean exploded/disassembled view.

you should also be able to manually override any dissably, either becaues yo uwant it solevd in your own way or because it can't besolved or sometihng.
