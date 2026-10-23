/**
 * How the scene looks: theme and geometry mode, the center gizmo, edges, shadows, reflections, footprints, materials, the light and cylinder silhouettes.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { CameraCubeGizmo, DEFAULT_FOOTPRINT_COLOR, DEFAULT_THEME_UI, FOOTPRINT_COLOR_SWATCHES, GeometryMode, OrbitCenterGizmo, THEMES, radialFadeColor, t, vscode } from './viewer-shared.js';
import * as KigumiPickTolerances from './pick-tolerances.js';

export const RenderingMixin = (Base) => class extends Base {
    setTheme(id) {
        const theme = THEMES[id];
        if (!theme) {
            return;
        }
        this.displayOptions.set('activeTheme', id);
        this.memberRenderProfileByType = {
            timber: theme.timberProfileId,
            accessory: theme.accessoryProfileId,
        };
        this.applyThemeUiTokens(theme);
        if (this.scene) {
            const tex = this._buildBackgroundTexture(theme);
            if (this._themeBackground && this._themeBackground.isTexture) {
                this._themeBackground.dispose();
            }
            this._themeBackground = tex;
            this._sheetColors = null;
            // Not applied here: the background is one of the things a mode
            // says, and applyRenderMode writes it on the frame requested below.
        }
        this.style.background = this._buildCssBg(theme);
        this.applyRenderProfilesToScene();
        this.requestUpdate();
    }

    setGeometryMode(mode) {
        const next = GeometryMode.VALID_MODES.has(mode) ? mode : GeometryMode.DEFAULT_MODE;
        const prev = (this.viewerOptions && this.viewerOptions.geometryMode) || GeometryMode.DEFAULT_MODE;
        if (next === prev) {
            return;
        }
        this.viewerOptions = { ...this.viewerOptions, geometryMode: next };

        // Identify timbers whose displayed mesh will actually swap when the mode
        // changes (by reference -- see GeometryMode.selectMeshBuffers). Accessories
        // and timbers whose alternate-mode arrays are absent render the same
        // geometry in either mode and are excluded.
        const lastMeshes = (this._lastGeometryData && this._lastGeometryData.meshes) || [];
        const swappedKeys = new Set();
        for (const mesh of lastMeshes) {
            if (!mesh) {
                continue;
            }
            const memberType = mesh.memberType === 'accessory' ? 'accessory' : 'timber';
            if (GeometryMode.meshBuffersDifferBetweenModes(mesh, memberType, prev, next)) {
                const key = mesh.memberKey || mesh.timberKey;
                if (key) {
                    swappedKeys.add(key);
                }
            }
        }

        // A CSG focus references triangles on the actual-geometry mesh; the
        // perfect-timber-within mesh is a different surface, so the focus
        // becomes invalid when geometry swaps. Timber-level selection survives,
        // because identity is keyed by memberKey, not by mesh contents.
        if (swappedKeys.size > 0 && this.selectionManager) {
            const focus = this.selectionManager.csgFocus;
            if (focus && swappedKeys.has(focus.timberKey)) {
                this._dropCsgFocus();
            }
        }

        if (this._lastGeometryData) {
            this.activeRefreshToken += 1;
            const token = this.activeRefreshToken;
            this.updateMeshScene(this._lastGeometryData, token, null).catch((err) => {
                // eslint-disable-next-line no-console
                console.error('setGeometryMode: updateMeshScene failed', err);
            });
        }

        if (this.settingsPanel && this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }

        // Persist the mode through the extension so subsequent refreshes start
        // in the same geometry mode. The runner does not need to act on this
        // (both meshes are always sent for non-perfect timbers), but the
        // extension echoes viewerOptions back on payload init.
        if (vscode) {
            vscode.postMessage({ type: 'setRefreshOptions', options: this.viewerOptions });
        }
    }

    applyThemeUiTokens(theme) {
        const ui = theme && theme.ui ? theme.ui : DEFAULT_THEME_UI;
        const tokenMap = {
            '--hv-bg-top': ui.bgTop,
            '--hv-bg-bottom': ui.bgBottom,
            '--hv-panel-bg': ui.panelBg,
            '--hv-panel-border': ui.panelBorder,
            '--hv-text': ui.text,
            '--hv-title': ui.title,
            '--hv-dim': ui.dim,
            '--hv-accent': ui.accent,
            '--hv-mesh': ui.mesh,
            '--hv-edge': ui.edge,
            '--hv-strong': ui.strong,
            '--hv-hint': ui.hint,
            '--hv-overlay-bg': ui.overlayBg,
            '--hv-overlay-error-bg': ui.overlayErrorBg,
            '--hv-broken': ui.broken,
            '--hv-error': ui.error,
            '--hv-error-hover': ui.errorHover,
            '--hv-error-active': ui.errorActive,
            '--hv-error-fg': ui.errorFg,
            '--hv-debug-accent': ui.debugAccent,
            '--hv-control-bg': ui.controlBg,
            '--hv-control-bg-strong': ui.controlBgStrong,
            '--hv-control-bg-hover': ui.controlBgHover,
            '--hv-control-bg-solid': ui.controlBgSolid,
            '--hv-control-bg-solid-hover': ui.controlBgSolidHover,
            '--hv-control-border': ui.controlBorder,
            '--hv-control-border-strong': ui.controlBorderStrong,
            '--hv-panel-header-bg': ui.panelHeaderBg,
            '--hv-table-head-bg': ui.tableHeadBg,
            '--hv-row-hover-bg': ui.rowHoverBg,
            '--hv-row-border': ui.rowBorder,
            '--hv-row-index': ui.rowIndex,
            '--hv-input-bg': ui.inputBg,
            '--hv-input-border': ui.inputBorder,
            '--hv-accent-soft': ui.accentSoft,
            '--hv-accent-mid': ui.accentMid,
            '--hv-accent-strong': ui.accentStrong,
            '--hv-accent-border': ui.accentBorder,
            '--hv-accent-border-strong': ui.accentBorderStrong,
            '--hv-layers-bg': ui.layersBg,
            '--hv-layers-collapsed-bg': ui.layersCollapsedBg,
            '--hv-layers-header-bg': ui.layersHeaderBg,
            '--hv-layers-hover-bg': ui.layersHoverBg,
            '--hv-layers-selected-bg': ui.layersSelectedBg,
            '--hv-chip-bg': ui.chipBg,
            '--hv-tag-member': ui.tagMember,
            '--hv-tag-slice': ui.tagSlice,
            '--hv-tag-generic': ui.tagGeneric,
        };
        for (const [cssVar, value] of Object.entries(tokenMap)) {
            this.style.setProperty(cssVar, value);
        }
        this.dataset.theme = ui.mode || 'light';
    }

    _buildBackgroundTexture(preset) {
        const w = preset.pattern ? 256 : 2;
        const h = 256;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, preset.gradientTop);
        gradient.addColorStop(1, preset.gradientBottom);
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);
        if (preset.pattern === 'linen') {
            ctx.strokeStyle = 'rgba(160,140,100,0.07)';
            ctx.lineWidth = 1;
            for (let i = -h; i < w + h; i += 12) {
                ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(i + h, 0); ctx.lineTo(i, h); ctx.stroke();
            }
        } else if (preset.pattern === 'grid') {
            ctx.strokeStyle = 'rgba(80,140,220,0.12)';
            ctx.lineWidth = 1;
            const sp = 24;
            for (let x = 0; x < w; x += sp) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
            }
            for (let y = 0; y < h; y += sp) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }
        } else if (preset.pattern === 'blobs' && Array.isArray(preset.blobColors)) {
            const radius = Math.max(w, h) * 0.55;
            for (const blob of preset.blobColors) {
                const cx = blob.x * w;
                const cy = blob.y * h;
                const blobGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
                blobGradient.addColorStop(0, blob.color);
                blobGradient.addColorStop(1, radialFadeColor(blob.color));
                ctx.fillStyle = blobGradient;
                ctx.fillRect(0, 0, w, h);
            }
        }
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        return tex;
    }

    _buildCssBg(preset) {
        if (preset.pattern === 'linen') {
            return `repeating-linear-gradient(45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), repeating-linear-gradient(-45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        if (preset.pattern === 'grid') {
            return `linear-gradient(rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(90deg, rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        if (preset.pattern === 'blobs' && Array.isArray(preset.blobColors)) {
            const blobLayers = preset.blobColors
                .map((blob) => `radial-gradient(circle at ${Math.round(blob.x * 100)}% ${Math.round(blob.y * 100)}%, ${blob.color} 0%, ${radialFadeColor(blob.color)} 60%)`)
                .join(', ');
            return `${blobLayers}, linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        return `linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
    }

    setCenterGizmoEnabled(enabled) {
        this.showCenterGizmo = enabled;
        this.updateOrbitCenterGizmo();
    }

    /**
     * Build the camera controls this scene asks for, and tear down the ones it
     * does not.
     *
     * Re-run whenever the active scene changes, not just at setup: the orbit
     * gizmo lives in the scene graph, so one built for the 3D view would go on
     * drawing its crosshair over a drawing's elevations.
     */
    syncCameraControls() {
        const wantsOrbitGizmo = this.sceneStore.wantsCameraControl('orbitGizmo');
        if (wantsOrbitGizmo && !this.orbitGizmo && this.scene) {
            this.orbitGizmo = new OrbitCenterGizmo({ THREE });
            this.orbitCenterGizmo = this.orbitGizmo.object3d;
            this.scene.add(this.orbitCenterGizmo);
        } else if (!wantsOrbitGizmo && this.orbitGizmo) {
            if (this.scene) {
                this.scene.remove(this.orbitCenterGizmo);
            }
            this.orbitGizmo.dispose();
            this.orbitGizmo = null;
            this.orbitCenterGizmo = null;
        }

        // The panel first: the cube and the light dial size themselves from it, and
        // built while it was still hidden on the way back from a drawing they came
        // out a pixel across.
        const panel = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#gizmo-panel')
            : null;
        if (panel) {
            const wantsAny = ['cube', 'orbitGizmo', 'projection', 'focus']
                .some((name) => this.sceneStore.wantsCameraControl(name));
            panel.style.display = wantsAny ? '' : 'none';
        }

        // The cube's canvas stays mounted either way -- its pointer handlers
        // are bound once at startup and would not survive being unmounted and
        // brought back. Hiding the panel is what makes it go away.
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#gizmo-cube-c')
            : null;
        const wantsCube = Boolean(canvas) && this.sceneStore.wantsCameraControl('cube');
        if (wantsCube && !this.cameraCube) {
            this.cameraCube = new CameraCubeGizmo({ THREE, canvas });
        } else if (!wantsCube && this.cameraCube) {
            this.cameraCube.dispose();
            this.cameraCube = null;
        }

        // Whatever changed size while the panel was hidden is put right now it shows.
        if (this.cameraCube) {
            this.cameraCube.resize();
        }
        this.drawLightDial();
    }

    /** Collapse the camera controls to their header, or bring them back. */
    toggleCameraPanel() {
        this.cameraPanelCollapsed = !this.cameraPanelCollapsed;
        this.requestUpdate();
        if (!this.cameraPanelCollapsed) {
            // Hidden, the cube and the dial had no size to draw at.
            this.updateComplete.then(() => this.syncCameraControls());
        }
    }

    renderCameraControls() {
        if (!this.cameraCube || !this.camera) {
            return;
        }
        const controller = this.cameraController;
        this.cameraCube.render(
            this.camera.position,
            { x: controller.cx, y: controller.cy, z: controller.cz },
        );
    }

    updateOrbitCenterGizmo() {
        if (!this.orbitGizmo) {
            return;
        }
        const controller = this.cameraController;
        this.orbitGizmo.update({
            center: { x: controller.cx, y: controller.cy, z: controller.cz },
            orbitDist: controller.orbitDist,
            visible: this.showCenterGizmo,
        });
    }

    setEdgeMode(mode) {
        if (!this.displayOptions.set('edgeMode', mode)) {
            return;
        }
        const next = this.edgeMode;
        // depthTest/depthWrite differ by mode ('overlay' always draws on top;
        // 'noOverlay' is properly depth-tested/occluded) -- update existing
        // materials in place rather than rebuilding meshes.
        const depthTested = next === 'noOverlay';
        for (const bundle of this.sceneManager.bundles()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.depthTest = depthTested;
                bundle.edges.material.depthWrite = depthTested;
                bundle.edges.material.needsUpdate = true;
            }
        }
        this.requestUpdate();
    }

    setEdgeLineThicknessPx(nextThickness) {
        if (!this.displayOptions.set('edgeLineThicknessPx', nextThickness)) {
            return;
        }
        const normalized = this.edgeLineThicknessPx;
        for (const bundle of this.sceneManager.bundles()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.linewidth = normalized;
            }
        }
        this.requestUpdate();
    }

    setShadowsEnabled(enabled) {
        // Records the ASK and nothing else. What it turns into -- the shadow
        // map, the sun's castShadow, whether the catcher is drawn -- depends on
        // whether a sheet is open as well, so it is applyRenderMode's to
        // derive. Writing it from here too is how the two used to disagree
        // about a sheet.
        this.displayOptions.set('shadowsEnabled', enabled);
        this.requestUpdate();
    }

    setReflectionsEnabled(enabled) {
        // Records the ASK and nothing else, as setShadowsEnabled does. What it
        // turns into depends on whether a sheet is open as well, so it is
        // applyRenderMode's to derive on the frame requested below.
        this.displayOptions.set('reflectionsEnabled', enabled);
        this.requestUpdate();
    }

    setFootprintColor(color) {
        if (!this.displayOptions.set('footprintColor', color)) {
            return;
        }
        const swatch = FOOTPRINT_COLOR_SWATCHES[this.footprintColor];
        if (Array.isArray(this.footprintObjects) && swatch) {
            for (const obj of this.footprintObjects) {
                if (obj && obj.fillMaterial) {
                    obj.fillMaterial.color.setHex(swatch.fill);
                }
                if (obj && obj.edgeMaterial) {
                    obj.edgeMaterial.color.setHex(swatch.edge);
                }
            }
        }
        this.applyFootprintVisibility();
        this.requestUpdate();
    }

    disposeFootprintObjects() {
        if (!Array.isArray(this.footprintObjects)) {
            this.footprintObjects = [];
            return;
        }
        for (const obj of this.footprintObjects) {
            if (!obj) {
                continue;
            }
            if (obj.group && this.scene) {
                this.scene.remove(obj.group);
            }
            if (obj.fillGeometry) obj.fillGeometry.dispose();
            if (obj.fillMaterial) obj.fillMaterial.dispose();
            if (obj.edgeGeometry) obj.edgeGeometry.dispose();
            if (obj.edgeMaterial) obj.edgeMaterial.dispose();
        }
        this.footprintObjects = [];
    }

    rebuildFootprints(footprints) {
        this.disposeFootprintObjects();
        const list = Array.isArray(footprints) ? footprints : [];
        const swatch = FOOTPRINT_COLOR_SWATCHES[this.footprintColor] || FOOTPRINT_COLOR_SWATCHES[DEFAULT_FOOTPRINT_COLOR];
        for (const footprint of list) {
            const corners = (footprint && Array.isArray(footprint.corners)) ? footprint.corners : [];
            if (corners.length < 3) {
                continue;
            }

            // Light filled polygon in the ground (XY, z=0) plane.
            const shape = new THREE.Shape();
            shape.moveTo(corners[0][0], corners[0][1]);
            for (let i = 1; i < corners.length; i += 1) {
                shape.lineTo(corners[i][0], corners[i][1]);
            }
            shape.closePath();
            const fillGeometry = new THREE.ShapeGeometry(shape);
            const fillMaterial = new THREE.MeshBasicMaterial({
                color: swatch.fill,
                transparent: true,
                opacity: 0.4,
                side: THREE.DoubleSide,
                depthWrite: false,
            });
            const fillMesh = new THREE.Mesh(fillGeometry, fillMaterial);
            fillMesh.renderOrder = -1;

            // Darkened edge around the footprint boundary.
            const edgePoints = corners.map((c) => new THREE.Vector3(c[0], c[1], 0));
            edgePoints.push(new THREE.Vector3(corners[0][0], corners[0][1], 0));
            const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
            const edgeMaterial = new THREE.LineBasicMaterial({ color: swatch.edge });
            const edgeLine = new THREE.Line(edgeGeometry, edgeMaterial);
            edgeLine.renderOrder = 0;

            const group = new THREE.Group();
            // Lift a hair off the ground plane to avoid z-fighting with the shadow catcher.
            group.position.z = 0.0015;
            group.add(fillMesh);
            group.add(edgeLine);
            group.visible = this.footprintColor !== 'transparent' && !this.isInDrawing;
            if (this.scene) {
                this.scene.add(group);
            }

            this.footprintObjects.push({ group, fillGeometry, fillMaterial, edgeGeometry, edgeMaterial });
        }
    }

    /**
     * Whether the ground footprints are drawn.
     *
     * Never in a drawing: a footprint is where the frame meets the ground, and
     * a sheet is about the pieces rather than the site. The colour setting
     * stays -- it is the 3D view's, and a drawing that wants one later can say
     * so -- but for now a drawing simply has none.
     */
    applyFootprintVisibility() {
        const visible = this.footprintColor !== 'transparent' && !this.isInDrawing;
        for (const obj of (this.footprintObjects || [])) {
            if (obj && obj.group) {
                obj.group.visible = visible;
            }
        }
    }

    setLeftClickDragRotatesCameraEnabled(enabled) {
        this.leftClickDragRotatesCamera = Boolean(enabled);
        this.requestUpdate();
    }

    resolveRenderProfile(profileId) {
        if (profileId && this.renderProfiles[profileId]) {
            return this.renderProfiles[profileId];
        }
        return this.renderProfiles['timber-default'];
    }

    resolveRenderProfileIdForMemberType(memberType) {
        if (memberType === 'accessory') {
            return this.memberRenderProfileByType.accessory;
        }
        return this.memberRenderProfileByType.timber;
    }

    // Single source of truth for the solid/edge/reflection material parameters
    // derived from a render profile. Used both to construct new materials
    // (createMaterialSetForMemberType) and to mutate existing ones
    // (applyRenderProfileToBundle), so the two paths never drift.
    renderProfileMaterialSpecs(profile) {
        return {
            solid: {
                color: profile.solidColor,
                metalness: profile.metalness,
                roughness: profile.roughness,
                flatShading: true,
                polygonOffset: true,
                // Larger than the original overlay-only values (2/2) --
                // 'noOverlay' mode depth-tests edges against these coincident
                // faces, so they need more headroom to win cleanly instead of
                // z-fighting. Doesn't affect 'overlay' mode since its edges
                // have depthTest disabled and never compare against this.
                polygonOffsetFactor: 2,
                polygonOffsetUnits: 2,
                side: THREE.FrontSide,
            },
            edge: {
                color: profile.edgeColor,
                transparent: true,
                opacity: profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100),
                // 'overlay' (default): always drawn on top, matching the
                // original edge-overlay behavior. 'noOverlay': depth tested
                // so edges are properly occluded by geometry in front of
                // them. setEdgeMode() also updates this in place on existing
                // materials when the mode changes.
                depthTest: this.edgeMode === 'noOverlay',
                depthWrite: this.edgeMode === 'noOverlay',
                // Fat lines (THREE.LineMaterial): linewidth is in screen
                // pixels (this three.js version has no worldUnits option),
                // and resolution must track the actual canvas size or the
                // computed pixel width is wrong -- onWindowResize() keeps
                // this in sync on existing materials.
                linewidth: this.edgeLineThicknessPx,
                resolution: this._getRendererResolution(),
            },
            reflection: {
                color: profile.reflectionColor,
                metalness: profile.reflectionMetalness,
                roughness: profile.reflectionRoughness,
                transparent: true,
                opacity: profile.reflectionOpacity,
                flatShading: true,
                depthWrite: false,
                side: THREE.DoubleSide,
            },
        };
    }

    // Apply a material spec (as built by renderProfileMaterialSpecs) to an
    // existing THREE material in place. `color` is a hex number applied via
    // setHex; every other key is assigned directly.
    applyMaterialSpec(material, spec) {
        const { color, ...rest } = spec;
        if (color !== undefined) {
            material.color.setHex(color);
        }
        Object.assign(material, rest);
        material.needsUpdate = true;
    }

    // THREE.LineMaterial's resolution uniform needs the actual canvas size in
    // pixels; falls back to a 1x1 placeholder before the renderer exists
    // (onWindowResize() and setEdgeLineThicknessPx() keep it correct afterwards).
    /**
     * The pick tolerances a click at *worldPoint* should be judged by.
     *
     * The camera is an argument rather than a lookup. Slack is specified in
     * pixels and converted to world units through the camera's scale, so it
     * belongs to the view the ray went through -- and on a sheet that is
     * whichever viewport the pointer is over, not the one that happens to be
     * active. Reading `this.camera` here silently used the wrong scale for
     * every hover over a viewport the reader had not clicked in. Likewise the
     * height that viewport is drawn at (`viewHeight`): measured against the
     * whole canvas, a sheet's views snapped at a fraction of their pixels.
     */
    _pickTolerances(worldPoint, camera, viewHeight) {
        return KigumiPickTolerances.pickTolerances(
            camera || this.camera, viewHeight || this._getRendererResolution().y, worldPoint);
    }

    _getRendererResolution() {
        return this.renderer ? this.renderer.getSize(new THREE.Vector2()) : new THREE.Vector2(1, 1);
    }

    createMaterialSetForMemberType(memberType) {
        const profileId = this.resolveRenderProfileIdForMemberType(memberType);
        const specs = this.renderProfileMaterialSpecs(this.resolveRenderProfile(profileId));
        return {
            profileId,
            solid: new THREE.MeshStandardMaterial(specs.solid),
            edge: new THREE.LineMaterial(specs.edge),
            reflection: new THREE.MeshStandardMaterial(specs.reflection),
        };
    }

    applyRenderProfileToBundle(bundle, profileId) {
        if (!bundle || !bundle.mesh || !bundle.mesh.material || !bundle.edges || !bundle.edges.material || !bundle.reflection || !bundle.reflection.material) {
            return;
        }
        const specs = this.renderProfileMaterialSpecs(this.resolveRenderProfile(profileId));
        bundle.profileId = profileId;
        this.applyMaterialSpec(bundle.mesh.material, specs.solid);
        this.applyMaterialSpec(bundle.edges.material, specs.edge);
        this.applyMaterialSpec(bundle.reflection.material, specs.reflection);
    }

    applyRenderProfilesToScene() {
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
            const metadata = this.memberMetadataByKey.get(memberKey) || { type: 'timber' };
            const profileId = this.resolveRenderProfileIdForMemberType(metadata.type);
            this.applyRenderProfileToBundle(bundle, profileId);
        }
    }

    createOrUpdateShadowCatcher(bounds) {
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const groundZ = bounds.minZ - 0.0005;
        this.groundZ = groundZ;
        this.shadowSize = Math.max(60, Math.max(dx, dy) * 8 || 60);

        if (!this.shadowCatcher) {
            this.shadowCatcher = new THREE.Mesh(
                new THREE.PlaneBufferGeometry(1, 1),
                new THREE.ShadowMaterial({ opacity: 0.22 })
            );
            this.shadowCatcher.receiveShadow = true;
            this.shadowCatcher.renderOrder = 1;
            this.scene.add(this.shadowCatcher);
        } else {
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.geometry = new THREE.PlaneBufferGeometry(1, 1);
        }

        this.shadowCatcher.position.set(centerX, centerY, groundZ + 0.0001);
        this.shadowCatcher.scale.set(this.shadowSize, this.shadowSize, 1);
        // Whether it is drawn is applyRenderMode's, on the next frame. This
        // builds the thing; it does not decide when it is wanted.
        this.updateReflectionTransforms();
        this.configureShadowCamera(bounds, this.shadowSize);
    }

    configureShadowCamera(bounds, size) {
        if (!this.sun || !this.sun.shadow || !this.sun.shadow.camera) {
            return;
        }
        const shadowCam = this.sun.shadow.camera;
        const half = size / 2;
        shadowCam.left = -half;
        shadowCam.right = half;
        shadowCam.top = half;
        shadowCam.bottom = -half;
        shadowCam.near = 0.5;
        shadowCam.far = Math.max(40, (bounds.maxZ - bounds.minZ) * 8 || 40);
        shadowCam.updateProjectionMatrix();
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const centerZ = (bounds.minZ + bounds.maxZ) / 2;
        this.sun.target.position.set(centerX, centerY, centerZ);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
    }

    getCameraSnapForDirection(direction) {
        return this.cameraController.getCameraSnapForDirection(direction);
    }

    snapCameraFromGizmoFace(localX, localY) {
        if (!this.cameraCube) {
            return;
        }
        const direction = this.cameraCube.axisAtPoint(localX, localY);
        if (!direction) {
            return;
        }
        const snap = this.getCameraSnapForDirection(direction);
        this.animateCameraTo(snap.offsetDir, this.cameraController.orbitDist, 260, snap.upVector);
    }

    syncLightAnglesFromSun() {
        if (!this.sun) {
            return;
        }
        const dx = this.sun.position.x - this.focusedCx;
        const dy = this.sun.position.y - this.focusedCy;
        const dz = this.sun.position.z - this.focusedCz;
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        this.lightDistance = distance;
        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = Math.max(0.2, Math.min(1.3, Math.asin(dz / distance)));
    }

    updateLightFromAngles() {
        if (!this.sun) {
            return;
        }
        const cosElevation = Math.cos(this.lightElevation);
        const dx = cosElevation * Math.cos(this.lightAzimuth) * this.lightDistance;
        const dy = cosElevation * Math.sin(this.lightAzimuth) * this.lightDistance;
        const dz = Math.sin(this.lightElevation) * this.lightDistance;

        this.sun.position.set(this.focusedCx + dx, this.focusedCy + dy, this.focusedCz + dz);
        this.sun.target.position.set(this.focusedCx, this.focusedCy, this.focusedCz);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
        this.configureShadowCamera(this.lastBounds, this.shadowSize || 60);
    }

    drawLightDial() {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        // Hidden, it has no size: drawn now it would be a pixel across when it comes back.
        if (!canvas || !canvas.clientWidth || !canvas.clientHeight) {
            return;
        }
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);

        const context = canvas.getContext('2d');
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.36;

        context.strokeStyle = 'rgba(88, 115, 166, 0.5)';
        context.lineWidth = 2;
        context.beginPath();
        context.arc(cx, cy, radius, 0, Math.PI * 2);
        context.stroke();

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const elevationRatio = (this.lightElevation - minElevation) / (maxElevation - minElevation);
        const knobRadius = radius * (1 - elevationRatio * 0.85);
        const knobX = cx + Math.cos(this.lightAzimuth) * knobRadius;
        const knobY = cy + Math.sin(this.lightAzimuth) * knobRadius;

        context.strokeStyle = 'rgba(88, 115, 166, 0.45)';
        context.lineWidth = 1.5;
        context.beginPath();
        context.moveTo(cx, cy);
        context.lineTo(knobX, knobY);
        context.stroke();

        context.fillStyle = '#5873a6';
        context.beginPath();
        context.arc(knobX, knobY, 5, 0, Math.PI * 2);
        context.fill();
    }

    applyLightDialFromPointer(event) {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        if (!canvas) {
            return;
        }
        const rect = canvas.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = event.clientX - cx;
        const dy = event.clientY - cy;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const maxDistance = Math.min(rect.width, rect.height) * 0.36;

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const clampedDistance = Math.min(maxDistance, distance);

        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = minElevation + (1 - clampedDistance / Math.max(1, maxDistance)) * (maxElevation - minElevation);
        this.updateLightFromAngles();
        this.drawLightDial();
    }

    // The true silhouette of a cylinder viewed by a point camera is exactly
    // two straight lines parallel to its axis (this holds exactly, not just
    // approximately, under perspective projection -- the tangency condition
    // works out to be independent of position along the axis).
    //
    // Those two lines sit at the radial direction u (pointing from the axis
    // straight at the camera) rotated by +/- acos(radius / d), where d is the
    // camera's distance from the axis line -- NOT at u itself (u projects to
    // the middle of the visible cylinder, bisecting it, rather than outlining
    // it). At typical viewing distances (d >> radius) that angle is close to
    // 90 degrees, but computing it exactly keeps close-up views correct too.
    //
    // Returns a flat 12-number [x,y,z, x,y,z, ...] array for
    // LineSegmentsGeometry.setPositions, or null if the camera is inside (or
    // on) the infinite cylindrical shell, where no real tangent lines exist.
    _silhouetteLinePositions(axisStart, axisEnd, radius, cameraPos) {
        const axisVec = new THREE.Vector3().subVectors(axisEnd, axisStart);
        const axisLen = axisVec.length();
        if (axisLen < 1e-9) {
            return null;
        }
        const axisDir = axisVec.divideScalar(axisLen);

        const toCam = new THREE.Vector3().subVectors(cameraPos, axisStart);
        const along = toCam.dot(axisDir);
        const w = toCam.sub(axisDir.clone().multiplyScalar(along)); // perpendicular component
        const d = w.length();
        if (d <= radius + 1e-9) {
            return null;
        }
        const u = w.divideScalar(d); // unit radial direction, axis -> camera
        const v = new THREE.Vector3().crossVectors(axisDir, u); // perpendicular to both

        const cosPhi = radius / d;
        const sinPhi = Math.sqrt(Math.max(0, 1 - cosPhi * cosPhi));
        const uPart = u.multiplyScalar(cosPhi);
        const n1 = new THREE.Vector3().addVectors(uPart, v.clone().multiplyScalar(sinPhi));
        const n2 = new THREE.Vector3().addVectors(uPart, v.multiplyScalar(-sinPhi));

        const offset1 = n1.multiplyScalar(radius);
        const offset2 = n2.multiplyScalar(radius);

        const p1a = new THREE.Vector3().addVectors(axisStart, offset1);
        const p1b = new THREE.Vector3().addVectors(axisEnd, offset1);
        const p2a = new THREE.Vector3().addVectors(axisStart, offset2);
        const p2b = new THREE.Vector3().addVectors(axisEnd, offset2);

        return [...p1a.toArray(), ...p1b.toArray(), ...p2a.toArray(), ...p2b.toArray()];
    }

    // Called every frame from the render loop -- recomputes the camera-facing
    // silhouette lines for every round accessory (see cylinderAxis / the
    // creation site in updateMeshScene).
    updateCylinderSilhouettes() {
        for (const bundle of this.sceneManager.bundles()) {
            const cyl = bundle.cylinderSilhouette;
            if (!cyl) {
                continue;
            }
            const positions = this._silhouetteLinePositions(cyl.axisStart, cyl.axisEnd, cyl.radius, this.camera.position);
            if (!positions) {
                continue;
            }
            cyl.line.geometry.setPositions(positions);
            cyl.line.computeLineDistances();
        }
    }
};
