<!-- 🤖🤖🤖🤖🤖🤖 -->
# Several tenons on one timber end

The workshop helper `merge_mortise_and_tenon_joints` takes ordinary mortise and tenon joints.
Lay out each tenon with the existing cutters. Give them the same mortise timber, tenon timber end,
and oriented shoulder plane. Set the relief when merging.

```python
parts = [
    cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement,
        tenon_length=mm(45),
        tenon_width_relative_to_joint=mm(16),
        tenon_height_relative_to_joint=mm(24),
        tenon_position=create_v2(x, 0),
        mortise_shoulder_inset=mm(5),
        relief=None,
        inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief,
    )
    for x in (mm(-18), mm(18))
]
joint = merge_mortise_and_tenon_joints(parts, relief=ButtJointNotchReliefConfig())
```

Each tenon can have its own size, tip, mortise depth, pegs and wedges. One shoulder
cut spares all the tenons. Peg holes and wedge kerfs still cut through the retained wood.
The caller lays out any required web of wood between the mortises.
