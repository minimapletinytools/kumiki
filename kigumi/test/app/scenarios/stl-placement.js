const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'stl-placement',
    async run({ check, inShell, waitFor, sleep, capture, openFrame, viewDoc, REPO, clipboard, window }) {
        const folder = path.join(REPO, '.kigumi', 'automation');
        fs.mkdirSync(folder, { recursive: true });
        const file = path.join(folder, 'stl_placement_test.py');
        const asset = path.join(REPO, 'patterns', 'assets', 'cabriole_leg.stl');
        const source = `from kumiki import *\n\n@frame\ndef leg(k: Optional[Kiwari] = None) -> Frame:\n    ref = create_timber(length=.72, size=create_v2(.07, .07), bottom_position=create_v3(0, 0, 0), length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=TimberTicket('leg'))\n    stock = create_stl_timber(ref, ${JSON.stringify(asset)})\n    return Frame.from_joints([], additional_unjointed_timbers=[stock])\n`;
        fs.writeFileSync(file, source);
        try {
            await openFrame(file);
            await waitFor(() => inShell(`${viewDoc}.querySelector('#layers-view .lp-row-timber')?.textContent.includes('(needs stl placement)')`));
            check('placeholder has a placement suffix in the tree', true);
            await waitFor(() => inShell(`[...${viewDoc}.querySelector('kigumi-app').memberMetadataByKey.values()].some(m => m.mesh?.stlPlacement)`));
            await inShell(`${viewDoc}.querySelector('#layers-view .lp-row-timber').click()`);
            await sleep(200);
            check('selecting a placeholder stays in the ordinary viewer', await inShell(`!${viewDoc}.querySelector('kigumi-app').stlEditor`));
            await inShell(`[...${viewDoc}.querySelectorAll('#info-panel button')].find(b => b.textContent === 'Edit STL placement').click()`);
            await waitFor(() => inShell(`!!${viewDoc}.querySelector('[data-stl-placement-editor] canvas')`));
            check('edit button enters isolated placement', await inShell(`${viewDoc}.querySelector('kigumi-app').stlEditor.suspended.every(([element]) => element.inert)`));
            await capture('stl-placement-editor');
            await inShell(`(() => {
                const doc = ${viewDoc};
                const button = [...doc.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'X +90°'); button.click();
                const input = doc.querySelector('[aria-label="Translation (m) X"]'); input.value = '0.025'; input.dispatchEvent(new Event('change'));
            })()`);
            check('quarter turns and fine translation reach the preview', await inShell(`(() => { const e = ${viewDoc}.querySelector('kigumi-app').stlEditor; return Math.abs(e.value.rotation[0] - 90) < 1e-8 && e.mesh.position.x === .025; })()`));
            await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'Copy configuration').click()`);
            await waitFor(async () => (await clipboard.readText()).startsWith('placement='));
            check('configuration can be copied', (await clipboard.readText()).includes('0.025'));
            await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'Cancel').click()`);
            check('cancel restores the viewer without editing source', fs.readFileSync(file, 'utf8') === source && await inShell(`!${viewDoc}.querySelector('[data-stl-placement-editor]')`));
            await inShell(`[...${viewDoc}.querySelectorAll('#info-panel button')].find(b => b.textContent === 'Edit STL placement').click()`);
            await waitFor(() => inShell(`!!${viewDoc}.querySelector('[data-stl-placement-editor] canvas')`));
            // A real pointer drag on the translation handle, through Electron's input pipeline.
            const handle = await inShell(`(() => {
                const doc = ${viewDoc}, editor = doc.querySelector('kigumi-app').stlEditor;
                const knob = editor.gizmo.children.find(o => o.userData.axis === 0);
                const p = knob.getWorldPosition(knob.position.clone()).project(editor.camera);
                const rect = editor.renderer.domElement.getBoundingClientRect();
                const iframe = document.querySelector('#slot-center iframe:not([hidden])').getBoundingClientRect();
                return { x: Math.round(iframe.left + rect.left + (p.x + 1) * rect.width / 2), y: Math.round(iframe.top + rect.top + (1 - p.y) * rect.height / 2) };
            })()`);
            window().webContents.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...handle });
            window().webContents.sendInputEvent({ type: 'mouseMove', x: handle.x + 35, y: handle.y + 10 });
            window().webContents.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, x: handle.x + 35, y: handle.y + 10 });
            await waitFor(() => inShell(`${viewDoc}.querySelector('kigumi-app').stlEditor.value.translation[0] !== 0`));
            check('translation gizmo responds to a pointer drag', true);
            for (const mode of ['Rotate', 'Scale', 'Uniform']) {
                await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'Reset').click()`);
                await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === '${mode === 'Uniform' ? 'Scale' : mode}').click()`);
                const points = await inShell(`(() => {
                    const e = ${viewDoc}.querySelector('kigumi-app').stlEditor;
                    const rect = e.renderer.domElement.getBoundingClientRect();
                    const iframe = document.querySelector('#slot-center iframe:not([hidden])').getBoundingClientRect();
                    const screen = p => { p.project(e.camera); return {x: Math.round(iframe.left + rect.left + (p.x+1)*rect.width/2), y: Math.round(iframe.top + rect.top + (1-p.y)*rect.height/2)}; };
                    const length = e.gizmoSize;
                    if (e.mode === 'rotation') return [screen(e.mesh.position.clone().set(length/Math.sqrt(2),length/Math.sqrt(2),0)), screen(e.mesh.position.clone().set(-length/Math.sqrt(2),length/Math.sqrt(2),0))];
                    const knob = e.gizmo.children.find(o => ${mode === 'Uniform' ? 'o.userData.uniformScale' : 'o.userData.axis === 0'});
                    const a = screen(knob.getWorldPosition(knob.position.clone()));
                    return [a, {x:a.x-40, y:a.y+10}];
                })()`);
                window().webContents.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...points[0]});
                window().webContents.sendInputEvent({type:'mouseMove',...points[1]});
                window().webContents.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...points[1]});
                await waitFor(() => inShell(`(() => {const e = ${viewDoc}.querySelector('kigumi-app').stlEditor; return e.mode === 'rotation' ? Math.abs(e.value.rotation[2]) > 30 : Math.abs(e.value.scale[0]-1) > .01;})()`));
                check(mode.toLowerCase() + ' gizmo responds to a pointer drag', true);
                if (mode !== 'Rotate') check(mode === 'Uniform' ? 'center box scales all axes equally' : 'axis box scales only one axis', await inShell(`(() => {
                    const s = ${viewDoc}.querySelector('kigumi-app').stlEditor.value.scale;
                    return ${mode === 'Uniform' ? 's[0] === s[1] && s[1] === s[2]' : 's[1] === 1 && s[2] === 1'};
                })()`));
                if (mode === 'Uniform') { await sleep(100); await capture('stl-center-scale'); }
            }

            await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'Reset').click()`);
            await inShell(`[...${viewDoc}.querySelectorAll('[data-stl-placement-editor] button')].find(b => b.textContent === 'Update configuration').click()`);
            await waitFor(() => fs.readFileSync(file, 'utf8').includes('placement='));
            await waitFor(() => inShell(`!${viewDoc}.querySelector('[data-stl-placement-editor]') && !${viewDoc}.querySelector('#layers-view .lp-row-timber')?.textContent.includes('(needs stl placement)')`));
            check('updating writes the unique call and rebuilds as STL geometry', true);
            await capture('stl-placement-applied');
            await openFrame(path.join(REPO, 'patterns', 'structures', 'cabriole_table.py'));
            await waitFor(() => inShell(`${viewDoc}.querySelector('kigumi-app').memberMetadataByKey.size >= 6`));
            await capture('cabriole-table');
        } finally { fs.rmSync(file, { force: true }); }
    },
};
