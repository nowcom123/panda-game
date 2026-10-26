"""Post-processing sharpening + bullet-time cinematic effects.

Runs entirely inside SimplePBR's existing tone-mapping quad — no extra
render-target or fullscreen pass needed.  The HUD layer is drawn afterwards
so all on-screen text / vignette overlays still appear on top.

Bullet-time effects (activated via set_bullet_time(strength 0..1)):
  • Desaturation of neutral surfaces (fire/tracer hues preserved)
  • Radial barrel distortion  (zooms inward, gives "through a scope" feel)
  • Chromatic aberration        (lateral RGB channel split at screen edges)
  • Luminance-preserving cold-blue tint (keeps dark areas readable)
  • All effects are smoothly eased in/out via the strength envelope.
"""
from panda3d.core import Shader


try:
    from simplepbr import Pipeline as _Base
except ImportError:          # headless / unit-test environment
    class _Base:             # type: ignore[no-redef]
        def __init__(self, **kw):
            pass
        def _setup_tonemapping(self):
            pass
        def _update(self, task):
            import direct.task.Task as T
            return T.Task.cont


# ---------------------------------------------------------------------------
#  GLSL snippet injected into SimplePBR's tone-mapping fragment shader
# ---------------------------------------------------------------------------
_BULLET_TIME_GLSL = """
// ── Bullet-time uniforms ────────────────────────────────────────────────
uniform float scene_sharpness;
uniform float bullet_time_strength;   // 0 = normal  1 = full slow-mo
uniform vec2  scene_texel;            // 1/resolution

// ── Helpers ──────────────────────────────────────────────────────────────
vec2 barrel_distort(vec2 uv, float strength) {
    // Expand centre, compress edges — gives convex-lens slow-mo look.
    vec2  d   = uv - 0.5;
    float r2  = dot(d, d);
    float warp = 1.0 + strength * 0.18 * r2;
    return 0.5 + d * warp;
}

vec3 chromatic_aberration(vec2 uv, float strength) {
    // Lateral RGB split — stronger at screen edges.
    vec2  d    = uv - 0.5;
    float edge = dot(d, d) * 4.0;           // 0 at centre, ~1 at corner
    float offs = strength * 0.008 * edge;

    vec2 uv_r = clamp(uv + vec2( offs,  0.0), scene_texel, vec2(1.0) - scene_texel);
    vec2 uv_g = clamp(uv, scene_texel, vec2(1.0) - scene_texel);
    vec2 uv_b = clamp(uv + vec2(-offs,  0.0), scene_texel, vec2(1.0) - scene_texel);

    float r = texture2D(tex, uv_r).r;
    float g = texture2D(tex, uv_g).g;
    float b = texture2D(tex, uv_b).b;
    return vec3(r, g, b);
}

vec3 time_grade(vec3 color, vec2 uv) {
    float s = bullet_time_strength;
    if (s < 0.001) return color;

    // 1. Desaturation – preserve saturated fire / tracer colours
    float hi  = max(color.r, max(color.g, color.b));
    float lo  = min(color.r, min(color.g, color.b));
    float sat = (hi - lo) / max(hi, 0.001);
    float desat_amt = s * 0.62 * (1.0 - smoothstep(0.25, 0.70, sat));
    float gray = dot(color, vec3(0.2126, 0.7152, 0.0722));

    // 2. Cold-blue tint  (slightly shift gray toward icy blue)
    vec3 tint = vec3(0.88, 0.96, 1.10);
    tint /= dot(tint, vec3(0.2126, 0.7152, 0.0722));
    vec3 cold = gray * tint;
    color = mix(color, cold, desat_amt);

    // This runs before tone mapping: do not subtract a display-space black
    // level, clamp HDR highlights, or multiply in another dark vignette.
    return color;
}

// ── Sharpening (independent of bullet-time) ───────────────────────────────
vec3 sharpen_scene(vec3 center, vec2 uv) {
    if (scene_sharpness <= 0.001) return center;
    vec2 dx = vec2(scene_texel.x * 1.35, 0.0);
    vec2 dy = vec2(0.0, scene_texel.y * 1.35);
    vec3 left  = texture2D(tex, clamp(uv - dx, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 right = texture2D(tex, clamp(uv + dx, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 down  = texture2D(tex, clamp(uv - dy, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 up    = texture2D(tex, clamp(uv + dy, scene_texel * 0.5, vec2(1.0) - scene_texel * 0.5)).rgb;
    vec3 detail = center - (left + right + down + up) * 0.25;
    vec3 limit  = vec3(0.035) + max(center, vec3(0.0)) * 0.28;
    float edge  = dot(abs(detail), vec3(0.2126, 0.7152, 0.0722));
    float gate  = smoothstep(0.002, 0.018, edge);
    return max(vec3(0.0), center + clamp(detail * 1.8, -limit, limit) * scene_sharpness * gate);
}
"""

