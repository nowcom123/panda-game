"""
[ 불릿타임 신규 연출 제안 독립 프리뷰 스크립트 ]
- 게임 코드를 직접 수정하지 않고, 독립 스크립트 내에서 제안 효과를 시뮬레이션 및 캡처
- 비교 항목:
  1) 일반 화면 (Standard Rendering)
  2) 제안된 불릿타임 연출 (약한 채도 22% 감소 + 차가운 청회색 틴트)
  3) 불릿타임 연출 + 사용자 선명도(Sharpening) 동시 적용 화면
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root_dir = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root_dir))

from panda3d.core import (
    loadPrcFileData, Filename, PNMImage, Shader, Vec3, LColor
)
loadPrcFileData('', 'window-type offscreen\nwin-size 1280 720\naudio-library-name null\nsync-video false')

from game import LiminalInfiniteLoop
from monster import TallSkeletonMonster
from boss_patterns import GroundDangerIndicator

out_dir = Path(__file__).resolve().parent

_PROPOSED_BT_GLSL = """
uniform float bt_intensity; // 0.0 ~ 1.0 (시작 0.20s, 종료 0.28s 부드러운 보간)

vec3 apply_bullet_time_grade(vec3 color) {
    if (bt_intensity <= 0.001) return color;
    // 1. 휘도(Luminance) 계산
    float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
    // 2. 약 22% 채도 감소 (15~25% 권장값 중앙)
    vec3 desat = mix(color, vec3(luma), 0.22);
    // 3. 차가운 청회색 미세 틴트 (적 안광 및 붉은 경고 링과 극명한 대비)
    vec3 cool_tint = desat * vec3(0.92, 0.96, 1.06);
    // 4. 전환 강도에 따른 부드러운 합성
    return mix(color, cool_tint, bt_intensity);
}
"""

def main():
    app = LiminalInfiniteLoop()
    try:
        with patch.object(app.player, 'lock_mouse'):
            app.start_test_mode()

        # 카메라 및 뷰모델 세팅
        app.camera.setPos(0, -5.2, 1.7)
        app.camera.setHpr(0, -6, 0)
        app.combat.switch_weapon('AR')
        app.combat.update(0.1)
        app.ui_mgr.hide_stage_banner()

        # 테스트용 몬스터 및 위험 링 배치 (시인성 검증용)
        skel = TallSkeletonMonster(app.world_root, 0.0, 3.5)
        skel.update(0.016, is_moving=False)
        ind = GroundDangerIndicator(app.render, 0.0, 3.5, radius=2.5, color=LColor(1.0, 0.25, 0.15, 0.75))
        ind.set_progress(0.7)

        pipe = app.pbr_pipeline
        pipe._update(SimpleNamespace(DS_cont=1))

        # 제안 셰이더를 임시 장착하여 시각 비교 프리뷰 캡처
        quad = pipe._post_process_quad
        orig_shader = quad.getShader()
        frag = orig_shader.getText(Shader.ST_fragment)
        frag = frag.replace('void main() {', _PROPOSED_BT_GLSL + '\nvoid main() {')
        frag = frag.replace('vec3 color = sharpen_scene(tex_color.rgb);',
                            'vec3 color = apply_bullet_time_grade(sharpen_scene(tex_color.rgb));')
        test_shader = Shader.make(Shader.SL_GLSL, orig_shader.getText(Shader.ST_vertex), frag)
        quad.setShader(test_shader)

        def capture(name):
            pipe._update(SimpleNamespace(DS_cont=1))
            for _ in range(3):
                app.graphicsEngine.renderFrame()
            assert not test_shader.getErrorFlag(), 'Preview shader failed to compile'
            shot = PNMImage()
            assert app.win.getScreenshot(shot)
            dest = out_dir / name
            shot.write(Filename.fromOsSpecific(str(dest)))
            print(f"Captured: {dest}")
            return shot

        # 1. 일반 화면 (불릿타임 OFF, 샤프닝 OFF)
        quad.setShaderInput('bt_intensity', 0.0)
        pipe.set_sharpening(False)
        normal = capture('preview_normal.png')

        # 2. 제안 불릿타임 연출 (22% 채도 감소 + 차가운 청회색 틴트)
        quad.setShaderInput('bt_intensity', 1.0)
        pipe.set_sharpening(False)
        proposed = capture('preview_bullet_time_proposed.png')

        # 3. 불릿타임 연출 + 사용자 선명도(Sharpening) ON 옵션 동시 적용 화면
        pipe.set_sharpening(True)
        sharpened = capture('preview_bullet_time_with_sharpening.png')

        def changed_pixels(a, b):
            return sum((a.getXel(x, y)-b.getXel(x, y)).length() > .01
                       for y in range(a.getYSize()) for x in range(a.getXSize()))

        grade_changes = changed_pixels(normal, proposed)
        sharp_changes = changed_pixels(proposed, sharpened)
        assert grade_changes > 3000, grade_changes
        assert sharp_changes > 3000, sharp_changes
        print(f'PASS: grade changes {grade_changes} pixels; independent sharpening changes {sharp_changes} pixels.')

        # 4. 탄피 배치 참고 이미지: 정지 프레임이며 감속·궤적 검증이 아니다.
        app.camera.setPos(0.22, 0.40, -0.05)
        app.camera.setHpr(15, -12, 0)
        quad.setShaderInput('bt_intensity', 1.0)
        pipe.set_sharpening(False)
        muzzle_pos = app.world_root.getRelativePoint(app.combat.vm_root, Vec3(0.18, 0.65, -0.21))
        # 탄피 여러 발을 배출 궤적 위치에 시뮬레이션
        app.combat.casing_effects.clear()
        app.combat.casing_effects.emit('AR', muzzle_pos + Vec3(0.06, 0.08, 0.08), Vec3(0.3, 0.1, 0.6))
        app.combat.casing_effects.emit('AR', muzzle_pos + Vec3(0.14, 0.02, 0.04), Vec3(0.2, -0.1, 0.2))
        capture('preview_casing_static.png')

        # 정리
        ind.destroy()
        skel.destroy()
        print("Comparison previews generated successfully.")
    finally:
        app.destroy()


if __name__ == '__main__':
    main()
