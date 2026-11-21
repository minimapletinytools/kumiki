// Mesh vertices arrive in world coordinates before the viewer moves a member for disassembly.
export function prepareTimberGrain(material, timberToWorld, memberKey) {
    const worldToTimber = new THREE.Matrix4().set(...timberToWorld).invert();
    let seed = 0;
    for (const char of memberKey) seed = (Math.imul(seed, 31) + char.charCodeAt(0)) >>> 0;
    const phaseOffset = (seed % 1021) / 1021;
    material.userData.hasTimberGrain = true;
    material.onBeforeCompile = shader => {
        if (!material.defines.TIMBER_GRAIN) return;
        shader.uniforms.worldToTimber = { value: worldToTimber };
        shader.vertexShader = 'uniform mat4 worldToTimber;\nvarying vec3 grainPosition;\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>',
            '#include <begin_vertex>\ngrainPosition = (worldToTimber * vec4(position, 1.0)).xyz;');
        shader.uniforms.grainOffset = { value: phaseOffset };
        shader.fragmentShader = 'uniform float grainOffset;\nvarying vec3 grainPosition;\n' + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `
            #include <color_fragment>
            // Slice the same nested growth rings on every face, including joint cheeks and end grain.
            vec3 p = grainPosition * 1000.0;
            float z = p.z + 430.0 * grainOffset;
            vec2 heart = vec2(22.0 + 28.0 * grainOffset + 5.0 * sin(z * 0.013),
                              35.0 + 16.0 * grainOffset + 4.0 * sin(z * 0.009));
            float radius = length((p.xy - heart) * vec2(0.89, 1.0));
            float phase = radius / 3.6 + 0.30 * sin(radius * 0.23) + 0.13 * sin(z * 0.017 + p.x * 0.07);
            float distanceToRing = abs(fract(phase + 0.5) - 0.5);
            float pixelWidth = max(fwidth(phase), 0.001);
            float ring = 1.0 - smoothstep(0.025, 0.12 + pixelWidth * 0.45, distanceToRing);
            ring = mix(ring, 0.15, smoothstep(0.20, 0.80, pixelWidth));
            float band = 0.5 + 0.5 * cos(6.28318 * phase) * (1.0 - smoothstep(0.2, 0.8, pixelWidth));
            diffuseColor.rgb *= mix(vec3(1.0), vec3(0.64, 0.47, 0.34), 0.52 * ring + 0.10 * band);
        `);
    };
}

export function showTimberGrain(material, enabled) {
    if (!material.userData.hasTimberGrain || Boolean(material.defines.TIMBER_GRAIN) === enabled) return;
    if (enabled) material.defines.TIMBER_GRAIN = 1;
    else delete material.defines.TIMBER_GRAIN;
    material.needsUpdate = true;
}
