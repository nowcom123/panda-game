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
                # 4. Medieval Crossbow Shoot & Reload
        cb_shoot_p = self._get_path("crossbow_shoot.wav")
        self.crossbow_shoot_sfx = self.loader.loadSfx(cb_shoot_p) if cb_shoot_p else None
        gunshot_p = self._get_path("gunshot.wav")
        self.gunshot_sfx = self.crossbow_shoot_sfx or (self.loader.loadSfx(gunshot_p) if gunshot_p else None)

        cb_reload_p = self._get_path("crossbow_reload.wav")
        self.crossbow_reload_sfx = self.loader.loadSfx(cb_reload_p) if cb_reload_p else None

        # 4-2. Melee Bash & Bolt Retrieval
        melee_swing_p = self._get_path("melee_swing.wav")
        self.melee_swing_sfx = self.loader.loadSfx(melee_swing_p) if melee_swing_p else None

        melee_hit_p = self._get_path("melee_hit.wav")
        self.melee_hit_sfx = self.loader.loadSfx(melee_hit_p) if melee_hit_p else None

        bolt_ret_p = self._get_path("bolt_retrieve.wav")
        self.bolt_retrieve_sfx = self.loader.loadSfx(bolt_ret_p) if bolt_ret_p else None

        # 4-3. Consumable survival items SFX
        flask_p = self._get_path("flask_drink.wav")
        self.flask_drink_sfx = self.loader.loadSfx(flask_p) if flask_p else None

        censer_p = self._get_path("censer_ignite.wav")
        self.censer_ignite_sfx = self.loader.loadSfx(censer_p) if censer_p else None

        firepot_p = self._get_path("firepot_explode.wav")
        self.firepot_explode_sfx = self.loader.loadSfx(firepot_p) if firepot_p else None

        pickup_p = self._get_path("item_pickup.wav")
        self.item_pickup_sfx = self.loader.loadSfx(pickup_p) if pickup_p else None

        # 4-1. 실감형 탄환 타격음 (생체 피격, 치명타 처치, 벽체 탄착)
        flesh_hit_p = self._get_path("bullet_impact_flesh.wav")
        self.flesh_hit_sfx = self.loader.loadSfx(flesh_hit_p) if flesh_hit_p else None

        kill_hit_p = self._get_path("bullet_impact_kill.wav")
        self.kill_hit_sfx = self.loader.loadSfx(kill_hit_p) if kill_hit_p else None

        wall_hit_p = self._get_path("bullet_impact_wall.wav")
        self.wall_hit_sfx = self.loader.loadSfx(wall_hit_p) if wall_hit_p else None

        # 5. 괴물 사운드 참조
        self.serpent_slither_sfx = None
        self.serpent_hiss_sfx = None
        self.skeleton_rattle_sfx = None
        self.skeleton_groan_sfx = None
        self.serpent_hiss_cooldown = 3.0
        self.skeleton_groan_cooldown = 4.0

        # 6. 정전 및 전력 복구 비상 사이렌
        # 6. Medieval Dark Fantasy Inversion & Bell SFX
        horn_p = self._get_path("abyssal_horn.wav")
        self.abyssal_horn_sfx = self.loader.loadSfx(horn_p) if horn_p else None
        purify_p = self._get_path("eclipse_purify.wav")
        self.eclipse_purify_sfx = self.loader.loadSfx(purify_p) if purify_p else None
        siren_p = self._get_path("siren_alarm.wav")
        self.siren_sfx = self.abyssal_horn_sfx or (self.loader.loadSfx(siren_p) if siren_p else None)
        pwr_p = self._get_path("power_restored.wav")
        self.power_restored_sfx = self.eclipse_purify_sfx or (self.loader.loadSfx(pwr_p) if pwr_p else None)

        # 6-2. Shadow Stalker Entity SFX
        shriek_p = self._get_path("stalker_shriek.wav")
        self.stalker_shriek_sfx = self.loader.loadSfx(shriek_p) if shriek_p else None
        lunge_p = self._get_path("stalker_lunge.wav")
        self.stalker_lunge_sfx = self.loader.loadSfx(lunge_p) if lunge_p else None

        # 7. 고대 룬 제단 및 탈출 관문 효과음
        altar_p = self._get_path("altar_activate.wav")
        self.altar_activate_sfx = self.loader.loadSfx(altar_p) if altar_p else None
        gate_p = self._get_path("gate_open.wav")
        self.gate_open_sfx = self.loader.loadSfx(gate_p) if gate_p else None

        # 준비음은 종별 두 음원을 번갈아 사용해 동시 공격의 소리가 끊기지 않게 합니다.
        self.attack_warning_sfx = []
        self._attack_warning_pools = {}
        self._attack_warning_indices = {}
        for kind, filename in (
            ('orc', 'orc_slam_charge.wav'),
            ('witch', 'witch_cast_charge.wav'),
            ('stalker', 'stalker_lunge_charge.wav'),
        ):
            path = self._get_path(filename)
            sounds = []
            if path:
                for _ in range(2):
                    sound = self.audio3d.loadSfx(path) if self.audio3d else self.loader.loadSfx(path)
                    if sound:
                        sound.setLoop(False)
                        sound.set3dMinDistance(4.0)
                        sound.set3dMaxDistance(32.0)
                        sounds.append(sound)
            self._attack_warning_pools[kind] = sounds
            self._attack_warning_indices[kind] = 0
            self.attack_warning_sfx.extend(sounds)

    def play_attack_warning(self, kind, position):
        sounds = self._attack_warning_pools.get(kind, [])
        if not sounds:
            return
        index = self._attack_warning_indices[kind]
        sound = sounds[index % len(sounds)]
        self._attack_warning_indices[kind] = index + 1
        sound.set3dAttributes(position.x, position.y, position.z + 1.0, 0, 0, 0)
        sound.setVolume(0.85)
        sound.play()

    def _get_path(self, fname):
        for directory in (self.audio_dir, os.path.dirname(__file__)):
            full_p = os.path.join(directory, fname)
            if os.path.isfile(full_p):
                return Filename.fromOsSpecific(os.path.abspath(full_p))
        return None

    def detach_monsters(self):
        """이전 몬스터의 소리를 중지하고 3D 위치 추적 연결을 해제합니다."""
        for name in ("serpent_slither_sfx", "serpent_hiss_sfx", "skeleton_rattle_sfx", "skeleton_groan_sfx"):
            sound = getattr(self, name, None)
            if sound:
                sound.stop()
                if self.audio3d:
                    self.audio3d.detachSound(sound)
            setattr(self, name, None)
        self.serpent_hiss_cooldown = 3.0
        self.skeleton_groan_cooldown = 4.0

    def stop_effects(self):
        """화면 전환 때 재생 중인 효과음과 몬스터 루프를 중지합니다."""
        for name, value in vars(self).items():
            if name.endswith('_sfx'):
                sounds = value if isinstance(value, list) else [value]
                for sound in sounds:
                    if sound:
                        sound.stop()

    def cleanup(self):
        self.stop_effects()
        self.detach_monsters()
        if self.bgm:
            self.bgm.stop()
        if self.audio3d:
            self.audio3d.disable()

    def attach_monsters(self, serpent, skeleton):
        """괴물 3D 오디오 부착"""
        self.detach_monsters()
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
        if mode != "PLAYING":
            self.stop_effects()
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
            for sound in (self.serpent_slither_sfx, self.skeleton_rattle_sfx):
                if sound:
                    sound.play()
        elif self.bgm:
            self.bgm.setVolume(0.20 if mode == "GAME_OVER" else 0.25)

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

    def play_crossbow_shoot(self):
        """기계식 강철 아발레스트 사격음 (강철 현 진동 + 격발음)"""
        if self.crossbow_shoot_sfx:
            self.crossbow_shoot_sfx.setVolume(1.0)
            self.crossbow_shoot_sfx.play()
        elif self.gunshot_sfx:
            self.gunshot_sfx.setVolume(1.0)
            self.gunshot_sfx.play()

    def play_gunshot(self):
        self.play_crossbow_shoot()

    def play_crossbow_reload(self):
        """아발레스트 래칫 크랭크 권선 및 볼트 삽입음"""
        if self.crossbow_reload_sfx:
            self.crossbow_reload_sfx.setVolume(0.95)
            self.crossbow_reload_sfx.play()

    def play_melee_swing(self):
        """근접 밀치기 휘두름 풍절음"""
        if self.melee_swing_sfx:
            self.melee_swing_sfx.setVolume(0.85)
            self.melee_swing_sfx.play()

    def play_melee_hit(self):
        """근접 타격 뼈/육편 파쇄 둔탁한 타격음"""
        if self.melee_hit_sfx:
            self.melee_hit_sfx.setVolume(1.0)
            self.melee_hit_sfx.play()

    def play_bolt_retrieve(self):
        """시체/바닥에서 강철 볼트 수습 금속음"""
        if self.bolt_retrieve_sfx:
            self.bolt_retrieve_sfx.setVolume(0.90)
            self.bolt_retrieve_sfx.play()

    def play_flesh_hit(self):
        """생체 피격 타격음 (묵직한 살점/뼈 파열음)"""
        if self.flesh_hit_sfx:
            self.flesh_hit_sfx.setVolume(random.uniform(0.88, 1.0))
            self.flesh_hit_sfx.play()

    def play_kill_hit(self):
        """치명타 처치 타격음 (강력한 파쇄 충격음)"""
        if self.kill_hit_sfx:
            self.kill_hit_sfx.setVolume(1.0)
            self.kill_hit_sfx.play()

    def play_wall_hit(self):
        """벽체/콘크리트 도탄 및 탄착음"""
        if self.wall_hit_sfx:
            self.wall_hit_sfx.setVolume(random.uniform(0.70, 0.90))
            self.wall_hit_sfx.play()

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

    def play_abyssal_horn(self):
        """Ancient Abyssal War Horn (Medieval Inversion sound)"""
        sfx = getattr(self, 'abyssal_horn_sfx', None) or self.siren_sfx
        if sfx:
            sfx.setVolume(1.0)
            sfx.play()

    def play_eclipse_purify(self):
        """Sacred Cathedral Bell of Returning Light"""
        sfx = getattr(self, 'eclipse_purify_sfx', None) or self.power_restored_sfx
        if sfx:
            sfx.setVolume(0.95)
            sfx.play()

    def play_stalker_shriek(self):
        """Shadow Stalker Horror Screech"""
        if getattr(self, 'stalker_shriek_sfx', None):
            self.stalker_shriek_sfx.setVolume(random.uniform(0.92, 1.0))
            self.stalker_shriek_sfx.play()

    def play_stalker_lunge(self):
        """Shadow Stalker Rapid Lunge / Claws Slash SFX"""
        if getattr(self, 'stalker_lunge_sfx', None):
            self.stalker_lunge_sfx.setVolume(random.uniform(0.85, 0.95))
            self.stalker_lunge_sfx.play()

    def play_siren_alarm(self):
        self.play_abyssal_horn()

    def play_power_restored(self):
        self.play_eclipse_purify()

    def play_altar_activate(self):
        """고대 룬 제단 활성화 공명음 및 화염 분출음"""
        if hasattr(self, 'altar_activate_sfx') and self.altar_activate_sfx:
            self.altar_activate_sfx.setVolume(1.0)
            self.altar_activate_sfx.play()

    def play_flask_drink(self):
        """생명의 성수병 음용 사운드"""
        if hasattr(self, 'flask_drink_sfx') and self.flask_drink_sfx:
            self.flask_drink_sfx.setVolume(0.95)
            self.flask_drink_sfx.play()

    def play_censer_ignite(self):
        """정화의 향로 성스러운 점화 사운드"""
        if hasattr(self, 'censer_ignite_sfx') and self.censer_ignite_sfx:
            self.censer_ignite_sfx.setVolume(1.0)
            self.censer_ignite_sfx.play()

    def play_firepot_explode(self):
        """비산 화약병 도자기 파열 및 포효하는 화염 폭발"""
        if hasattr(self, 'firepot_explode_sfx') and self.firepot_explode_sfx:
            self.firepot_explode_sfx.setVolume(1.0)
            self.firepot_explode_sfx.play()

    def play_item_pickup(self):
        """던전 유골함/보급함 성물 파밍 획득음"""
        if hasattr(self, 'item_pickup_sfx') and self.item_pickup_sfx:
            self.item_pickup_sfx.setVolume(0.85)
            self.item_pickup_sfx.play()

    def play_gate_open(self):
        """심층 탈출 관문 개방 육중한 석문 및 쇠사슬음"""
        if hasattr(self, 'gate_open_sfx') and self.gate_open_sfx:
            self.gate_open_sfx.setVolume(1.0)
            self.gate_open_sfx.play()

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
