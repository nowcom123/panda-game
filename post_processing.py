"""Optional scene sharpening in the existing SimplePBR tone-mapping pass.

No additional render target or fullscreen pass; the HUD is drawn afterwards.
The adapter preserves SimplePBR's tone map, exposure and optional color LUT.
"""
from panda3d.core import Shader
from simplepbr import Pipeline


_SHARPEN_GLSL = """
uniform float scene_sharpness;
uniform vec2 scene_texel;

vec3 sharpen_scene(vec3 center) {
    if (scene_sharpness <= 0.001) return center;
    vec2 dx = vec2(scene_texel.x * 1.35, 0.0);
    vec2 dy = vec2(0.0, scene_texel.y * 1.35);
    vec3 left = texture2D(tex, clamp(v_texcoord - dx, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 right = texture2D(tex, clamp(v_texcoord + dx, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 down = texture2D(tex, clamp(v_texcoord - dy, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 up = texture2D(tex, clamp(v_texcoord + dy, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 detail = center - (left + right + down + up) * 0.25;
    // Limit HDR overshoot and suppress amplification of almost-flat noise.
    vec3 limit = vec3(0.035) + max(center, vec3(0.0)) * 0.28;
    float edge = dot(abs(detail), vec3(0.2126, 0.7152, 0.0722));
    float gate = smoothstep(0.002, 0.018, edge);
    vec3 sharpened = max(vec3(0.0), center + clamp(detail * 1.8, -limit, limit) * scene_sharpness * gate);
    return sharpened;
}
"""


class GamePostProcessing(Pipeline):
    """Keep shader reconfiguration and window resizing owned by SimplePBR."""

    def _setup_tonemapping(self):
        super()._setup_tonemapping()
        quad = self._post_process_quad
        original = quad.getShader()
        fragment = original.getText(Shader.ST_fragment)
        sample = 'vec3 color = tex_color.rgb;'
        if fragment.count(sample) != 1 or fragment.count('void main() {') != 1:
            raise RuntimeError('SimplePBR tone-map layout changed; update sharpening shader adapter.')
        fragment = fragment.replace('void main() {', _SHARPEN_GLSL + '\nvoid main() {')
        fragment = fragment.replace(sample, 'vec3 color = sharpen_scene(tex_color.rgb);')
        shader = Shader.make(Shader.SL_GLSL, original.getText(Shader.ST_vertex), fragment)
        quad.setShader(shader)
        self.sharpening_enabled = getattr(self, 'sharpening_enabled', False)
        self._sync_sharpening_inputs()

    def _sync_sharpening_inputs(self):
        self._post_process_quad.setShaderInput('scene_sharpness', float(self.sharpening_enabled))
        self._post_process_quad.setShaderInput('scene_texel',
            1.0 / max(1, self.window.getXSize()), 1.0 / max(1, self.window.getYSize()))

    def set_sharpening(self, enabled):
        self.sharpening_enabled = bool(enabled)
        self._sync_sharpening_inputs()

    def _update(self, task):
        result = super()._update(task)
        self._sync_sharpening_inputs()
        return result
