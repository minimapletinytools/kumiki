// Which member is frontmost at each pixel of a viewport.
//
// Depth says how far the nearest surface is; this says whose it is. That is what drawing over a
// timber needs and depth cannot give: a line inside a timber -- a perfect face, a centerline --
// should be hidden by another timber in front of it, never by its own faces around it.
//
// Every member gets a small integer id and an id mesh: a child of its solid mesh, sharing its
// geometry, flat-coloured with the id, on a layer of its own. So it moves, and hides, with its
// member, and the normal render never sees it. render() draws that layer into a render target
// per viewport; a shader asks it per fragment (clipLineMaterial), and the CPU per pixel (idAt).
//
// Only the frontmost surface per pixel, at the viewport's resolution: what is second needs the
// CPU ray, and a test at a silhouette should look a pixel or two around (clipLineMaterial does).

/** The layer id meshes live on; the main render keeps cameras on layer 0. */
const ID_LAYER = 31;
/** 0 is background: nothing drawn there. Member ids count from 1. */
const BACKGROUND = 0;

/** An id as an RGB colour, 8 bits a channel: 16 million members before it wraps. */
function idToRgb(id) {
    return [id & 0xff, (id >> 8) & 0xff, (id >> 16) & 0xff];
}

/** The id a pixel read back from the render target holds. */
function rgbToId(r, g, b) {
    return r + (g << 8) + (b << 16);
}

// Decoded in the shader the same way: each channel back to 0..255, then weighted.
const SHADER_DECODE = `
    float kigumiMemberIdAt(vec2 fragCoord) {
        vec2 uv = (fragCoord - memberIdViewport.xy) / memberIdViewport.zw;
        vec3 c = floor(texture2D(memberIdMap, uv).rgb * 255.0 + 0.5);
        return c.r + c.g * 256.0 + c.b * 65536.0;
    }
`;

// Kept where any nearby pixel is the line's own member: a line on its timber's outline would
// otherwise flicker between its own pixels and the neighbour's.
const SHADER_TEST = `
    #ifdef USE_MEMBER_ID
        {
            bool own = false;
            for (int i = 0; i < 5; i++) {
                vec2 offset = i == 0 ? vec2(0.0) : (i == 1 ? vec2(1.5, 0.0) : (i == 2 ? vec2(-1.5, 0.0)
                    : (i == 3 ? vec2(0.0, 1.5) : vec2(0.0, -1.5))));
                if (abs(kigumiMemberIdAt(gl_FragCoord.xy + offset) - ownMemberId) < 0.5) {
                    own = true;
                }
            }
            if (!own) discard;
        }
    #endif
`;

class MemberIdBuffer {
    /**
     * @param {object} options
     * @param {object} options.THREE
     * @param {object} options.renderer the viewer's WebGLRenderer
     */
    constructor({ THREE, renderer }) {
        this.THREE = THREE;
        this.renderer = renderer;
        this.idsByKey = new Map();
        this.keysById = new Map();
        this.targets = new Map();
        // One uniform object for every material that asks: render() points it at the viewport
        // being drawn, and they all follow.
        this.uniforms = {
            memberIdMap: { value: null },
            memberIdViewport: { value: new THREE.Vector4(0, 0, 1, 1) },
        };
    }

    /** The member's id, made the first time it is asked for and kept. */
    idFor(memberKey) {
        let id = this.idsByKey.get(memberKey);
        if (id === undefined) {
            id = this.idsByKey.size + 1;
            this.idsByKey.set(memberKey, id);
            this.keysById.set(id, memberKey);
        }
        return id;
    }

    /** An id mesh for the member, as a child of `solidMesh`, sharing its geometry. */
    attach(memberKey, solidMesh) {
        const THREE = this.THREE;
        const [r, g, b] = idToRgb(this.idFor(memberKey));
        const material = new THREE.MeshBasicMaterial({
            color: new THREE.Color(r / 255, g / 255, b / 255),
            side: solidMesh.material ? solidMesh.material.side : THREE.FrontSide,
            toneMapped: false,
        });
        const mesh = new THREE.Mesh(solidMesh.geometry, material);
        mesh.layers.set(ID_LAYER);
        // Never what a ray hits: picking asks for the member, and this is only its id.
        mesh.raycast = () => {};
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        solidMesh.add(mesh);
        return mesh;
    }

