(function (globalScope) {
    'use strict';
    // The model behind the CSG trees embedded in the layers panel. Pure: no DOM
    // and no viewer state, so jest can cover the parts that are easy to get
    // subtly wrong -- how a payload reshapes into the two views, which node a
    // pick resolves to, and which section a pick should reveal in.
    //
    // The payload comes from runner.serialize_cut_csg_tree:
    //   { kind, label, path, role, jointName, jointId, cutIndex,
    //     features: [...], children: [...] }
    //
    // A timber's CSG appears in two places, both built from this one payload:
    //
    //   by timbers  the rendered CSG as it is
    //   by joints   the same tree narrowed to one cutting, so that cutting can
    //               be read against the timber body it cuts into
    //
    // Neither view rearranges the tree. Every node shows its real children,
    // top tier included, because anything else buries the timber body -- and
    // the body is where the faces you want to reach live.

    /** Roles as the tree displays them, mapped from the payload's roles. */
    function displayRole(role) {
        if (role === 'subtract') {
            return 'cut';
        }
        return role || null;
    }

    /**
     * Split the rendered tree into the timber body and its cuttings.
     *
     * render_timber_with_cuts_csg_local() returns Difference(body, [cuts...]),
     * so the body is the base child. A timber with no cuts has no Difference
     * to unwrap and is its own body.
     */
    function splitBodyAndCuts(root) {
        if (!root) {
            return null;
        }
        const children = root.children || [];
        const base = children.find((child) => child.role === 'base');
        if (root.kind !== 'Difference' || !base) {
            return { body: root, cuts: [] };
        }
        return {
            body: base,
            cuts: children.filter((child) => child.role === 'subtract'),
        };
    }

    /**
     * Row identity. The layers panel keeps one expansion set for every row it
     * shows, so ids carry their context: the same CSG node appears once under
     * its timber and again under its joint, and those must expand separately.
     */
    function nodeId(prefix, indexPath) {
        return prefix + ':' + indexPath.join('.');
    }

    function timberPrefix(timberKey) {
        return 'csg:t:' + timberKey;
    }

    function jointPrefix(jointId, timberKey, cutIndex) {
        return 'csg:j:' + jointId + ':' + timberKey + ':' + cutIndex;
    }

    /** Build a display node and everything under it. */
    function buildNode(payloadNode, prefix, indexPath) {
        const childPayloads = payloadNode.children || [];
        const node = {
            id: nodeId(prefix, indexPath),
            kind: payloadNode.kind,
            displayName: payloadNode.displayName || payloadNode.kind,
            label: payloadNode.label || null,
            path: payloadNode.path || [],
            role: displayRole(payloadNode.role),
            cutIndex: payloadNode.cutIndex === undefined ? null : payloadNode.cutIndex,
            jointId: payloadNode.jointId || null,
            jointName: payloadNode.jointName || null,
            features: payloadNode.features || [],
            children: [],
        };
        node.children = childPayloads.map((child, index) => (
            buildNode(child, prefix, indexPath.concat(index))
        ));
        return node;
    }

    /**
     * The by-timbers tree: the rendered CSG exactly as it is.
     *
     * Nothing is reshaped at the top. The root is the Difference the timber
     * renders as -- base and cuts as ordinary children -- or the body itself
     * when the timber has no cuts. Hanging the cuts off the body instead
     * would read more directly, but it buries the body's own structure under
     * the things subtracted from it, and the body is exactly where the faces
     * you want to reach live.
     */
    function timberTree(payload, timberKey) {
        const root = payload && payload.tree;
        if (!root) {
            return null;
        }
        return buildNode(root, timberPrefix(timberKey), [0]);
    }

    /**
     * The by-joints tree: the timber as this one cutting alone would leave it.
     *
     * Literally Difference(body, [thisCut]) -- a real sub-CSG of the rendered
     * tree, not a display arrangement -- so the cutting can be read against
     * the body it cuts into. A timber with no cuts is just its body.
     */
    function jointCuttingTree(payload, timberKey, jointId, cutIndex) {
        const root = payload && payload.tree;
        if (!root) {
            return null;
        }
        const prefix = jointPrefix(jointId, timberKey, cutIndex);
        const split = splitBodyAndCuts(root);
        const cut = split.cuts.filter((child) => child.cutIndex === cutIndex);
        if (!cut.length) {
            return buildNode(split.body, prefix, [0]);
        }
        const justThisCut = Object.assign({}, root, {
            children: [split.body].concat(cut),
        });
        return buildNode(justThisCut, prefix, [0]);
    }

    /**
     * Flatten a display tree into render-ready rows, honouring expansion.
     * Children of a collapsed node are omitted rather than hidden, so the row
     * count tracks what is actually on screen.
     */
    function flatten(root, expandedIds) {
        const expanded = expandedIds instanceof Set ? expandedIds : new Set(expandedIds || []);
        const rows = [];

        function walk(node, depth) {
            if (!node) {
                return;
            }
            const children = node.children || [];
            const isExpanded = expanded.has(node.id);
            rows.push({
                id: node.id,
                depth,
                kind: node.kind,
                displayName: node.displayName,
                label: node.label,
                role: node.role,
                path: node.path,
                cutIndex: node.cutIndex,
                jointId: node.jointId,
                jointName: node.jointName,
                features: node.features,
                hasChildren: children.length > 0,
                expanded: isExpanded,
            });
            if (!isExpanded) {
                return;
            }
            for (const child of children) {
                walk(child, depth + 1);
            }
        }

        walk(root, 0);
        return rows;
    }

    /**
     * The shallowest node whose CSG path matches `path` exactly.
     *
     * Shallowest, because untagged nodes inherit their parent's path: around a
     * tenon the labelled SolidUnion, the untagged Difference under it and the
     * untagged HalfSpace beside that all carry ['mortise_and_tenon']. The node
     * that *owns* the label is the shallowest of those, and it is also what
     * find_csg_by_path resolves to -- so the list selection and the 3D
     * highlight agree on which node was picked. Returns null when nothing
     * matches.
     *
     * Works on a payload tree or a display tree; both carry path + children.
     */
    function findByPath(root, path) {
        const wanted = (path || []).join(' ');
        let found = null;

        function walk(node) {
            if (!node || found) {
                return;
            }
            if ((node.path || []).join(' ') === wanted) {
                found = node;
                return;
            }
            for (const child of node.children || []) {
                walk(child);
            }
        }

        walk(root);
        return found;
    }

    /** Which cutting a resolved pick path belongs to; null for the timber body. */
    function cutIndexForPath(payload, path) {
        const node = findByPath(payload && payload.tree, path);
        if (!node || node.cutIndex === undefined) {
            return null;
        }
        return node.cutIndex;
    }

    /** Every id from the display root down to and including the node at `id`. */
    function ancestorIds(root, id) {
        let chain = null;

        function walk(node, trail) {
            if (!node || chain) {
                return;
            }
            const here = trail.concat(node.id);
            if (node.id === id) {
                chain = here;
                return;
            }
            for (const child of node.children || []) {
                walk(child, here);
            }
        }

        walk(root, []);
        return chain || [];
    }

    /**
     * Which section a viewer pick should reveal itself in.
     *
     * The by-timbers section, unless the current focus is already in a joint
     * section tree that contains what was just picked. That tree holds exactly
     * the body and one cutting, so "contains" means the pick landed on that
     * cutting or on the body -- staying put beats yanking the user across to
     * the other section for a node already on screen.
     */
    function revealTarget(focus, pick) {
        const context = focus && focus.context;
        const sameTimber = Boolean(context)
            && context.section === 'joints'
            && focus.timberKey === pick.timberKey;
        const onBody = pick.cutIndex === null || pick.cutIndex === undefined;
        if (sameTimber && (onBody || pick.cutIndex === context.cutIndex)) {
            return {
                section: 'joints',
                jointId: context.jointId,
                cutIndex: context.cutIndex,
                timberKey: pick.timberKey,
            };
        }
        return { section: 'timbers', timberKey: pick.timberKey };
    }

    /**
     * How to describe what a selection landed on: the tail of the breadcrumb.
     *
     * A pick that resolved to a feature names it by kind -- face, edge, point.
     * A pick that selected a node whole says what that node *is* instead: an
     * ordinary click descends one level at a time, so it selects unions and
     * differences on the way down, and the highlight lights the whole of them.
     * Calling every one of those a "face" contradicted what was on screen.
     *
     * `nouns` maps a feature type to its display word, so the wording can be
     * translated without this having to know about i18n.
     */
    function describePickTail(pick, nouns) {
        if (!pick) {
            return null;
        }
        if (pick.featureLabel) {
            const noun = (nouns && nouns[pick.featureType]) || 'feature';
            return noun + ' (' + pick.featureLabel + ')';
        }
        const kind = pick.nodeDisplayName || pick.nodeKind;
        if (!kind) {
            return null;
        }
        return pick.nodeLabel ? kind + ' (' + pick.nodeLabel + ')' : kind;
    }

    /**
     * The breadcrumb for a selection: the timber, the labelled nodes above
     * what was selected, then what was selected.
     *
     * `path` is the chain of labels down to the selected node, so it already
     * ends with that node's own label. Left in, the node appears twice -- once
     * as a path segment and again as its kind -- reading as two levels when it
     * is one, and making a node look like it vanished when the next click down
     * replaced its kind with a deeper label. So the trailing duplicate is
     * dropped and the label folded into the description instead.
     *
     * Not dropped when a feature is selected: the node is then a real ancestor
     * of the thing picked, and popping it would lose it from the trail.
     */
    function breadcrumbSegments(timberName, path, pick, nouns) {
        const trail = (path || []).slice();
        const selectedTheNodeItself = Boolean(pick) && !pick.featureLabel && Boolean(pick.nodeLabel);
        if (selectedTheNodeItself && trail.length && trail[trail.length - 1] === pick.nodeLabel) {
            trail.pop();
        }
        const segments = timberName ? [timberName] : [];
        segments.push(...trail);
        const tail = describePickTail(pick, nouns);
        if (tail) {
            segments.push(tail);
        }
        return segments;
    }

    /** Row text: the base type, plus the tag it was given. */
    function describeNode(node) {
        if (!node) {
            return '';
        }
        const kind = node.displayName || node.kind;
        if (node.label) {
            return kind + ' · ' + node.label;
        }
        return kind;
    }

    const CsgTreeView = {
        splitBodyAndCuts,
        nodeId,
        timberPrefix,
        jointPrefix,
        timberTree,
        jointCuttingTree,
        flatten,
        findByPath,
        cutIndexForPath,
        ancestorIds,
        revealTarget,
        describeNode,
        describePickTail,
        breadcrumbSegments,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { CsgTreeView };
    }
    globalScope.CsgTreeView = CsgTreeView;
})(typeof window !== 'undefined' ? window : globalThis);
