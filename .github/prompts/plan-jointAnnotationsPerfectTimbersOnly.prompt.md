## Plan: Joint Annotation Rollout

Add a function-level joint annotation marker for perfect-timber-only support, defined in timber.py, then apply it to all core cut_* joint implementations in workshop modules (excluding cut_basic_* wrappers and alias-only exports). This keeps semantics explicit at the API layer while minimizing noise in wrapper APIs.

**Steps**
1. Define annotation primitives in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/timber.py.
2. Add an annotation utility in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/timber.py for function-level tagging.
3. Apply the annotation to all core cutter functions in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/plain_joints.py.
4. Apply the annotation to all core cutter functions in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/mortise_and_tenon_joint.py.
5. Apply the annotation to all core cutter functions in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/japanese_joints.py.
6. Apply the annotation to all core cutter functions in /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/double_butt_joints.py.
7. Add focused tests in /Users/peter.lu/kitchen/faucet/kumiki/tests/ to validate the annotation is present on the intended functions.
8. Run verification: type-check and full test suite.

**Relevant files**
- /Users/peter.lu/kitchen/faucet/kumiki/kumiki/timber.py — add annotation type(s) and function decorator/attribute helper.
- /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/plain_joints.py — annotate core plain-joint cutters including deprecated core cutters if still part of core API surface.
- /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/mortise_and_tenon_joint.py — annotate mortise-and-tenon core cutters.
- /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/japanese_joints.py — annotate Japanese core cutters.
- /Users/peter.lu/kitchen/faucet/kumiki/kumiki/joints/workshop/double_butt_joints.py — annotate implemented core double-butt cutters; do not annotate NotImplemented stubs unless requested.
- /Users/peter.lu/kitchen/faucet/kumiki/tests/ — add tests asserting annotation coverage for targeted functions.

**Verification**
1. Run source .venv/bin/activate.
2. Run uv run ty check.
3. Run python3 -m pytest tests/ -v.
4. Confirm all intended core cut_* functions have the annotation and cut_basic_* wrappers remain unannotated.

**Decisions**
- Annotation location: on joint functions (decorator/attribute), not on Joint return objects.
- Scope for this pass: only core cut_* implementations in workshop modules.
- Excluded from this pass: cut_basic_* wrappers and compatibility alias names.

**Further Considerations**
1. Decide whether deprecated core functions (for example _DEPRECATED cutters in plain_joints.py) should be annotated for consistency or left unannotated to discourage usage; recommended: annotate if they are still callable and return Joint.
2. Decide whether NotImplemented core stubs (for example cut_castle_joint) should predeclare annotation now; recommended: skip until implemented to avoid implying real support.
3. Decide annotation data shape: boolean marker versus structured metadata object; recommended: structured metadata to enable future flags beyond perfect-timber-only.