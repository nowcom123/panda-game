"""
Audio System Module
Panda3D OpenAL 기반 3D 입체 음향, BGM 관리, 발자국 및 몬스터 환경음 제어
"""

import os
import random
from panda3d.core import Filename
from direct.showbase.Audio3DManager import Audio3DManager


class AudioManager:
    def __init__(self, base, loader, camera, sfx_manager_list=None):
        self.base = base
        self.loader = loader
        self.camera = camera
        self.audio_dir = os.path.join(os.path.dirname(__file__), "assets", "audio")

        # 1. 3D 입체 음향 매니저 초기화
        if sfx_manager_list:
            self.audio3d = Audio3DManager(sfx_manager_list[0], self.camera)
            self.audio3d.setDistanceFactor(1.0)
            self.audio3d.setDropOffFactor(1.1)
        else:
            self.audio3d = None

        # 2. BGM 초기화
        bgm_p = self._get_path("bgm_horror.wav")
        if bgm_p:
            self.bgm = self.loader.loadMusic(bgm_p)
            if self.bgm:
                self.bgm.setLoop(True)
                self.bgm.setVolume(0.35)
                self.bgm.play()
        else:
            self.bgm = None

        # 3. 발자국 효과음
        self.footstep_sfx = []
        for name in ["footstep_1.wav", "footstep_2.wav", "footstep_3.wav"]:
            snd_p = self._get_path(name)
            if snd_p:
                snd = self.loader.loadSfx(snd_p)
                if snd:
                    self.footstep_sfx.append(snd)

        sprint_p = self._get_path("footstep_sprint.wav")
        self.footstep_sprint_sfx = self.loader.loadSfx(sprint_p) if sprint_p else None
        self.footstep_idx = 0

        # 4. 권총 발사음
        gunshot_p = self._get_path("gunshot.wav")
        self.gunshot_sfx = self.loader.loadSfx(gunshot_p) if gunshot_p else None

        # 5. 괴물 사운드 참조
        self.serpent_slither_sfx = None
        self.serpent_hiss_sfx = None
        self.skeleton_rattle_sfx = None
        self.skeleton_groan_sfx = None
        self.serpent_hiss_cooldown = 3.0
        self.skeleton_groan_cooldown = 4.0

        # 6. 정전 및 전력 복구 비상 사이렌
        siren_p = self._get_path("siren_alarm.wav")
        self.siren_sfx = self.loader.loadSfx(siren_p) if siren_p else None
        pwr_p = self._get_path("power_restored.wav")
        self.power_restored_sfx = self.loader.loadSfx(pwr_p) if pwr_p else None

    def _get_path(self, fname):
        full_p = os.path.join(self.audio_dir, fname)
        if os.path.exists(full_p):
            return Filename.fromOsSpecific(os.path.abspath(full_p))
        return None

    def attach_monsters(self, serpent, skeleton):
        """괴물 3D 오디오 부착"""
        if not self.audio3d:
            return

        # 뱀 괴물 사운드
        slither_p = self._get_path("serpent_slither.wav")
        hiss_p = self._get_path("serpent_hiss.wav")
        if slither_p:
            self.serpent_slither_sfx = self.audio3d.loadSfx(slither_p)
            if self.serpent_slither_sfx:
                self.serpent_slither_sfx.setLoop(True)
                self.serpent_slither_sfx.setVolume(0.0)
                self.audio3d.attachSoundToObject(self.serpent_slither_sfx, serpent.node)
                self.serpent_slither_sfx.play()

        if hiss_p:
            self.serpent_hiss_sfx = self.audio3d.loadSfx(hiss_p)
            if self.serpent_hiss_sfx:
                self.serpent_hiss_sfx.setVolume(0.8)
                self.audio3d.attachSoundToObject(self.serpent_hiss_sfx, serpent.node)

        # 해골 괴물 사운드
        rattle_p = self._get_path("skeleton_rattle.wav")
        groan_p = self._get_path("skeleton_groan.wav")
        if rattle_p:
            self.skeleton_rattle_sfx = self.audio3d.loadSfx(rattle_p)
            if self.skeleton_rattle_sfx:
                self.skeleton_rattle_sfx.setLoop(True)
                self.skeleton_rattle_sfx.setVolume(0.0)
                self.audio3d.attachSoundToObject(self.skeleton_rattle_sfx, skeleton.node)
                self.skeleton_rattle_sfx.play()

        if groan_p:
            self.skeleton_groan_sfx = self.audio3d.loadSfx(groan_p)
            if self.skeleton_groan_sfx:
                self.skeleton_groan_sfx.setVolume(0.8)
                self.audio3d.attachSoundToObject(self.skeleton_groan_sfx, skeleton.node)

    def set_bgm_mode(self, mode="INTRO"):
        """인트로 / 게임플레이 상태별 BGM 및 괴물 오디오 볼륨 설정"""
        if mode == "INTRO":
            if self.bgm:
                self.bgm.setVolume(0.35)
            if self.serpent_slither_sfx:
                self.serpent_slither_sfx.setVolume(0.0)
            if self.skeleton_rattle_sfx:
                self.skeleton_rattle_sfx.setVolume(0.0)
        elif mode == "PLAYING":
            if self.bgm:
                self.bgm.setVolume(0.55)

    def play_footstep(self, is_sprinting=False):
        """플레이어 보행 발자국 사운드"""
        if is_sprinting and self.footstep_sprint_sfx:
            self.footstep_sprint_sfx.setVolume(random.uniform(0.65, 0.85))
            self.footstep_sprint_sfx.play()
        elif self.footstep_sfx:
            snd = self.footstep_sfx[self.footstep_idx % len(self.footstep_sfx)]
            self.footstep_idx += 1
            snd.setVolume(random.uniform(0.38, 0.55))
            snd.play()

    def play_gunshot(self):
        """권총 발사음"""
        if self.gunshot_sfx:
            self.gunshot_sfx.setVolume(0.85)
            self.gunshot_sfx.play()

    def play_serpent_hit(self):
        """뱀 피격 쉭쉭 효과음"""
        if self.serpent_hiss_sfx:
            self.serpent_hiss_sfx.setVolume(1.0)
            self.serpent_hiss_sfx.play()

    play_serpent_hiss = play_serpent_hit

    def play_skeleton_hit(self):
        """해골 피격 신음 효과음"""
        if self.skeleton_groan_sfx:
            self.skeleton_groan_sfx.setVolume(1.0)
            self.skeleton_groan_sfx.play()

    def play_siren_alarm(self):
        """정전 이벤트 발동 비상 사이렌"""
        if self.siren_sfx:
            self.siren_sfx.setVolume(0.95)
            self.siren_sfx.play()

    def play_power_restored(self):
        """전력 복구 서지 사운드"""
        if self.power_restored_sfx:
            self.power_restored_sfx.setVolume(0.85)
            self.power_restored_sfx.play()

    def update(self, dt, dist_serpent, dist_skeleton, s_los, k_los):
        """프레임별 3D 오디오 리스너 및 몬스터 거리 감쇠/포효 갱신"""
        if self.audio3d:
            self.audio3d.update()

        # 뱀 괴물 이동 슬리더 & 쉭쉭거림
        if self.serpent_slither_sfx:
            vol_s = max(0.0, min(1.0, (32.0 - dist_serpent) / 24.0)) * 0.75
            self.serpent_slither_sfx.setVolume(vol_s)

        if dist_serpent < 18.0 or s_los:
            self.serpent_hiss_cooldown -= dt
            if self.serpent_hiss_cooldown <= 0.0:
                if self.serpent_hiss_sfx:
                    h_vol = max(0.35, min(1.0, (22.0 - dist_serpent) / 18.0))
                    self.serpent_hiss_sfx.setVolume(h_vol)
                    self.serpent_hiss_sfx.play()
                self.serpent_hiss_cooldown = random.uniform(3.5, 6.5)

        # 해골 괴물 이동 래틀 & 신음
        if self.skeleton_rattle_sfx:
            vol_k = max(0.0, min(1.0, (34.0 - dist_skeleton) / 26.0)) * 0.75
            self.skeleton_rattle_sfx.setVolume(vol_k)

        if dist_skeleton < 20.0 or k_los:
            self.skeleton_groan_cooldown -= dt
            if self.skeleton_groan_cooldown <= 0.0:
                if self.skeleton_groan_sfx:
                    g_vol = max(0.35, min(1.0, (24.0 - dist_skeleton) / 20.0))
                    self.skeleton_groan_sfx.setVolume(g_vol)
                    self.skeleton_groan_sfx.play()
                self.skeleton_groan_cooldown = random.uniform(4.0, 7.5)
