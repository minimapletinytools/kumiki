/**
 * What a click picked, and how members, highlights and measurement ends look for the selection.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { CSG_HIGHLIGHT_EDGE_WIDTH_PX, CSG_HIGHLIGHT_POINT_SIZE_PX, CsgTreeView, DRAWING_CONTEXT_OPACITY, KigumiMeasurements, SelectionVisuals, computeSelectionVisualContext, csgFocusKey, describeCandidates, edgeSegmentPositions, heldHighlightKey, selectionVisualPolicy, vscode } from './viewer-shared.js';
import * as KigumiFeatureStates from './feature-states.js';
import * as KigumiHighlights from './highlights.js';
import * as KigumiHover from './hover-state.js';
import * as KigumiMemberStates from './member-states.js';

export const SelectionVisualsMixin = (Base) => class extends Base {
    handleCSGSelectionResult(message) {
        // While measuring, a click the hover showed as refused does nothing but say why.
        // Selecting it anyway left a feature selected and no measurement.
        if (KigumiHover.HoverState.clickDoesNothing(message, this.measureDraft.isActive)) {
            this.reportMeasureRefusal((message.verdict || {}).reason || 'no-kind');
            return;
        }
        const path = Array.isArray(message.path) ? message.path : [];
        const featureLabel = message.featureLabel || null;
        if (message.memberKey === '' && !featureLabel && path.length === 0) {
            // A drawing's pick along the ray that found nothing on any member: a click on nothing.
            this._dropCsgFocus();
            this.selectionManager.clearTimberSelection();
            return;
        }
        // Kept so that "measure from this" has something to start from without
        // asking again: the reference, where it is, and what it lies on.
        this._lastPickAnchor = this._anchorFromPick(message);
        this.lastPickDetail = {
            featureType: message.featureType || null,
            jointName: message.jointName || null,
            facesToward: message.facesToward || null,
            nodeKind: message.nodeKind || null,
            nodeDisplayName: message.nodeDisplayName || null,
            nodeLabel: message.nodeLabel || null,
            outwardNormal: Array.isArray(message.outwardNormal) ? message.outwardNormal : null,
            derivation: message.derivation || null,
        };
        const hlMesh = message.highlightMesh;
        const parentHlMesh = message.parentHighlightMesh || null;
        const stats = message.stats;

        // Which timber this applies to. message.memberKey is authoritative
        // now that several timbers can be selected at once; the focus and the
        // lone-selection fallback only cover older runners that omit it.
        const focus = this.selectionManager.csgFocus;
        const timberKey = message.memberKey
            || (focus && focus.timberKey)
            || (this.selectionManager.selectedTimbers.size === 1
                ? this.selectionManager.getSelectedTimbers()[0]
                : null);

        if (timberKey) {
            const cutIndex = this._cutIndexForPick(timberKey, path);
            const target = CsgTreeView.revealTarget(focus, { timberKey, cutIndex });
            this.selectionManager.setCsgFocus({
                timberKey,
                path,
                featureLabel,
                cutIndex,
                context: target.section === 'joints'
                    ? { section: 'joints', jointId: target.jointId, cutIndex: target.cutIndex }
                    : { section: 'timbers' },
            });
            this._revealCsgFocusInList(target, path);
        }

        // A pick made while a measurement is being taken is also its second
        // end. Offered to the draft AFTER the ordinary handling rather than
        // instead of it: it is still a selection, and highlighting it is how
        // you can see what you picked. The first end is not deselected by
        // that -- it was never the selection, it is held, and drawn as held.
        if (this.measureDraft.isActive) {
            this._measurePicked(message);
        }

        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        // Kept, not drawn. What is lit is worked out from the state every
        // frame -- see _highlightState -- so this is the geometry that answer
        // will need, and it stops being used the moment the focus moves off it.
        this._csgHighlightSource = {
            key: csgFocusKey({ timberKey, path, featureLabel }),
            mesh: hlMesh,
            parentMesh: parentHlMesh,
            edgePositions: edgeSegmentPositions(message.highlightEdgeSegments),
            pointAt: KigumiHighlights.pointHighlightAt(message),
            featureLabel,
        };

        if (stats) {
            this.emitViewerLog('csg-selection', {
                path,
                featureLabel,
                meshWalkMs: stats.meshWalkMs,
                trianglesMatched: stats.trianglesMatched,
                totalTriangles: stats.totalTriangles,
                ...describeCandidates(message),
            });
        }

        this.selectionPanel.updateInfo(this.currentFrameData);
    }

    _getSelectionVisualContext() {
        return computeSelectionVisualContext(
            this.selectionManager.getSelectedTimbers(),
            this.selectionManager.csgFocus,
        );
    }

    _getSelectionVisualPolicy(state, baseUnselectedOpacity) {
        return selectionVisualPolicy(state, baseUnselectedOpacity);
    }

    /**
     * Everything the look of the frame depends on, folded into one value.
     *
     * READ off the state, never announced by it. Nothing has to remember to say
     * that something changed -- which is the point. Eleven places used to call
     * applySelectionOpacity, which is eleven places that could forget, and a
     * counter bumped by each would only have moved the forgetting somewhere
     * less visible. Asking costs nothing to get wrong.
     *
     * Cheap enough to take every frame: about a hundred and fifty values for a
     * frame of twenty-five timbers. In that same frame renderMeasurements
     * throws the whole SVG overlay away and builds DOM nodes for every
     * dimension -- and that is the one visual here that has never drifted.
     *
     * EVERY INPUT `_memberAppearance` READS HAS TO BE IN HERE, or what is drawn
     * can stop following the state. A test reads both and checks, because that
     * is the one way left to get this wrong.
     */
    visualSignature(state) {
        if (!this.sceneManager || !this.selectionManager) {
            return '';
        }
        // Worked out once a frame and handed in: building it twice would mean
        // asking the same question twice and allocating the edge positions
        // twice with it.
        const lit = state || this._highlightState();
        // Each member's whole state, so anything memberStateFor learns to read
        // is folded without being listed here as well.
        const visualContext = this._getSelectionVisualContext();
        const members = [];
        for (const [key, bundle] of this.sceneManager.entries()) {
            members.push([key, bundle.profileId || '', this._memberState(key, visualContext)]);
        }
        // Gathered here, folded there. The reading is what makes this pulled;
        // the folding is a pure function and is tested as one.
        return SelectionVisuals.visualSignatureOf({
            unselectedTransparencyPercent: this.unselectedTransparencyPercent,
            selectedTransparencyPercent: this.selectedTransparencyPercent,
            edgeLineVisibilityPercent: this.edgeLineVisibilityPercent,
            edgeMode: this.edgeMode,
            showDrawingGhosts: this.showDrawingGhosts,
            showFeatureParent: this.showFeatureParent,
            inDrawing: this.isInDrawing,
            selected: this.selectionManager.getSelectedTimbers() || [],
            focus: this.selectionManager.csgFocus,
            lit,
            members,
        });
    }

    /**
     * Bring what is drawn back in line with the state, if the state has moved.
     *
     * Called from the frame loop, and the only thing that calls
     * applySelectionOpacity now: the eleven scattered callers are gone, and
     * with them the possibility of forgetting one. A change is seen at most a
     * frame later, which is the same frame it would have been drawn in anyway.
     */
    applyDerivedVisuals() {
        const lit = this._highlightState();
        const signature = this.visualSignature(lit);
        if (signature === this._visualSignature) {
            return false;
        }
        this._visualSignature = signature;
        this.applySelectionOpacity();
        this._reconcileHighlights(KigumiHighlights.highlightsFor(lit));
        return true;
    }

    /**
     * What should be lit, as a list. See highlights.js.
     *
     * Every source is kept rather than drawn on arrival, and offered here only
     * while the state it belongs to is still the state: a selection highlight
     * from before the focus moved describes a selection nobody has.
     */
    /**
     * The ends of the selected measurements, lit.
     *
     * Their geometry comes from the runner, asked once per end and kept until the
     * frame changes. An end not yet answered is asked for here and drawn when the
     * answer comes back.
     */
    _measurementEndSources() {
        const marks = this.selectionManager ? this.selectionManager.getMarkedMeasurements() : [];
        const sources = [];
        const missing = [];
        for (const mark of marks) {
            const found = this.focusedMeasurement(mark.viewportId, mark.measureKey);
            if (!found || KigumiMeasurements.isDeleted(found.measure)) {
                continue;
            }
            for (const anchor of [found.measure.a, found.measure.b]) {
                const reference = KigumiMeasurements.anchorReference(anchor);
                if (!reference) {
                    continue;
                }
                const key = 'end:' + JSON.stringify(reference);
                const lit = this._measurementEndHighlights.get(key);
                if (lit) {
                    sources.push(lit);
                } else if (!this._measurementEndAsked.has(key)) {
                    this._measurementEndAsked.add(key);
                    missing.push({ key, reference });
                }
            }
        }
        if (missing.length && typeof vscode !== 'undefined') {
            vscode.postMessage({
                type: 'requestFeatureHighlights',
                keys: missing.map((one) => one.key),
                references: missing.map((one) => one.reference),
            });
        }
        return sources;
    }

    /** The runner's answer for measurement ends: kept by key, drawn from the next frame. */
    _setMeasurementEndHighlights(message) {
        const keys = message.keys || [];
        (message.highlights || []).forEach((highlight, index) => {
            const key = keys[index];
            if (!key) {
                return;
            }
            this._measurementEndHighlights.set(key, {
                key,
                mesh: highlight.highlightMesh,
                edgePositions: edgeSegmentPositions(highlight.highlightEdgeSegments),
                pointAt: KigumiHighlights.pointHighlightAt(highlight),
            });
        });
        this.requestUpdate();
    }

    /**
     * The timbers' reference features, lit where the option says: in drawings, on
     * the members the drawing is about; everywhere, on every visible member; or not.
     */
    _referenceSources() {
        const mode = this.referenceFeatures;
        const inDrawing = Boolean(this.selectionManager && this.selectionManager.inDrawing);
        if (mode === 'never' || (mode === 'drawings' && !inDrawing) || (inDrawing && !this.showDrawingReferenceFeatures)) {
            return [];
        }
        const drawn = this.activeSceneMembers;
        const { featureKeyOf } = KigumiFeatureStates;
        const sources = [];
        for (const [memberKey, features] of this._referenceFeaturesByMember) {
            if (this.isMemberHidden(memberKey) || (drawn && !drawn.has(memberKey))) {
                continue;
            }
            for (const feature of features) {
                sources.push({
                    key: featureKeyOf({ memberKey, path: ['reference'], featureLabel: feature.name }),
                    edgePositions: feature.edgePositions,
                    primary: Boolean(feature.primary),
                });
            }
        }
        return sources;
    }

    _highlightState() {
        const focus = this.selectionManager && this.selectionManager.csgFocus;
        const source = this._csgHighlightSource;
        const held = this.measureDraft && this.measureDraft.heldEnd;
        const hover = this._hover && this._hover.drawn;
        const { featureKeyOf, featureStatesFor } = KigumiFeatureStates;
        return {
            features: featureStatesFor({
                selection: KigumiHighlights.sourceForFocus(source, csgFocusKey(focus)),
                hover: hover ? {
                    key: featureKeyOf(hover),
                    mesh: hover.highlightMesh,
                    edgePositions: edgeSegmentPositions(hover.highlightEdgeSegments),
                    pointAt: KigumiHighlights.pointHighlightAt(hover),
                    refused: KigumiHover.HoverState.isRefused(hover),
                } : null,
                held: (held && held.highlight) ? {
                    key: held.featureKey || heldHighlightKey(held.reference),
                    mesh: held.highlight.highlightMesh,
                    edgePositions: edgeSegmentPositions(held.highlight.highlightEdgeSegments),
                    pointAt: KigumiHighlights.pointHighlightAt(held),
                } : null,
                measurementEnd: this._measurementEndSources(),
                reference: this._referenceSources(),
            }),
            showFeatureParent: Boolean(this.showFeatureParent),
            policy: this._getSelectionVisualPolicy(
                this._getSelectionVisualContext().state,
                1 - (this.unselectedTransparencyPercent / 100)),
        };
    }

    /**
     * Make what is lit match what should be.
     *
     * Adds what is missing, drops what is no longer wanted, and leaves the rest
     * alone -- so an overlay that is still wanted keeps its geometry and only
     * its colour and opacity follow the state. Nothing here decides WHETHER
     * something should be lit; that is highlightsFor's job, and it is pure.
     */
    _reconcileHighlights(wanted) {
        KigumiHighlights.reconcile(this._highlightObjects, wanted, {
            build: (descriptor) => {
                const object = this._buildHighlightObject(descriptor);
                if (object) {
                    object.userData.role = descriptor.role;
                    object.userData.opacity = descriptor.opacity;
                    this.scene.add(object);
                }
                return object;
            },
            // Appearance every pass, geometry only once: the opacity follows
            // the selection, which the old code froze at the moment the
            // message arrived.
            update: (object, descriptor) => {
                object.userData.role = descriptor.role;
                object.userData.opacity = descriptor.opacity;
                object.material.color.setHex(descriptor.color);
                object.material.opacity = descriptor.opacity;
                object.renderOrder = descriptor.renderOrder;
            },
            drop: (object) => {
                this.scene.remove(object);
                object.geometry.dispose();
                object.material.dispose();
            },
        });
    }

    /** One overlay, of any of the three shapes. */
    _buildHighlightObject(descriptor) {
        if (descriptor.shape === 'point') {
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute(
                'position', new THREE.BufferAttribute(new Float32Array(descriptor.at), 3));
            const material = new THREE.PointsMaterial({
                color: descriptor.color,
                size: CSG_HIGHLIGHT_POINT_SIZE_PX,
                // The size is in pixels, not world units, so it does not shrink
                // to nothing as the camera pulls back.
                sizeAttenuation: false,
                transparent: true,
                opacity: descriptor.opacity,
                // Over the timber it sits on, as the other two overlays are: a
                // corner is exactly where the surface is, so depth testing it
                // leaves it fighting the surface for the same pixels.
                depthTest: false,
                depthWrite: false,
            });
            return new THREE.Points(geometry, material);
        }
        if (descriptor.shape === 'edges') {
            const geometry = new THREE.LineSegmentsGeometry();
            geometry.setPositions(descriptor.positions);
            const material = new THREE.LineMaterial({
                color: descriptor.color,
                linewidth: descriptor.linewidth || CSG_HIGHLIGHT_EDGE_WIDTH_PX,
                // Pixel thickness is computed against this, so it tracks the
                // canvas the way the timbers' own edges do. Kept in step on
                // resize for EVERY overlay now -- only the selection's line
                // used to be, so the hover and the held one went thin.
                resolution: this._getRendererResolution(),
                // Over everything, unless the overlay is a mark ON the timber (a
                // reference feature): then hidden by what is in front, and pulled
                // a little toward the camera so it does not fight the surface it lies on.
                depthTest: Boolean(descriptor.depthTest),
                depthWrite: false,
                polygonOffset: Boolean(descriptor.depthTest),
                polygonOffsetFactor: -1,
                polygonOffsetUnits: -4,
                transparent: true,
                opacity: descriptor.opacity,
            });
            const line = new THREE.LineSegments2(geometry, material);
            line.computeLineDistances();
            return line;
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
            'position', new THREE.BufferAttribute(new Float32Array(descriptor.mesh.vertices), 3));
        geometry.setIndex(descriptor.mesh.indices);
        geometry.computeVertexNormals();
        const material = new THREE.MeshBasicMaterial({
            color: descriptor.color,
            transparent: true,
            opacity: descriptor.opacity,
            depthTest: false,
            depthWrite: false,
            side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        return mesh;
    }

    applySelectionOpacity() {
        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const baseSelectedOpacity = 1 - (this.selectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        for (const [name, bundle] of this.sceneManager.entries()) {
            this.sceneManager.setMemberAppearance(name, this._memberAppearance(name, bundle, {
                baseSelectedOpacity,
                visualContext,
                policy,
            }));
        }
    }

    /** What a member looks like: its state, resolved with the current settings. See member-states.js. */
    _memberAppearance(memberKey, bundle, { baseSelectedOpacity, visualContext, policy }) {
        return KigumiMemberStates.appearanceFor(this._memberState(memberKey, visualContext), {
            baseSelectedOpacity,
            policy,
            profile: this.resolveRenderProfile(bundle.profileId),
            edgeLineVisibilityPercent: this.edgeLineVisibilityPercent,
            edgeMode: this.edgeMode,
            showDrawingGhosts: this.showDrawingGhosts,
            drawingContextOpacity: DRAWING_CONTEXT_OPACITY,
        });
    }

    /** What state a member is in. See member-states.js; the signature folds it per member. */
    _memberState(memberKey, visualContext) {
        return KigumiMemberStates.memberStateFor(memberKey, {
            hidden: this.isMemberHidden(memberKey),
            locked: this.isMemberLocked(memberKey),
            visualContext,
            drawnMembers: this.activeSceneMembers,
            inDrawing: this.isInDrawing,
        });
    }

    /** Whether a measurement could be started from what is focused now. */
    /** The picked feature's reference and world geometry, or null. */
    get pickedFeature() {
        const anchor = this._lastPickAnchor;
        return anchor ? { reference: anchor.reference, geometry: anchor.geometry } : null;
    }

    /** Have the extension put a description of the selection on the clipboard, for an assistant. */
    copySelectionForAI(selection) {
        if (vscode) {
            vscode.postMessage({ type: 'copySelectionForAI', selection });
        }
    }
};
