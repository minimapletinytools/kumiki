/**
 * What the pointer is over and what a click picks: the hover asked for, answered and shown; the click and the pick request it sends.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { choosePickAction, vscode } from './viewer-shared.js';
import * as KigumiHover from './hover-state.js';

export const PickingMixin = (Base) => class extends Base {
    /** The pointer moved over the canvas. Cheap: no request goes out here. */
    handleCanvasHover(event) {
        if (!this._hover) {
            this._hover = new KigumiHover.HoverState();
        }
        // Which viewport a pick lands in is decided from here, since the answer
        // arrives long after the click that asked.
        this._lastClientX = event.clientX;
        this._lastClientY = event.clientY;
        const under = this._resolvePointer(event.clientX, event.clientY);
        this._hoverViewportId = under ? under.viewport.id : null;
        // The pointer says whether shift is down, which catches a press the window missed.
        this._setShiftHeld(Boolean(event.shiftKey));
        // Both thresholds at once: forget a cycled choice on any movement, ask
        // again only once past the slop. See HoverState.pointerAt.
        this._hover.pointerAt(event.clientX, event.clientY);
    }

    /**
     * Ask about the pointer, once it has settled.
     *
     * Driven from the render loop rather than a timer, so a hover cannot
     * outlive the viewer that owns it, and so nothing is asked while the tab
     * is not drawing.
     */
    pumpHover() {
        if (!this._hover || typeof vscode === 'undefined') {
            return;
        }
        const due = this._hover.due();
        if (!due) {
            return;
        }
        // The same decision a click makes, so hover shows what a click would do
        // rather than something else -- shift included, since it switches the
        // selection mode. Only a pick that reaches a feature has one to ask the
        // runner about: in timber mode that is a timber already selected, so
        // with shift held while measuring nothing else lights.
        //
        // The decision also says WHICH member, which is not the nearest one: a
        // click drills into the selected timber wherever it sits along the ray.
        const along = this._findMembersAlongRay(due.x, due.y);
        const decision = choosePickAction({
            hits: along.hits,
            selectedTimbers: this.selectionManager.selectedTimbers,
            shiftKey: this._shiftHeld,
            inDrawing: this.selectionManager.inDrawing,
            measuring: this.measureDraft.isActive,
            alongRay: Boolean(along.ray),
        });
        const target = KigumiHover.hoverTarget(decision)
            || (decision.action === 'csg' && along.ray ? { memberKey: null, point: along.ray.origin } : null);
        if (decision.action !== 'csg' || !target) {
            // Either nothing under the pointer, or a click here would take the
            // whole timber rather than anything inside it.
            if (this._hover.pinned) {
                // The feature menu is holding this point and what it offers has
                // gone. Close it rather than leave rows naming features that are
                // not there -- and only the feature menu pins, so this cannot
                // reach the export menu, which a hover finding nothing must not
                // dismiss.
                this.closeMemberContextMenu();
            }
            this.clearHover();
            return;
        }

        // From wherever the selection already is, exactly as the click does.
        const focus = this.selectionManager.csgFocus;
        const currentPath = (focus && focus.timberKey === target.memberKey) ? focus.path : [];
        vscode.postMessage({
            type: 'hoverFeatureAtPoint',
            memberKey: target.memberKey,
            point: target.point,
            currentPath,
            ctrlClick: false,
            request: due.request,
            // Null, not zero: zero means "the first one", and the runner needs
            // to tell that from "choose for me".
            candidateIndex: this._hover.asking,
            // The same tolerances a click would use, or hover lights something
            // a click then refuses to select -- and through the camera the ray
            // actually went through, which on a sheet need not be the active
            // viewport's.
            tolerances: this._pickTolerances(target.point, along.camera, along.viewHeight),
            // The line the pointer went along, so features that lie in a void
            // rather than on a surface can be found at all. See _findMembersAlongRay.
            ray: along.ray,
            ...this._pickContext(),
            // The end already held, and which way we are looking. With these
            // the runner offers the feature that can finish the measurement
            // rather than the most specific one, and says whether it can.
            ...this._heldForRequest(),
        });
    }

    /** An answer came back. Draws only when it is about somewhere new. */
    handleHoverResult(message) {
        if (!this._hover) {
            return;
        }
        const kept = this._hover.answered(message.request, message);
        if (!kept.kept) {
            return;
        }
        // The verdict counts as part of what is drawn, not just the feature:
        // taking a first end is a button press, so the colour can change while
        // the pointer rests exactly where it was.
        if (!this._hover.wouldRedraw(message)) {
            return;
        }
        this._hover.markDrawn(message);
        if (this.contextMenu.isOpen) {
            // The feature menu marks the row THIS answer came from, so a new
            // answer has to reach it. Tab changes the answer without the pointer
            // moving, and nothing else would draw the menu again.
            this.requestUpdate();
        }
        // What the pointer is offering, drawn as the measurement it would make.
        this._updateMeasurePreview(message);
        // Nothing is drawn here. What the pointer is over is part of the state,
        // and the frame loop lights it -- including in the refused colour, from
        // the same verdict the click reads, so the two cannot disagree.
    }

    /** What the hover has to say about the measurement in hand, if any. */
    _heldForRequest() {
        // Whether an end is still held is the draft's to answer, not this
        // method's: asking for HOLDING alone left every pick after the first
        // pair judged as if nothing were held, so the runner returned no kinds,
        // no pairwise anchors and no plane -- and a third pick drew nothing in
        // the 3D view and drew the preview from each end's own position, only
        // coming right on confirm.
        const held = this.measureDraft.heldEnd;
        // Only in the view it is being made in: elsewhere a click starts again, so a hover there
        // is an ordinary one, judged against nothing.
        if (!held || this._hoverViewportId !== this.selectionManager.scope) {
            return {};
        }
        const viewport = this.viewports.find((one) => one.id === this.selectionManager.scope);
        const axes = viewport ? this.viewportAxes(viewport) : null;
        return {
            heldGeometry: held.geometry,
            heldAt: held.at,
            // The reference too, so the runner can resolve the held end the way
            // it resolves a written one and place both through the same rules.
            // Sending its geometry alone left it working the answer out a
            // second way, and the two drifted.
            heldReference: held.reference,
            look: axes ? axes.look : null,
            right: axes ? axes.right : null,
            up: axes ? axes.up : null,
        };
    }

    /**
     * What every pick is judged in, measuring or not. The space: a drawing projects onto its
     * sheet -- everything under the pointer is a candidate, and a face is a plane only seen
     * edge-on -- while the 3D view takes the surface the pointer is on. And in a drawing, the
     * members it draws, which are what can hide something; its faded context cannot.
     */
    _pickContext() {
        const drawn = this.isInDrawing ? this.activeSceneMembers : null;
        return {
            space: this.isInDrawing ? 'projected' : '3d',
            drawnMembers: drawn ? Array.from(drawn) : null,
        };
    }

    /**
     * The pointer is over nothing worth drawing: forget what was.
     *
     * The outline, the measurement preview, and the record of what is drawn --
     * one thing between them, so they go together. Called where the hover has
     * actually gone away, never from the teardown inside a redraw.
     *
     * There may be no hover yet: it is made on the first pointer move, and a scene can change
     * before one (the viewer opening straight into a drawing).
     */
    _forgetHover() {
        if (this._hover) {
            this._hover.markDrawn(null);
        }
        this._updateMeasurePreview(null);
    }

    /** Leaving the canvas, or changing mode: nothing should stay lit. */
    clearHover() {
        if (this._hover && this._hover.pinned) {
            // The feature menu is asking, about the point it was opened at, and
            // reaching one of its rows means leaving the canvas. Anything that
            // really means "end this" closes the menu first, which unpins.
            return false;
        }
        if (this._hover) {
            this._hover.clear();
        }
        this._forgetHover();
        return true;
    }

    handleCanvasClick(event) {
        if (!event) {
            return;
        }
        // A pick belongs to the view it is made in; one in another view starts there afresh.
        const under = this._resolvePointer(event.clientX, event.clientY);
        if (under) {
            this.selectionManager.enterScope(under.viewport.id);
        }
        const { hits, camera: pickCamera, ray: pickRay, viewHeight: pickViewHeight } =
            this._findMembersAlongRay(event.clientX, event.clientY);
        const decision = choosePickAction({
            hits,
            selectedTimbers: this.selectionManager.selectedTimbers,
            shiftKey: !!event.shiftKey,
            // The selection mode (pickMode): feature mode in a drawing and while
            // measuring, timber mode otherwise and with shift held while measuring.
            // Hover asks the same question above and must get the same answer, or
            // it lights what a click will not take.
            inDrawing: this.selectionManager.inDrawing,
            measuring: this.measureDraft.isActive,
            alongRay: Boolean(pickRay),
        });

        if (decision.action === 'clear') {
            this._dropCsgFocus();
            this.selectionManager.clearTimberSelection();
            return;
        }

        const { memberKey, hit } = decision;

        if (decision.action === 'toggle') {
            this._dropCsgFocus();
            this.selectionManager.toggleTimber(memberKey);
        } else if (decision.action === 'csg') {
            // Drilling into a timber that is already selected. Ask the runner
            // what sits under the cursor; the answer comes back as a
            // csgSelectionResult and becomes the new focus.
            // No surface hit (a drawing's pick along the ray): the ray's start stands in for it.
            const point = hit ? [hit.point.x, hit.point.y, hit.point.z] : pickRay.origin;
            const focus = this.selectionManager.csgFocus;
            const currentPath = (focus && focus.timberKey === memberKey) ? focus.path : [];
            if (typeof vscode !== 'undefined') {
                const request = {
                    type: 'findCSGAtPoint',
                    memberKey,
                    point,
                    currentPath,
                    // No drilling in a drawing: its views pick features directly, every timber alike.
                    ctrlClick: !this.isInDrawing && (!!event.ctrlKey || !!event.metaKey),
                    tolerances: this._pickTolerances(point, pickCamera, pickViewHeight),
                    // See _findMembersAlongRay: a hit point is on a surface, and
                    // a feature in a void is not near any surface.
                    ray: pickRay,
                    // Whatever the hover is showing is what the click takes.
                    candidateIndex: this._hover ? this._hover.asking : null,
                    ...this._pickContext(),
                    // The same question the hover asked, so the click resolves
                    // to the feature the hover lit rather than to a different
                    // one -- and so the pick comes back with the plane.
                    ...this._heldForRequest(),
                };
                // The whole question, so a pick can be replayed against the runner.
                this.emitViewerLog('pick-request', {
                    ...request,
                    camera: pickCamera ? {
                        position: pickCamera.position.toArray(),
                        quaternion: pickCamera.quaternion.toArray(),
                    } : null,
                });
                vscode.postMessage(request);
            }
        } else {
            this._dropCsgFocus();
            this.selectionManager.selectTimber(memberKey, false);
        }

        this.emitViewerLog('selection-changed', {
            selectedTimbers: this.selectionManager.getSelectedTimbers(),
        });
        // What the pointer rests on may light differently now: in timber mode a
        // timber just selected offers its features.
        if (this._hover) {
            this._hover.askAgain();
        }
    }
};