    /**
     * Draw `scene`'s id meshes as `camera` sees them into the render target kept for
     * `viewportKey`, `widthPx` by `heightPx` (drawing-buffer pixels), and point the shared
     * uniforms at it: `rectPx` is where the viewport sits in the drawing buffer, [x, y, w, h]
     * from the bottom left. Leaves the renderer drawing to the canvas again.
     */
    render(scene, camera, viewportKey, rectPx) {
        const THREE = this.THREE;
        const width = Math.max(1, Math.round(rectPx[2]));
        const height = Math.max(1, Math.round(rectPx[3]));
        let target = this.targets.get(viewportKey);
        if (!target) {
            target = new THREE.WebGLRenderTarget(width, height, {
                minFilter: THREE.NearestFilter,
                magFilter: THREE.NearestFilter,
                format: THREE.RGBAFormat,
                type: THREE.UnsignedByteType,
            });
            this.targets.set(viewportKey, target);
        } else if (target.width !== width || target.height !== height) {
            target.setSize(width, height);
        }
        const renderer = this.renderer;
        const previousColor = renderer.getClearColor(new THREE.Color());
        const previousAlpha = renderer.getClearAlpha();
        const previousLayers = camera.layers.mask;
        const previousBackground = scene.background;
        renderer.setRenderTarget(target);
        renderer.setClearColor(0x000000, 1);
        renderer.clear(true, true, false);
        scene.background = null;
        camera.layers.set(ID_LAYER);
        renderer.render(scene, camera);
        camera.layers.mask = previousLayers;
        scene.background = previousBackground;
        renderer.setRenderTarget(null);
        renderer.setClearColor(previousColor, previousAlpha);
        this.uniforms.memberIdMap.value = target.texture;
        this.uniforms.memberIdViewport.value.set(rectPx[0], rectPx[1], width, height);
        return target;
    }

    /** Which member is frontmost at a pixel of a viewport's last render, or null. */
    idAt(viewportKey, xPx, yPx) {
        const target = this.targets.get(viewportKey);
        if (!target) {
            return null;
        }
        const pixel = new Uint8Array(4);
        this.renderer.readRenderTargetPixels(target, Math.floor(xPx), Math.floor(yPx), 1, 1, pixel);
        const id = rgbToId(pixel[0], pixel[1], pixel[2]);
        return id === BACKGROUND ? null : (this.keysById.get(id) || null);
    }

    /**
     * Make a LineMaterial draw only where `memberKey` is the frontmost member: hidden by any other
     * member in front, never by its own. Must be called before the material is first drawn.
     */
    clipLineMaterial(material, memberKey) {
        material.uniforms.memberIdMap = this.uniforms.memberIdMap;
        material.uniforms.memberIdViewport = this.uniforms.memberIdViewport;
        material.uniforms.ownMemberId = { value: this.idFor(memberKey) };
        material.defines = { ...(material.defines || {}), USE_MEMBER_ID: '' };
        material.fragmentShader = clipShader(material.fragmentShader);
        material.needsUpdate = true;
        return material;
    }

    dispose() {
        for (const target of this.targets.values()) {
            target.dispose();
        }
        this.targets.clear();
    }
}

/** A LineMaterial fragment shader with the member test put in after its clipping. */
function clipShader(source) {
    const declare = `
        #ifdef USE_MEMBER_ID
            uniform sampler2D memberIdMap;
            uniform vec4 memberIdViewport;
            uniform float ownMemberId;
            ${SHADER_DECODE}
        #endif
    `;
    const hook = '#include <clipping_planes_fragment>';
    if (!source.includes(hook)) {
        throw new Error('member-id-buffer: the line shader has no clipping hook to follow');
    }
    return source
        .replace('void main() {', `${declare}\n\t\tvoid main() {`)
        .replace(hook, `${hook}\n${SHADER_TEST}`);
}

const KigumiMemberIdBuffer = { MemberIdBuffer, idToRgb, rgbToId, clipShader, ID_LAYER, BACKGROUND };

export { MemberIdBuffer, idToRgb, rgbToId, clipShader, ID_LAYER, BACKGROUND };
