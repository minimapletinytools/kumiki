// Editing a drawing's layout on the sheet: the edit button starts it, a click picks out a view, then
// split, float, resize, a divider moved, a dock (with where it will land shown first, and every view
// it resizes fitted), a drag let go of with Escape, a face picked and looked at, a camera preset, a
// quarter turn, the wheel and a middle drag on the view, a fit, undo back to the code's, and Escape
// ends it.
module.exports = {
    name: 'layout-edit',
    async run({ check, inShell, waitFor, capture, runAppCommand, viewDoc, DRAWING_FRAME }) {
        await runAppCommand('kigumi.openFrameFromSidebar', DRAWING_FRAME);
        const app = `${viewDoc}.querySelector("kigumi-app")`;
        const drawingId = await waitFor(() => inShell(`(() => {
            const a = ${app};
            const drawings = a && a.sceneStore ? a.sceneStore.drawings() : [];
            return drawings.length && Array.from(a.sceneManager.bundles()).length ? drawings[drawings.length - 1].id : null;
        })()`), { timeoutMs: 90000 });
        await inShell(`${app}.enterDrawing(${JSON.stringify(drawingId)})`);
        const frame = 'new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 300))))';
        await inShell(frame);
        const info = await inShell(`(() => { const a = ${app}; const s = a.sceneStore.activeScene();
            return { layout: !!s.layout, ids: a.viewports.map(v => v.id), origin: s.origin }; })()`);
        check('the drawing carries its layout', info.layout, JSON.stringify(info));
        const first = info.ids.find(id => !/preview/i.test(id)) || info.ids[0];

        await capture('00-edit-button');
        await inShell(`${app}.renderRoot.querySelector('#layout-edit-btn').click()`);
        await inShell(frame);
        check('the edit button starts editing the layout', await inShell(`${app}.layoutEditing === true`));

        // Click on a view's empty corner: the view is picked out.
        await inShell(`(() => { const a = ${app};
            const host = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const page = a.pageScreenRect(host.width, host.height);
            const r = view.pixelRect(page, host.height);
            const x = host.left + r.x + 6, y = host.top + (host.height - r.y - r.height) + 6;
            a.handleCanvasClick({ clientX: x, clientY: y, shiftKey: false });
        })()`);
        const picked = await waitFor(() => inShell(`${app}.layoutSelection`), { timeoutMs: 10000 }).catch(() => null);
        check('a click in a view picks it out', picked === first, String(picked));
        await inShell(frame);
        await capture('01-selected');

        const press = (selector, index, dx, dy, { capturing } = {}) => inShell(`(async () => { const a = ${app};
            const el = a.renderRoot.querySelectorAll(${JSON.stringify(selector)})[${index}];
            if (!el) return 'missing';
            const b = el.getBoundingClientRect();
            const win = a.ownerDocument.defaultView;
            const x = b.left + b.width / 2, y = b.top + b.height / 2;
            el.dispatchEvent(new win.PointerEvent('pointerdown', { bubbles: true, clientX: x, clientY: y }));
            if (${dx} || ${dy}) {
                for (let step = 1; step <= 5; step += 1) {
                    win.dispatchEvent(new win.PointerEvent('pointermove', { clientX: x + ${dx} * step / 5, clientY: y + ${dy} * step / 5 }));
                }
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                if (${Boolean(capturing)}) return 'held';
                win.dispatchEvent(new win.PointerEvent('pointerup', { clientX: x + ${dx}, clientY: y + ${dy} }));
            }
            return 'ok';
        })()`);
        const release = () => inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.PointerEvent('pointerup', {})); })()`);
        const count = () => inShell(`${app}.viewports.length`);

        const before = await count();
        await press('.vp-tool', 0, 0, 0);
        const split = await waitFor(() => inShell(`(() => { const a = ${app}; return a.viewports.length > ${before} && a.viewports.some(v => v.id === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('splitting a view adds a copy beside it', split);
        await inShell(frame);
        await capture('02-split');

        // Drag the copy's grip to the middle of the preview, clear of any view's edge: it floats there.
        await inShell(`${app}.selectDrawingViewport(${JSON.stringify(first + ' 2')})`);
        await inShell(frame);
        const host = await inShell(`(() => { const a = ${app}; const h = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => /preview/i.test(v.id)) || a.viewports[a.viewports.length - 1];
            const r = view.pixelRect(a.pageScreenRect(h.width, h.height), h.height);
            const g = a.renderRoot.querySelector('.vp-grip').getBoundingClientRect();
            return { cx: h.left + r.x + r.width / 2 - (g.left + g.width / 2), cy: h.top + (h.height - r.y - r.height / 2) - (g.top + g.height / 2) }; })()`);
        await press('.vp-grip', 0, Math.round(host.cx), Math.round(host.cy));
        const floated = await waitFor(() => inShell(`(() => { const a = ${app}; const l = a.sceneStore.activeScene().layout;
            return !a._layoutDraft && l.roots.some(r => r.leaf === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('a view dragged off the grid floats', floated);
        await inShell(frame);
        await capture('03-floated');

        // Resize it from a corner.
        await press('.vp-handle-se', 0, 60, 40);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);
        await inShell(frame);
        await capture('04-resized');

        // Move a divider.
        await press('.vp-divider-columns', 0, -60, 0);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);
        await inShell(frame);
        await capture('05-divider');

        // Where the grip is, and how to hold the floating view at a point and read what a drop there would do.
        const holdAt = async (point) => {
            await inShell(frame);
            const grip = await inShell(`(() => { const el = ${app}.renderRoot.querySelector('.vp-grip');
                if (!el) return { missing: { editing: ${app}.layoutEditing, selected: ${app}.layoutSelection, draft: !!${app}._layoutDraft } };
                const g = el.getBoundingClientRect(); return { x: g.left + g.width / 2, y: g.top + g.height / 2 }; })()`);
            if (grip.missing) return { gripMissing: grip.missing };
            await press('.vp-grip', 0, Math.round(point.x - grip.x), Math.round(point.y - grip.y), { capturing: true });
            await inShell(frame);
            return inShell(`(() => { const d = ${app}._layoutDraft; return d && d.drop ? { kind: d.drop.kind, target: d.drop.target, side: d.drop.side } : null; })()`);
        };
        const escape = () => inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()`);
        const geometry = await inShell(`(() => { const a = ${app}; const h = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const page = a.pageScreenRect(h.width, h.height);
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const r = view.pixelRect(page, h.height);
            const divider = a.renderRoot.querySelector('.vp-divider-rows');
            const d = divider ? divider.getBoundingClientRect() : null;
            return { right: { x: h.left + r.x + r.width - 30, y: h.top + (h.height - r.y - r.height / 2) },
                divider: d ? { x: d.left + d.width / 2, y: d.top + d.height / 2 } : null,
                sheet: { x: h.left + page.x + page.width / 2, y: h.top + page.y + page.height + 15 },
                end: { x: h.left + page.x + page.width * 0.2, y: h.top + page.y + page.height - 6 } }; })()`);

        // On a divider: one more in that column. Along the sheet's edge: a new row. Let go of both.
        const onDivider = geometry.divider ? await holdAt(geometry.divider) : null;
        check('held on a divider, it would join that row or column', onDivider && onDivider.kind === 'insert', JSON.stringify(onDivider));
        await capture('06-drop-divider');
        await escape();
        await release();
        const onSheet = await holdAt(geometry.sheet);
        check('held just outside the sheet, it would be a new row', onSheet && onSheet.kind === 'sheet', JSON.stringify(onSheet));
        await capture('06-drop-sheet');
        await escape();
        await release();
        // Just inside the bottom of the last view in a column: one more at that column's end.
        const atEnd = await holdAt(geometry.end);
        check('held just inside a column\'s last view, it would go at that column\'s end', atEnd && atEnd.kind === 'insert', JSON.stringify(atEnd));
        await capture('06-drop-end');
        await escape();
        await release();

        // Near the first view's edge: a split of it, docked there when let go.
        const drop = await holdAt(geometry.right);
        check('held near a view\'s edge, it would split that view', drop && drop.kind === 'split' && drop.target === first && drop.side === 'right', JSON.stringify(drop));
        await capture('06-drop-split');
        await release();
        const docked = await waitFor(() => inShell(`(() => { const a = ${app}; const l = a.sceneStore.activeScene().layout;
            return !a._layoutDraft && !l.roots.some(r => r.leaf === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('let go there, it docks beside that view', docked);
        // The view it was docked beside was squeezed to make room: it is fitted again too.
        const leafCamera = (name) => `(() => { const walk = (n) => n.leaf === ${JSON.stringify(name)} ? n
            : n.split ? n.split.portions.map(p => walk(p.node)).find(Boolean) : null;
            const l = ${app}.sceneStore.activeScene().layout;
            const found = l.roots.map(walk).find(Boolean); return found ? found.camera || null : null; })()`;
        const squeezed = await inShell(leafCamera(first));
        check('a view pushed aside is fitted again', squeezed && squeezed.look && !squeezed.extent, JSON.stringify(squeezed));
        await inShell(frame);
        await capture('07-docked');

        // Escape lets go of a drag and leaves the layout as it was.
        await inShell(`${app}.selectDrawingViewport(${JSON.stringify(first)})`);
        await inShell(frame);
        const layoutBefore = await inShell(`JSON.stringify(${app}.sceneStore.activeScene().layout)`);
        await press('.vp-grip', 0, 80, 60, { capturing: true });
        await inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()`);
        await release();
        await inShell('new Promise(r => setTimeout(r, 500))');
        const kept = await inShell(`(() => { const a = ${app}; return !a._layoutDraft && a.layoutEditing && JSON.stringify(a.sceneStore.activeScene().layout) === ${JSON.stringify(layoutBefore)}; })()`);
        check('escape during a drag lets go of it, still editing', kept);

        // Only a face can be picked while editing: click on a member in the view, then look at that face.
        const onMember = await inShell(`(() => { const a = ${app};
            const host = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const drawn = a.activeSceneMembers;
            const entry = Array.from(a.sceneManager.membersByKey.entries()).find(([key, b]) => b.mesh && (!drawn || drawn.has(key)));
            if (!entry) return null;
            const mesh = entry[1].mesh;
            mesh.geometry.computeBoundingBox();
            const centre = mesh.geometry.boundingBox.getCenter(mesh.geometry.boundingBox.min.clone()).applyMatrix4(mesh.matrixWorld);
            const ndc = centre.project(view.camera);
            const r = view.pixelRect(a.pageScreenRect(host.width, host.height), host.height);
            const x = host.left + r.x + (ndc.x + 1) / 2 * r.width, y = host.top + (host.height - r.y - r.height) + (1 - ndc.y) / 2 * r.height;
            a.handleCanvasClick({ clientX: x, clientY: y, shiftKey: false });
            return [x, y];
        })()`);
        const face = await waitFor(() => inShell(`(() => { const d = ${app}.lastPickDetail; return d && d.featureType ? d : null; })()`), { timeoutMs: 15000 }).catch(() => null);
        check('a click while editing takes a face', face && face.featureType === 'FACE' && Array.isArray(face.worldNormal), JSON.stringify({ onMember, face }));
        await inShell(frame);
        await capture('08-face');
        await press('.vp-tool-camera', 0, 0, 0);
        const faceItem = await inShell(`(() => { const m = ${app}.contextMenu; const item = (m.items || (m.state && m.state.items) || []).find(i => i.id === 'face'); return item ? !item.disabled : null; })()`);
        await inShell(`${app}.contextMenu.choose('face')`);
        const facing = face && face.worldNormal ? await waitFor(() => inShell(`(() => { const a = ${app}; const v = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const n = ${JSON.stringify(face.worldNormal)};
            return !a._layoutDraft && v && v.spec.camera.look.every((c, i) => Math.abs(c + n[i]) < 1e-6); })()`), { timeoutMs: 15000 }).catch(() => false) : false;
        check('the selected face can be looked at square on', facing, JSON.stringify({ faceItem }));

        // Turn the view to look down from the top, then fit it.
        await press('.vp-tool-camera', 0, 0, 0);
        await inShell(`${app}.contextMenu.choose('top')`);
        const turned = await waitFor(() => inShell(`(() => { const a = ${app}; const v = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            return !a._layoutDraft && v && Math.abs(v.spec.camera.look[2] + 1) < 1e-6; })()`), { timeoutMs: 15000 }).catch(() => false);
        check('a camera preset turns the view', turned);
        await inShell(frame);
        await capture('09-top');

        // A quarter turn: from the top, the camera goes round to the right and looks back along -x.
        await press('.vp-tool-orbit-right', 0, 0, 0);
        const quarter = await waitFor(() => inShell(`(() => { const a = ${app}; const v = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            return !a._layoutDraft && v && Math.abs(v.spec.camera.look[0] + 1) < 1e-6; })()`), { timeoutMs: 15000 }).catch(() => false);
        check('the turning buttons turn the camera a quarter turn', quarter);
        // Its measurements were made looking the other way: kept on that plane, so not drawn here.
        const stale = await inShell(`(() => { const v = ${app}.viewports.find(v => v.id === ${JSON.stringify(first)});
            const look = v.spec.camera.look; const ms = v.spec.measurements || [];
            return { count: ms.length, offPlane: ms.filter(m => m.plane && Math.abs(m.plane.normal.reduce((sum, c, i) => sum + c * look[i], 0)) < 0.5).length }; })()`);
        check('a turned view\'s old measurements no longer match it', stale.count > 0 && stale.offPlane === stale.count, JSON.stringify(stale));
        await inShell(frame);
        await capture('10-turned');

        // The wheel zooms the view, and a middle drag pans it, not the sheet.
        const middleOf = `(() => { const a = ${app}; const host = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const r = view.pixelRect(a.pageScreenRect(host.width, host.height), host.height);
            return { x: host.left + r.x + r.width / 2, y: host.top + (host.height - r.y - r.height / 2) }; })()`;
        const camera = () => inShell(`(() => { const v = ${app}.viewports.find(v => v.id === ${JSON.stringify(first)}); return { extent: v.spec.camera.extent, target: v.spec.camera.target }; })()`);
        const mid = await inShell(middleOf);
        const beforeWheel = await camera();
        await inShell(`(() => { const a = ${app}; const win = a.ownerDocument.defaultView;
            a.renderRoot.querySelector('#viewport').dispatchEvent(new win.WheelEvent('wheel', { bubbles: true, cancelable: true, clientX: ${mid.x}, clientY: ${mid.y}, deltaY: -100 })); })()`);
        const afterWheel = await camera();
        check('the wheel zooms the selected view', afterWheel.extent < beforeWheel.extent, JSON.stringify({ beforeWheel, afterWheel }));
        const pageBefore = await inShell(`JSON.stringify(${app}.pageView || null)`);
        await inShell(`(() => { const a = ${app}; const win = a.ownerDocument.defaultView; const c = a.renderRoot.querySelector('#c');
            c.dispatchEvent(new win.MouseEvent('mousedown', { bubbles: true, button: 1, clientX: ${mid.x}, clientY: ${mid.y} }));
            for (let step = 1; step <= 5; step += 1) win.dispatchEvent(new win.MouseEvent('mousemove', { clientX: ${mid.x} + step * 10, clientY: ${mid.y} }));
            win.dispatchEvent(new win.MouseEvent('mouseup', { button: 1, clientX: ${mid.x} + 50, clientY: ${mid.y} })); })()`);
        const afterPan = await camera();
        const pageAfter = await inShell(`JSON.stringify(${app}.pageView || null)`);
        check('a middle drag pans the selected view, not the sheet',
            afterPan.target.some((c, i) => Math.abs(c - afterWheel.target[i]) > 1e-9) && pageAfter === pageBefore,
            JSON.stringify({ afterWheel, afterPan, pageBefore, pageAfter }));
        await waitFor(() => inShell(`(() => { const a = ${app}; return !a._layoutDraft && a.viewports.find(v => v.id === ${JSON.stringify(first)}).spec.camera.extent < ${beforeWheel.extent}; })()`), { timeoutMs: 15000 }).catch(() => null);
        await inShell('new Promise(r => setTimeout(r, 800))');
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);

        await press('.vp-tool-fit', 0, 0, 0);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);

        // Undo everything back to the code's layout.
        // Each undo waits for the runner's answer, which is slower on CI.
        for (let i = 0; i < 40 && await inShell(`${app}.sceneStore.activeScene().layoutEdited`); i += 1) {
            const was = await inShell(`JSON.stringify(${app}.sceneStore.activeScene().layout)`);
            await inShell(`${app}.undoMeasurementChange()`);
            await waitFor(() => inShell(`JSON.stringify(${app}.sceneStore.activeScene().layout) !== ${JSON.stringify(was)}`), { timeoutMs: 15000 }).catch(() => null);
        }
        const undone = await inShell(`(() => { const a = ${app}; return { edited: a.sceneStore.activeScene().layoutEdited, ids: a.viewports.map(v => v.id) }; })()`);
        check('undo puts the code layout back', !undone.edited && undone.ids.join() === info.ids.join(), JSON.stringify(undone));
        await inShell(frame);
        await capture('11-undone');

        await inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()`);
        check('escape ends editing', await inShell(`${app}.layoutEditing === false`));
    },
};
