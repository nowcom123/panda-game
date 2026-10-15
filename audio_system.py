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

        # 7. 신규 전술 효과음 (재장전, 공이 클릭, 탄약 획득, 피격음, 방어/레벨업/스킬)
        empty_p = self._get_path("empty_click.wav")
        self.empty_click_sfx = self.loader.loadSfx(empty_p) if empty_p else None
        reload_p = self._get_path("reload.wav")
        self.reload_sfx = self.loader.loadSfx(reload_p) if reload_p else None
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
        hb_p = self._get_path("heartbeat.wav")
        self.heartbeat_sfx = self.loader.loadSfx(hb_p) if hb_p else None
        inv_open_p = self._get_path("inventory_open.wav")
        self.inv_open_sfx = self.loader.loadSfx(inv_open_p) if inv_open_p else None
        inv_close_p = self._get_path("inventory_close.wav")
        self.inv_close_sfx = self.loader.loadSfx(inv_close_p) if inv_close_p else None
        item_use_p = self._get_path("item_use.wav")
        self.item_use_sfx = self.loader.loadSfx(item_use_p) if item_use_p else None
        ads_in_p = self._get_path("ads_in.wav")
        self.ads_in_sfx = self.loader.loadSfx(ads_in_p) if ads_in_p else None
        ads_out_p = self._get_path("ads_out.wav")
        self.ads_out_sfx = self.loader.loadSfx(ads_out_p) if ads_out_p else None
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

    def play_empty_click(self):
        """탄약 고갈 시 공이 격발음"""
        if self.empty_click_sfx:
            self.empty_click_sfx.setVolume(0.75)
            self.empty_click_sfx.play()

    def play_reload(self):
        """탄창 장착 및 슬라이드 장전음"""
        if self.reload_sfx:
            self.reload_sfx.setVolume(0.85)
            self.reload_sfx.play()

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

    def play_witch_fireball(self):
        """마녀 파이어볼 발사음"""
        if self.witch_fireball_sfx:
            self.witch_fireball_sfx.setVolume(0.85)
            self.witch_fireball_sfx.play()

    def play_orc_slam(self):
        """오크 땅울림 지진파 강타음"""
        if self.orc_slam_sfx:
            self.orc_slam_sfx.setVolume(1.0)
            self.orc_slam_sfx.play()

    def play_crit_hit(self):
        """헤드샷 치명타 적중 핑 사운드"""
        if self.crit_hit_sfx:
            self.crit_hit_sfx.setVolume(0.95)
            self.crit_hit_sfx.play()

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

    def play_ads(self, is_aiming=True):
        """정밀 조준 진입/해제 무기 파지음"""
        snd = self.ads_in_sfx if is_aiming else self.ads_out_sfx
        if snd:
            snd.setVolume(0.50)
            snd.play()

    def play_monster_explode(self):
        """몬스터 사망 시 신체 폭발 및 파편화 파열음"""
        if self.monster_explode_sfx:
            self.monster_explode_sfx.setVolume(1.0)
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
            self.grenade_blast_sfx.play()

    def play_barrel_ignite(self):
        """폭발성 유류 드럼통 관통 점화 및 분출음"""
        if self.barrel_ignite_sfx:
            self.barrel_ignite_sfx.setVolume(0.95)
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
