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

        self.master_sfx_volume = 1.0
        self.master_bgm_volume = 1.0

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

        # 4. 권총, 매그넘, AR 돌격소총 발사음 보이스 풀
        gunshot_p = self._get_path("gunshot.wav")
        self.gunshot_sfx = self.loader.loadSfx(gunshot_p) if gunshot_p else None
        self.gunshot_voices = [self.loader.loadSfx(gunshot_p) for _ in range(24)] if gunshot_p else []
        self.gunshot_voice_index = 0

        magnum_p = self._get_path("magnum_shot.wav")
        self.magnum_voices = [self.loader.loadSfx(magnum_p) for _ in range(16)] if magnum_p else self.gunshot_voices
        self.magnum_voice_index = 0

        ar_p = self._get_path("ar_shot.wav")
        self.ar_voices = [self.loader.loadSfx(ar_p) for _ in range(24)] if ar_p else self.gunshot_voices
        self.ar_voice_index = 0

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

        # 7. 신규 전술 효과음 (재장전, 공이 클릭, 탄약 획득, 피격음, 방어/레벨업/스킬)
        empty_p = self._get_path("empty_click.wav")
        self.empty_click_sfx = self.loader.loadSfx(empty_p) if empty_p else None
        reload_p = self._get_path("reload.wav")
        self.reload_sfx = self.loader.loadSfx(reload_p) if reload_p else None
        self.reload_sounds = {"PISTOL": self.reload_sfx}
        for weapon, filename in (("DUAL_PISTOL", "dual_reload.wav"), ("AR", "ar_reload.wav"), ("SHOTGUN", "shotgun_reload.wav")):
            path = self._get_path(filename)
            self.reload_sounds[weapon] = self.loader.loadSfx(path) if path else self.reload_sfx
        slide_p = self._get_path("slide_release.wav")
        self.slide_release_sfx = self.loader.loadSfx(slide_p) if slide_p else None
        ammo_p = self._get_path("ammo_pickup.wav")
        self.ammo_pickup_sfx = self.loader.loadSfx(ammo_p) if ammo_p else None
        hurt_p = self._get_path("player_hurt.wav")
        self.player_hurt_sfx = self.loader.loadSfx(hurt_p) if hurt_p else None
        door_alarm_p = self._get_path("door_alarm.wav")
        self.door_alarm_sfx = self.loader.loadSfx(door_alarm_p) if door_alarm_p else None
        door_unlock_p = self._get_path("door_unlock.wav")
        self.door_unlock_sfx = self.loader.loadSfx(door_unlock_p) if door_unlock_p else None
        levelup_p = self._get_path("levelup.wav")
        self.levelup_sfx = self.loader.loadSfx(levelup_p) if levelup_p else None
        fireball_p = self._get_path("witch_fireball.wav")
        self.witch_fireball_sfx = self.loader.loadSfx(fireball_p) if fireball_p else None
        slam_p = self._get_path("orc_slam.wav")
        self.orc_slam_sfx = self.loader.loadSfx(slam_p) if slam_p else None

        # 8. 정밀 조준, 치명타, 심장박동, 인벤토리/아이템 효과음
        crit_p = self._get_path("crit_hit.wav")
        self.crit_hit_sfx = self.loader.loadSfx(crit_p) if crit_p else None
        flesh_p = self._get_path("flesh_hit.wav")
        self.flesh_hit_sfx = self.loader.loadSfx(flesh_p) if flesh_p else None
        hb_p = self._get_path("heartbeat.wav")
        self.heartbeat_sfx = self.loader.loadSfx(hb_p) if hb_p else None
        inv_open_p = self._get_path("inventory_open.wav")
        self.inv_open_sfx = self.loader.loadSfx(inv_open_p) if inv_open_p else None
        inv_close_p = self._get_path("inventory_close.wav")
        self.inv_close_sfx = self.loader.loadSfx(inv_close_p) if inv_close_p else None
        item_use_p = self._get_path("item_use.wav")
        self.item_use_sfx = self.loader.loadSfx(item_use_p) if item_use_p else None
        explode_p = self._get_path("monster_explode.wav")
        self.monster_explode_sfx = self.loader.loadSfx(explode_p) if explode_p else None
        slide_p = self._get_path("slide.wav")
        self.slide_sfx = self.loader.loadSfx(slide_p) if slide_p else None
        grenade_throw_p = self._get_path("grenade_throw.wav")
        self.grenade_throw_sfx = self.loader.loadSfx(grenade_throw_p) if grenade_throw_p else None
        grenade_blast_p = self._get_path("grenade_blast.wav")
        self.grenade_blast_sfx = self.loader.loadSfx(grenade_blast_p) if grenade_blast_p else None
        barrel_ignite_p = self._get_path("barrel_ignite.wav")
        self.barrel_ignite_sfx = self.loader.loadSfx(barrel_ignite_p) if barrel_ignite_p else None
        combo_p = self._get_path("combo_kill.wav")
        self.combo_kill_sfx = self.loader.loadSfx(combo_p) if combo_p else None
        crate_p = self._get_path("crate_open.wav")
        self.crate_open_sfx = self.loader.loadSfx(crate_p) if crate_p else None

        # 8-1. 불릿 타임, 오버차지 고폭탄, 헤드샷 골절 크런치, 정예 토벌 효과음
        bt_hum_p = self._get_path("bullet_time_hum.wav")
        self.bullet_time_hum_sfx = self.loader.loadSfx(bt_hum_p) if bt_hum_p else None
        if self.bullet_time_hum_sfx:
            self.bullet_time_hum_sfx.setLoop(True)
        self.bullet_time_audio_active = False
        self.bullet_time_audio_elapsed = 0.0
        self.bullet_time_audio_level = 0.0
        self._world_sound_levels = {}
        self.time_cues = {}
        for key in ('enter', 'exit', 'tail'):
            path = self._get_path('time_' + key + '.wav')
            self.time_cues[key] = [self.loader.loadSfx(path) for _ in range(8 if key == 'tail' else 1)] if path else []
        self._time_tail_index = 0
        overcharge_p = self._get_path("overcharge_shot.wav")
        self.overcharge_shot_sfx = self.loader.loadSfx(overcharge_p) if overcharge_p else None
        crunch_p = self._get_path("headshot_crunch.wav")
        self.headshot_crunch_sfx = self.loader.loadSfx(crunch_p) if crunch_p else None
        elite_p = self._get_path("elite_kill.wav")
        self.elite_kill_sfx = self.loader.loadSfx(elite_p) if elite_p else None

        # 8-2. 샷건 및 무기 교체 효과음
        sg_blast_p = self._get_path("shotgun_blast.wav")
        self.shotgun_blast_sfx = self.loader.loadSfx(sg_blast_p) if sg_blast_p else None
        self.shotgun_voices = [self.loader.loadSfx(sg_blast_p) for _ in range(4)] if sg_blast_p else []
        self.shotgun_voice_index = 0
        sg_pump_p = self._get_path("shotgun_pump.wav")
        self.shotgun_pump_sfx = self.loader.loadSfx(sg_pump_p) if sg_pump_p else None
        w_switch_p = self._get_path("weapon_switch.wav")
        self.weapon_switch_sfx = self.loader.loadSfx(w_switch_p) if w_switch_p else None

        # 8-3. 지옥의 파수견 및 불릿 타임 펄스 효과음
        h_growl_p = self._get_path("hound_growl.wav")
        self.hound_growl_sfx = self.loader.loadSfx(h_growl_p) if h_growl_p else None
        h_dodge_p = self._get_path("hound_dodge.wav")
        self.hound_dodge_sfx = self.loader.loadSfx(h_dodge_p) if h_dodge_p else None
        h_death_p = self._get_path("hound_death.wav")
        self.hound_death_sfx = self.loader.loadSfx(h_death_p) if h_death_p else None
        h_step_p = self._get_path("hound_step.wav")
        self.hound_step_sfx = self.loader.loadSfx(h_step_p) if h_step_p else None


        # 9. 몬스터 3D 입체 접근 이동음 & 포효 사운드 풀 (동시 재생 인스턴스)
        self.monster_sound_pools = {}
        if self.audio3d:
            pool_specs = {
                "orc_step": ("orc_step.wav", 4, 1.5, 32.0, 0.95),
                "orc_growl": ("orc_growl.wav", 3, 2.0, 35.0, 1.0),
                "skel_step": ("skeleton_rattle.wav", 4, 1.5, 30.0, 0.90),
                "skel_groan": ("skeleton_groan.wav", 3, 2.0, 32.0, 0.95),
                "serp_slither": ("serpent_slither.wav", 3, 1.5, 30.0, 0.90),
                "serp_hiss": ("serpent_hiss.wav", 3, 2.0, 30.0, 1.0),
                "witch_whisper": ("witch_whisper.wav", 3, 2.0, 32.0, 0.95),
                "hound_step": ("hound_step.wav", 4, 1.2, 28.0, 0.90),
                "hound_growl": ("hound_growl.wav", 3, 2.0, 32.0, 1.0),
            }
            for key, (fname, count, min_d, max_d, base_v) in pool_specs.items():
                p = self._get_path(fname)
                if p:
                    instances = []
                    for _ in range(count):
                        snd = self.audio3d.loadSfx(p)
                        if snd:
                            self.audio3d.setSoundMinDistance(snd, min_d)
                            self.audio3d.setSoundMaxDistance(snd, max_d)
                            instances.append(snd)
                    if instances:
                        self.monster_sound_pools[key] = {
                            "instances": instances,
                            "min_dist": min_d,
                            "max_dist": max_d,
                            "base_vol": base_v,
                            "idx": 0
                        }

    def _get_path(self, fname):
        full_p = os.path.join(self.audio_dir, fname)
        if os.path.exists(full_p):
            return Filename.fromOsSpecific(os.path.abspath(full_p))
        return None

    def play_monster_3d(self, sound_key, node, volume_scale=1.0):
        """
        적 노드(NodePath) 위치에서 3D 입체 사운드 재생
        - 거리 감쇠 (Min 1.5m ~ Max 32m)
        - 리스너(카메라) 시선에 따른 좌우 360도 입체 패닝 자동 적용
        """
        if not self.audio3d or not node or node.isEmpty() or sound_key not in self.monster_sound_pools:
            return

        pool = self.monster_sound_pools[sound_key]
        instances = pool["instances"]

        # 미재생 중인 가용 인스턴스 검색
        chosen = None
        for snd in instances:
            if snd.status() != snd.PLAYING:
                chosen = snd
                break
        if not chosen:
            chosen = instances[pool["idx"]]
            pool["idx"] = (pool["idx"] + 1) % len(instances)

        self.audio3d.detachSound(chosen)
        self.audio3d.attachSoundToObject(chosen, node)
        chosen.setVolume(pool["base_vol"] * volume_scale)
        self._register_world_sound(chosen, pool["base_vol"] * volume_scale)
        self.audio3d.setSoundMinDistance(chosen, pool["min_dist"])
        self.audio3d.setSoundMaxDistance(chosen, pool["max_dist"])
        chosen.play()

    def attach_monsters(self, serpent, skeleton):
        """괴물 3D 오디오 부착 (호환성 유지)"""
        if not self.audio3d:
            return

        # 뱀 괴물 사운드
        slither_p = self._get_path("serpent_slither.wav")
        hiss_p = self._get_path("serpent_hiss.wav")
        if slither_p and serpent and hasattr(serpent, 'node'):
            self.serpent_slither_sfx = self.audio3d.loadSfx(slither_p)
            if self.serpent_slither_sfx:
                self.serpent_slither_sfx.setLoop(True)
                self.serpent_slither_sfx.setVolume(0.0)
                self.audio3d.attachSoundToObject(self.serpent_slither_sfx, serpent.node)
                self.serpent_slither_sfx.play()

        if hiss_p and serpent and hasattr(serpent, 'node'):
            self.serpent_hiss_sfx = self.audio3d.loadSfx(hiss_p)
            if self.serpent_hiss_sfx:
                self.serpent_hiss_sfx.setVolume(0.8)
                self.audio3d.attachSoundToObject(self.serpent_hiss_sfx, serpent.node)

        # 해골 괴물 사운드
        rattle_p = self._get_path("skeleton_rattle.wav")
        groan_p = self._get_path("skeleton_groan.wav")
        if rattle_p and skeleton and hasattr(skeleton, 'node'):
            self.skeleton_rattle_sfx = self.audio3d.loadSfx(rattle_p)
            if self.skeleton_rattle_sfx:
                self.skeleton_rattle_sfx.setLoop(True)
                self.skeleton_rattle_sfx.setVolume(0.0)
                self.audio3d.attachSoundToObject(self.skeleton_rattle_sfx, skeleton.node)
                self.skeleton_rattle_sfx.play()

        if groan_p and skeleton and hasattr(skeleton, 'node'):
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
                self.bgm.setVolume(0.55 * self.master_bgm_volume)

    def set_sfx_volume(self, volume):
        """효과음 전체 마스터 볼륨 설정 (0.0 ~ 1.0)"""
        self.master_sfx_volume = max(0.0, min(1.0, float(volume)))
        if hasattr(self, 'base') and hasattr(self.base, 'sfxManagerList'):
            for mgr in self.base.sfxManagerList:
                mgr.setVolume(self.master_sfx_volume)

    def set_bgm_volume(self, volume):
        """배경음 전체 마스터 볼륨 설정 (0.0 ~ 1.0)"""
        self.master_bgm_volume = max(0.0, min(1.0, float(volume)))
        if hasattr(self, 'base') and hasattr(self.base, 'musicManager') and self.base.musicManager:
            self.base.musicManager.setVolume(self.master_bgm_volume)
        elif self.bgm:
            self.bgm.setVolume(0.55 * self.master_bgm_volume)

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
        """9mm 권총 및 듀얼 글록 발사음"""
        self._play_firearm_voice("gunshot", 0.72)

    def play_magnum_shot(self):
        """데저트 이글 .50 매그넘 발사음"""
        self._play_firearm_voice("magnum", 0.90)

    def play_ar_shot(self):
        """5.56mm 전술 돌격소총(AR) 고속 연사음"""
        self._play_firearm_voice("ar", 0.78)

    def _play_firearm_voice(self, key, volume):
        voices = getattr(self, key + "_voices")
        if not voices:
            return
        index = getattr(self, key + "_voice_index")
        sound = voices[index]
        setattr(self, key + "_voice_index", (index + 1) % len(voices))
        if sound:
            sound.setVolume(volume)
            sound.setPlayRate(1.0)
            sound.play()
            if getattr(self, "bullet_time_audio_active", False):
                self._play_time_cue("tail")

    def play_serpent_hit(self):
        """뱀 피격 쉭쉭 효과음"""
        if self.serpent_hiss_sfx:
            self.serpent_hiss_sfx.setVolume(1.0)
            self._register_world_sound(self.serpent_hiss_sfx, self.serpent_hiss_sfx.getVolume())
            self.serpent_hiss_sfx.play()

    play_serpent_hiss = play_serpent_hit

    def play_skeleton_hit(self):
        """해골 피격 신음 효과음"""
        if self.skeleton_groan_sfx:
            self.skeleton_groan_sfx.setVolume(1.0)
            self._register_world_sound(self.skeleton_groan_sfx, self.skeleton_groan_sfx.getVolume())
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

    def play_empty_click(self):
        """탄약 고갈 시 공이 격발음"""
        if self.empty_click_sfx:
            self.empty_click_sfx.setVolume(0.26)
            self.empty_click_sfx.play()

    def play_reload(self, weapon="PISTOL", duration=None):
        """탄창 장착 및 슬라이드 장전음"""
        self.stop_weapon_actions()
        sound = self.reload_sounds.get(weapon, self.reload_sfx)
        if sound:
            sound.setVolume(0.34)
            sound.setPlayRate(sound.length() / duration if duration and duration > 0 else 1.0)
            sound.play()

    def play_slide_release(self):
        if self.slide_release_sfx:
            self.slide_release_sfx.setVolume(0.30)
            self.slide_release_sfx.play()

    def stop_weapon_actions(self):
        for sound in list(self.reload_sounds.values()) + [self.shotgun_pump_sfx]:
            if sound:
                sound.stop()

    def play_ammo_pickup(self):
        """탄약 상자 습득 차징 사운드"""
        if self.ammo_pickup_sfx:
            self.ammo_pickup_sfx.setVolume(0.80)
            self.ammo_pickup_sfx.play()

    def play_player_hurt(self):
        """플레이어 피격 충격음"""
        if self.player_hurt_sfx:
            self.player_hurt_sfx.setVolume(0.90)
            self.player_hurt_sfx.play()

    def play_door_alarm(self):
        """탈출문 방어 개방 비프음"""
        if self.door_alarm_sfx:
            self.door_alarm_sfx.setVolume(0.70)
            self.door_alarm_sfx.play()

    def play_door_unlock(self):
        """탈출문 완전 개방 락 해제 사운드"""
        if self.door_unlock_sfx:
            self.door_unlock_sfx.setVolume(0.95)
            self.door_unlock_sfx.play()

    def play_levelup(self):
        """레벨업 축하 아르페지오 사운드"""
        if self.levelup_sfx:
            self.levelup_sfx.setVolume(0.85)
            self.levelup_sfx.play()

    def play_witch_cast(self):
        """마녀 마법 시전 경고음 (파이어볼 시전 시작 시 호출)"""
        if self.witch_fireball_sfx:
            self.witch_fireball_sfx.setVolume(0.55)
            self._register_world_sound(self.witch_fireball_sfx, self.witch_fireball_sfx.getVolume())
            self.witch_fireball_sfx.play()

    def play_witch_fireball(self):
        """마녀 파이어볼 발사음"""
        if self.witch_fireball_sfx:
            self.witch_fireball_sfx.setVolume(0.85)
            self._register_world_sound(self.witch_fireball_sfx, self.witch_fireball_sfx.getVolume())
            self.witch_fireball_sfx.play()

    def play_orc_slam(self):
        """오크 땅울림 지진파 강타음"""
        if self.orc_slam_sfx:
            self.orc_slam_sfx.setVolume(1.0)
            self._register_world_sound(self.orc_slam_sfx, self.orc_slam_sfx.getVolume())
            self.orc_slam_sfx.play()

    def play_crit_hit(self):
        """헤드샷 치명타 적중 핑 사운드"""
        if self.crit_hit_sfx:
            self.crit_hit_sfx.setVolume(0.95)
            self.crit_hit_sfx.play()

    def play_flesh_hit(self):
        """탄환 몸통 적중 시 찰진 유기물 관통 타격음 재생"""
        if self.flesh_hit_sfx:
            self.flesh_hit_sfx.setVolume(random.uniform(0.75, 0.95))
            self.flesh_hit_sfx.play()

    def play_heartbeat(self):
        """빈사 위기 저주파 심장박동 사운드"""
        if self.heartbeat_sfx:
            self.heartbeat_sfx.setVolume(0.90)
            self.heartbeat_sfx.play()


    def play_inventory_toggle(self, is_open):
        """전술 인벤토리 개폐 효과음"""
        snd = self.inv_open_sfx if is_open else self.inv_close_sfx
        if snd:
            snd.setVolume(0.85)
            snd.play()

    def play_item_use(self):
        """소모품 사용 효과음 (주사기/키트/탄약)"""
        if self.item_use_sfx:
            self.item_use_sfx.setVolume(0.90)
            self.item_use_sfx.play()

    def play_monster_explode(self):
        """몬스터 사망 시 신체 폭발 및 파편화 파열음"""
        if self.monster_explode_sfx:
            self.monster_explode_sfx.setVolume(1.0)
            self._register_world_sound(self.monster_explode_sfx, self.monster_explode_sfx.getVolume())
            self.monster_explode_sfx.play()

    def play_slide(self):
        """스페이스바 전술 슬라이딩 지면 마찰 풍절음"""
        if self.slide_sfx:
            self.slide_sfx.setVolume(0.90)
            self.slide_sfx.play()

    def play_grenade_throw(self):
        """[G] 키 전술 파열 수류탄 핀 해제 및 투척음"""
        if self.grenade_throw_sfx:
            self.grenade_throw_sfx.setVolume(0.95)
            self.grenade_throw_sfx.play()

    def play_grenade_blast(self):
        """전술 수류탄 대규모 파열 폭발 및 충격파음"""
        if self.grenade_blast_sfx:
            self.grenade_blast_sfx.setVolume(1.0)
            self._register_world_sound(self.grenade_blast_sfx, self.grenade_blast_sfx.getVolume())
            self.grenade_blast_sfx.play()

    def play_barrel_ignite(self):
        """폭발성 유류 드럼통 관통 점화 및 분출음"""
        if self.barrel_ignite_sfx:
            self.barrel_ignite_sfx.setVolume(0.95)
            self._register_world_sound(self.barrel_ignite_sfx, self.barrel_ignite_sfx.getVolume())
            self.barrel_ignite_sfx.play()

    def play_combo_kill(self):
        """연속 킬 콤보 달성 시 타격 사운드"""
        if self.combo_kill_sfx:
            self.combo_kill_sfx.setVolume(0.95)
            self.combo_kill_sfx.play()

    def play_crate_open(self):
        """[E] 전술 보급 상자 개봉음"""
        if self.crate_open_sfx:
            self.crate_open_sfx.setVolume(0.90)
            self.crate_open_sfx.play()

    def play_bullet_time(self, is_start=True):
        """Lower a continuous hum into slow motion, then fade it out."""
        if is_start:
            if self.bullet_time_audio_active:
                return
            self._play_time_cue('enter')
            # Retriggering during the exit fade continues the same voice.
            if self.bullet_time_audio_level <= 0.0:
                self.bullet_time_audio_elapsed = 0.0
                if self.bullet_time_hum_sfx:
                    self.bullet_time_hum_sfx.setVolume(0.0)
                    self.bullet_time_hum_sfx.setPlayRate(1.0)
                    self.bullet_time_hum_sfx.play()
            self.bullet_time_audio_active = True
        else:
            self._play_time_cue('exit')
            self.bullet_time_audio_active = False

    def _play_time_cue(self, key):
        voices = getattr(self, 'time_cues', {}).get(key, [])
        if voices:
            index = getattr(self, '_time_tail_index', 0) % len(voices)
            sound = voices[index]
            if sound:
                sound.setVolume(0.16 if key == 'tail' else 0.35)
                sound.play()
            self._time_tail_index = index + 1

    def _register_world_sound(self, sound, volume):
        if not hasattr(self, '_world_sound_levels'):
            self._world_sound_levels = {}
        self._world_sound_levels[sound] = volume
        level = getattr(self, 'bullet_time_audio_level', 0.0)
        sound.setPlayRate(1.0 - 0.55 * level)
        sound.setVolume(volume * (1.0 - 0.25 * level))

    def update_bullet_time(self, dt):
        snd = self.bullet_time_hum_sfx
        if self.bullet_time_audio_active:
            self.bullet_time_audio_elapsed += dt
            self.bullet_time_audio_level = min(1.0, self.bullet_time_audio_level + dt / 0.12)
        else:
            self.bullet_time_audio_level = max(0.0, self.bullet_time_audio_level - dt / 0.30)
        for sound, volume in getattr(self, '_world_sound_levels', {}).items():
            sound.setPlayRate(1.0 - 0.55 * self.bullet_time_audio_level)
            sound.setVolume(volume * (1.0 - 0.25 * self.bullet_time_audio_level))
        if not snd:
            return
        if not self.bullet_time_audio_active and self.bullet_time_audio_level <= 0.0:
            snd.stop()
            return
        progress = min(1.0, self.bullet_time_audio_elapsed / 0.95)
        ease = progress * progress * (3.0 - 2.0 * progress)
        snd.setPlayRate(1.0 - 0.58 * ease)
        snd.setVolume(0.32 * self.bullet_time_audio_level)

    def stop_bullet_time(self):
        """Silence the looping effect immediately when resetting the game."""
        self.bullet_time_audio_active = False
        self.bullet_time_audio_elapsed = 0.0
        self.bullet_time_audio_level = 0.0
        for sound, volume in getattr(self, '_world_sound_levels', {}).items():
            sound.setPlayRate(1.0)
            sound.setVolume(volume)
        for voices in getattr(self, 'time_cues', {}).values():
            for sound in voices:
                if sound:
                    sound.stop()
        if self.bullet_time_hum_sfx:
            self.bullet_time_hum_sfx.stop()

    def play_overcharge_shot(self):
        """오버차지 고폭 플라즈마 소이탄 격발음"""
        if self.overcharge_shot_sfx:
            self.overcharge_shot_sfx.setVolume(1.0)
            self.overcharge_shot_sfx.play()

    def play_headshot_crunch(self):
        """치명타 헤드샷 적중 시 뼈 파쇄 크런치 음향"""
        if self.headshot_crunch_sfx:
            self.headshot_crunch_sfx.setVolume(1.0)
            self.headshot_crunch_sfx.play()

    def play_elite_kill(self):
        """정예 변이 몬스터 처치 시 웅장한 시네마틱 킬 사운드"""
        if self.elite_kill_sfx:
            self.elite_kill_sfx.setVolume(1.0)
            self.elite_kill_sfx.play()

    def play_shotgun_blast(self):
        """12게이지 샷건 산탄 대폭발 사운드"""
        self._play_firearm_voice("shotgun", 0.85)

    def play_shotgun_pump(self):
        """샷건 펌프액션 슬라이드 왕복 장전음"""
        if self.shotgun_pump_sfx:
            self.shotgun_pump_sfx.setVolume(0.30)
            self.shotgun_pump_sfx.play()

    def play_weapon_switch(self):
        """무기 교체 스왑 사운드"""
        if self.weapon_switch_sfx:
            self.weapon_switch_sfx.setVolume(0.24)
            self.weapon_switch_sfx.play()

    def play_hound_growl(self, node=None):
        """지옥의 파수견 으르렁거림 (3D 위치 음향 지원)"""
        if node and self.audio3d:
            self.play_pooled_3d("hound_growl", node, volume=1.0)
        elif self.hound_growl_sfx:
            self.hound_growl_sfx.setVolume(0.95)
            self.hound_growl_sfx.play()

    def play_hound_dodge(self, node=None):
        """지옥의 파수견 총알 도약 회피 음향"""
        if self.hound_dodge_sfx:
            self.hound_dodge_sfx.setVolume(1.0)
            self.hound_dodge_sfx.play()

    def play_hound_death(self):
        """지옥의 파수견 사망 하울링 및 뼈 파열음"""
        if self.hound_death_sfx:
            self.hound_death_sfx.setVolume(1.0)
            self.hound_death_sfx.play()

    def play_hound_step(self, node=None):
        """지옥의 파수견 고속 발톱 착지음"""
        if node and self.audio3d:
            self.play_pooled_3d("hound_step", node, volume=0.85)
        elif self.hound_step_sfx:
            self.hound_step_sfx.setVolume(0.80)
            self.hound_step_sfx.play()

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
                    self._register_world_sound(self.serpent_hiss_sfx, self.serpent_hiss_sfx.getVolume())
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
                    self._register_world_sound(self.skeleton_groan_sfx, self.skeleton_groan_sfx.getVolume())
                    self.skeleton_groan_sfx.play()
                self.skeleton_groan_cooldown = random.uniform(4.0, 7.5)