# What we replace in SimplePBR's fragment shader ─ fragile but contained.
_SIMPLEPBR_SAMPLE = 'vec3 color = tex_color.rgb;'
_SIMPLEPBR_MAIN   = 'void main() {'


class GamePostProcessing(_Base):
    """SimplePBR subclass: sharpening + full bullet-time cinematic shader."""

    # ------------------------------------------------------------------ init
    def _setup_tonemapping(self):
        super()._setup_tonemapping()
        quad     = self._post_process_quad
        original = quad.getShader()
        fragment = original.getText(Shader.ST_fragment)

        if fragment.count(_SIMPLEPBR_SAMPLE) != 1 or \
           fragment.count(_SIMPLEPBR_MAIN)   != 1:
            raise RuntimeError(
                'SimplePBR tone-map layout changed; '
                'update GamePostProcessing shader adapter.'
            )

        # Inject helpers before main()
        fragment = fragment.replace(
            _SIMPLEPBR_MAIN,
            _BULLET_TIME_GLSL + '\n' + _SIMPLEPBR_MAIN
        )

        # Replace the plain sample with distortion + chromatic abberation
        # then pass the (possibly remapped) uv to our grade/sharpen chain.
        replacement = (
            # 1) compute warped UV
            'float _bt = bullet_time_strength;\n'
            'vec2  _uv = barrel_distort(v_texcoord, _bt);\n'
            # 2) chromatic aberration sample (replaces the plain tex sample)
            'vec3 _raw = (_bt > 0.001)\n'
            '    ? chromatic_aberration(_uv, _bt)\n'
            '    : tex_color.rgb;\n'
            # 3) sharpen, grade, store as `color`
            'vec3 color = time_grade(sharpen_scene(_raw, _uv), _uv);\n'
        )
        fragment = fragment.replace(_SIMPLEPBR_SAMPLE, replacement)

        shader = Shader.make(
            Shader.SL_GLSL,
            original.getText(Shader.ST_vertex),
            fragment
        )
        quad.setShader(shader)

        self.sharpening_enabled  = getattr(self, 'sharpening_enabled', False)
        self.bullet_time_strength = 0.0
        self._sync_inputs()

    # ---------------------------------------------------------------- helpers
    def _sync_inputs(self):
        q = self._post_process_quad
        q.setShaderInput('bullet_time_strength', float(getattr(self, 'bullet_time_strength', 0.0)))
        q.setShaderInput('scene_sharpness',      float(getattr(self, 'sharpening_enabled', False)))
        wx = max(1, self.window.getXSize())
        wy = max(1, self.window.getYSize())
        q.setShaderInput('scene_texel', 1.0 / wx, 1.0 / wy)

    # ─────────────────────────────────── public API
    def set_bullet_time(self, strength: float):
        """Call every frame with strength 0..1 from bullet_time.intensity()."""
        self.bullet_time_strength = max(0.0, min(1.0, strength))
        self._post_process_quad.setShaderInput(
            'bullet_time_strength', self.bullet_time_strength
        )

    def set_sharpening(self, enabled: bool):
        self.sharpening_enabled = bool(enabled)
        self._sync_inputs()

    # Keep texel size up-to-date on resize
    def _update(self, task):
        result = super()._update(task)
        self._sync_inputs()
        return result
