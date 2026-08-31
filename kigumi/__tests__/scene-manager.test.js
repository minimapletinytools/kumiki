const { SceneManager } = require('../webview/scene-manager.js');

function fakeMesh(name) {
    return {
        name,
        visible: true,
        castShadow: false,
        geometry: { dispose: jest.fn() },
        material: { dispose: jest.fn(), transparent: false, opacity: 1 },
    };
}

function fakeBundle(name) {
    return {
        memberType: 'timber',
        profileId: 'timber-warm',
        mesh: fakeMesh(`${name}-solid`),
        edges: fakeMesh(`${name}-edges`),
        reflection: fakeMesh(`${name}-reflection`),
    };
}

function manager() {
    const scene = { removed: [], remove(object) { this.removed.push(object); } };
    return { scene, sceneManager: new SceneManager({ THREE: {}, scene }) };
}

describe('the member registry', () => {
    test('a registered member can be found again', () => {
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);
        expect(sceneManager.get('post#0')).toBe(bundle);
        expect(sceneManager.has('post#0')).toBe(true);
        expect(sceneManager.size).toBe(1);
    });

    test('disposing a member releases what it held and forgets it', () => {
        const { sceneManager, scene } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        sceneManager.disposeMember('post#0');

        expect(bundle.mesh.geometry.dispose).toHaveBeenCalled();
        expect(bundle.mesh.material.dispose).toHaveBeenCalled();
        expect(scene.removed).toContain(bundle.mesh);
        expect(sceneManager.has('post#0')).toBe(false);
        // and the reverse lookup goes with it, or a stale mesh could still
        // claim to be a member
        expect(sceneManager.memberForObject(bundle.mesh)).toBeUndefined();
    });

    test('disposing everything leaves nothing behind', () => {
        const { sceneManager } = manager();
        sceneManager.register('a', fakeBundle('a'));
        sceneManager.register('b', fakeBundle('b'));
        sceneManager.disposeAll();
        expect(sceneManager.size).toBe(0);
    });
});

describe('picking, which answers with member keys', () => {
    function raycasterHitting(...meshes) {
        return { intersectObjects: (targets) => meshes
            .filter((mesh) => targets.includes(mesh))
            .map((mesh) => ({ object: mesh, distance: 1 })) };
    }

    test('a ray reports the member, not the mesh it happened to hit', () => {
        // A caller that unwrapped a mesh could not survive those meshes being
        // merged, which is the point of answering this way.
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        const hits = sceneManager.memberAtRay(raycasterHitting(bundle.mesh));

        expect(hits).toHaveLength(1);
        expect(hits[0].memberKey).toBe('post#0');
    });

    test('members the caller rules out are never offered to the ray', () => {
        const { sceneManager } = manager();
        const hidden = fakeBundle('hidden');
        const visible = fakeBundle('visible');
        sceneManager.register('hidden#0', hidden);
        sceneManager.register('visible#0', visible);

        const hits = sceneManager.memberAtRay(
            raycasterHitting(hidden.mesh, visible.mesh),
            { isPickable: (key) => key !== 'hidden#0' },
        );

        expect(hits.map((entry) => entry.memberKey)).toEqual(['visible#0']);
    });

    test('a hit on something unregistered is dropped rather than guessed at', () => {
        const { sceneManager } = manager();
        sceneManager.register('post#0', fakeBundle('post'));
        expect(sceneManager.memberAtRay(raycasterHitting(fakeMesh('stray')))).toEqual([]);
    });
});

describe('appearance, which takes a class as well as numbers', () => {
    const APPEARANCE = {
        name: 'ghost',
        opacity: 0.2,
        edgeOpacity: 0.8,
        edgesVisible: true,
        reflectionOpacity: 0.1,
        reflectionsVisible: true,
    };

    test('the numbers reach the mesh, its edges and its reflection', () => {
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        sceneManager.setMemberAppearance('post#0', APPEARANCE);

        expect(bundle.mesh.material.opacity).toBe(0.2);
        expect(bundle.mesh.material.transparent).toBe(true);
        expect(bundle.edges.material.opacity).toBe(0.8);
        expect(bundle.reflection.material.opacity).toBe(0.1);
    });

    test('a transparent member casts no shadow', () => {
        // It would be a solid shadow under something you can see through.
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        sceneManager.setMemberAppearance('post#0', APPEARANCE);
        expect(bundle.mesh.castShadow).toBe(false);

        sceneManager.setMemberAppearance('post#0', { ...APPEARANCE, name: 'normal', opacity: 1 });
        expect(bundle.mesh.castShadow).toBe(true);
    });

    test('hidden hides everything the member draws', () => {
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        sceneManager.setMemberAppearance('post#0', { ...APPEARANCE, name: 'hidden' });

        expect(bundle.mesh.visible).toBe(false);
        expect(bundle.edges.visible).toBe(false);
        expect(bundle.reflection.visible).toBe(false);
    });

    test('edges and reflections can be off without the member being hidden', () => {
        const { sceneManager } = manager();
        const bundle = fakeBundle('post');
        sceneManager.register('post#0', bundle);

        sceneManager.setMemberAppearance('post#0', {
            ...APPEARANCE, name: 'normal', edgesVisible: false, reflectionsVisible: false,
        });

        expect(bundle.mesh.visible).toBe(true);
        expect(bundle.edges.visible).toBe(false);
        expect(bundle.reflection.visible).toBe(false);
    });

    test('dressing a member that is not there is survivable', () => {
        const { sceneManager } = manager();
        expect(() => sceneManager.setMemberAppearance('nobody', APPEARANCE)).not.toThrow();
    });
});
