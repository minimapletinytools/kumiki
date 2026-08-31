(function (globalScope) {
    'use strict';
    // What a member is on screen: the mapping from a member key to the objects
    // that draw it.
    //
    // Everything else asks this rather than reaching into a bundle, and that is
    // the point. Two rules make batched geometry possible later without
    // touching anything but this file:
    //
    //   - picking goes through memberAtRay, which answers with a member key
    //     rather than a mesh, so an implementation that draws a thousand
    //     members in one call can still say which one was hit;
    //   - appearance goes through setMemberAppearance, which takes the name of
    //     a class as well as the numbers, so an implementation that shares one
    //     material per class has the name it needs to group by.
    //
    // Today both do the straightforward thing: one mesh per member, and
    // properties written per member. Nothing depends on that.

    class SceneManager {
        constructor({ THREE, scene }) {
            this.THREE = THREE;
            this.scene = scene;
            // memberKey -> { mesh, edges, reflection, cylinderSilhouette, profileId }
            this.membersByKey = new Map();
            // The reverse, for turning a raycast hit back into a member.
            this.keysByObject = new Map();
        }

        setScene(scene) {
            this.scene = scene;
        }

        register(memberKey, bundle) {
            this.membersByKey.set(memberKey, bundle);
            if (bundle && bundle.mesh) {
                this.keysByObject.set(bundle.mesh, memberKey);
            }
        }

        get(memberKey) {
            return this.membersByKey.get(memberKey);
        }

        has(memberKey) {
            return this.membersByKey.has(memberKey);
        }

        keys() {
            return this.membersByKey.keys();
        }

        entries() {
            return this.membersByKey.entries();
        }

        bundles() {
            return this.membersByKey.values();
        }

        get size() {
            return this.membersByKey.size;
        }

        /** The member a rendered object belongs to, or undefined. */
        memberForObject(object) {
            return this.keysByObject.get(object);
        }

        /**
         * Every member a ray passes through, nearest first.
         *
         * Answers with member keys rather than meshes: what draws a member is
         * this file's business, and a caller that had to unwrap a mesh could
         * not survive those meshes being merged.
         */
        memberAtRay(raycaster, { isPickable } = {}) {
            const targets = [];
            for (const [memberKey, bundle] of this.membersByKey.entries()) {
                if (isPickable && !isPickable(memberKey)) {
                    continue;
                }
                if (bundle && bundle.mesh) {
                    targets.push(bundle.mesh);
                }
            }

            const hits = [];
            for (const hit of raycaster.intersectObjects(targets, false)) {
                const memberKey = this.keysByObject.get(hit.object);
                if (memberKey) {
                    hits.push({ memberKey, hit });
                }
            }
            return hits;
        }

        /**
         * How one member should look.
         *
         * `appearance.name` says which class it is -- normal, selected, ghost,
         * hidden -- and the rest are the numbers that class resolves to. The
         * name is not used here yet; it is what a materials-shared-by-class
         * implementation would group on.
         */
        setMemberAppearance(memberKey, appearance) {
            const bundle = this.membersByKey.get(memberKey);
            if (!bundle) {
                return;
            }
            const visible = appearance.name !== 'hidden';

            if (bundle.mesh) {
                const transparent = appearance.opacity < 1;
                bundle.mesh.visible = visible;
                bundle.mesh.material.transparent = transparent;
                bundle.mesh.material.opacity = appearance.opacity;
                // A transparent member casts no shadow: it would be a solid
                // shadow under something you can see through.
                bundle.mesh.castShadow = visible && !transparent;
            }

            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.opacity = appearance.edgeOpacity;
                bundle.edges.visible = visible && appearance.edgesVisible;
            }

            if (bundle.reflection && bundle.reflection.material) {
                bundle.reflection.material.opacity = appearance.reflectionOpacity;
                bundle.reflection.visible = visible && appearance.reflectionsVisible;
            }
        }

        /** Take a member off the scene and give back what it held. */
        disposeMember(memberKey) {
            const bundle = this.membersByKey.get(memberKey);
            if (!bundle) {
                return;
            }
            this.disposeBundle(bundle);
            this.membersByKey.delete(memberKey);
            if (bundle.mesh) {
                this.keysByObject.delete(bundle.mesh);
            }
        }

        disposeBundle(bundle) {
            if (!bundle) {
                return;
            }
            if (this.scene) {
                this.scene.remove(bundle.mesh);
                this.scene.remove(bundle.edges);
                if (bundle.reflection) {
                    this.scene.remove(bundle.reflection);
                }
            }
            if (bundle.mesh) {
                bundle.mesh.geometry.dispose();
                if (bundle.mesh.material && typeof bundle.mesh.material.dispose === 'function') {
                    bundle.mesh.material.dispose();
                }
            }
            if (bundle.edges) {
                bundle.edges.geometry.dispose();
                if (bundle.edges.material && typeof bundle.edges.material.dispose === 'function') {
                    bundle.edges.material.dispose();
                }
            }
            if (bundle.reflection && bundle.reflection.material
                && typeof bundle.reflection.material.dispose === 'function') {
                bundle.reflection.material.dispose();
            }
            // cylinderSilhouette.line is a child of bundle.edges (removed
            // above) and shares its material (disposed above) -- only its own
            // geometry is left to release.
            if (bundle.cylinderSilhouette) {
                bundle.cylinderSilhouette.line.geometry.dispose();
            }
        }

        disposeAll() {
            for (const bundle of this.membersByKey.values()) {
                this.disposeBundle(bundle);
            }
            this.membersByKey.clear();
            this.keysByObject.clear();
        }
    }

    const KigumiSceneManager = { SceneManager };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiSceneManager;
    }
    globalScope.KigumiSceneManager = KigumiSceneManager;
})(typeof window !== 'undefined' ? window : globalThis);
