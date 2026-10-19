import os
import wave
import random
import shutil
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "assets", "audio")
SAMPLE_RATE = 44100

def save_wav(filename, samples, sample_rate=SAMPLE_RATE):
    """부동소수점 배열(-1.0 ~ 1.0)을 16-bit PCM WAV 파일로 안전하게 저장"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # 정규화 및 클리핑 방지 (-0.92 ~ 0.92 범위)
    max_val = np.max(np.abs(samples))
    if max_val > 1e-6:
        samples = (samples / max_val) * 0.92
    else:
        samples = np.zeros_like(samples)
        
    int_samples = (samples * 32767.0).astype(np.int16)
    
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)  # 모노 (3D 오디오 및 공간 음향 호환)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())
        
    print(f"Generated: {filepath} ({len(samples)/sample_rate:.2f}s, {len(int_samples.tobytes())} bytes)")

def make_bgm():
    """
    어둡고 음산한 백룸 앰비언스 BGM (~24초 심리스 루프)
    - 42Hz, 48Hz, 56Hz 서브베이스 바이노럴 드론 (공포감 유발 저주파)
    - 4초 주기 심장박동 펄스 (Heartbeat Sub-Thump)
    - 삼음도(Tritone) 불협화음 쉬버링 공명
    - 천천히 변하는 필터드 앰비언트 바람
    """
    duration = 24.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # 1. 서브베이스 드론 (Sub-bass drone with beat frequencies)
    drone = (
        0.40 * np.sin(2 * np.pi * 44.0 * t) +
        0.30 * np.sin(2 * np.pi * 48.5 * t) +
        0.25 * np.sin(2 * np.pi * 55.0 * t) +
        0.15 * np.sin(2 * np.pi * 65.4 * t)
    )
    # 느린 LFO 볼륨 스웰 (0.083 Hz, ~12초 주기)
    lfo_sub = 0.75 + 0.25 * np.sin(2 * np.pi * 0.0833 * t)
    drone *= lfo_sub

    # 2. 불협화음 삼음도 앰비언트 (Tritone Dissonance: F# - C, 185Hz & 261Hz)
    detuned_shimmer = (
        0.10 * np.sin(2 * np.pi * 185.0 * t + 0.5 * np.sin(2 * np.pi * 0.25 * t)) +
        0.08 * np.sin(2 * np.pi * 261.6 * t + 0.4 * np.sin(2 * np.pi * 0.18 * t)) +
        0.06 * np.sin(2 * np.pi * 370.0 * t)
    )
    lfo_shimmer = 0.5 + 0.5 * np.sin(2 * np.pi * (1.0 / 6.0) * t)
    detuned_shimmer *= lfo_shimmer

    # 3. 4초 주기 심장 박동 펄스 (Heartbeat Sub-Thump)
    heartbeat = np.zeros_like(t)
    pulse_interval = 4.0
    num_pulses = int(duration / pulse_interval)
    for i in range(num_pulses):
        p_t0 = i * pulse_interval
        # 첫 번째 쿵 (Thump 1)
        idx1 = (t >= p_t0) & (t < p_t0 + 0.35)
        dt1 = t[idx1] - p_t0
        heartbeat[idx1] += 0.45 * np.sin(2 * np.pi * 50.0 * dt1) * np.exp(-dt1 * 12.0)
        
        # 두 번째 쿵 (Thump 2, 0.28초 뒤)
        idx2 = (t >= p_t0 + 0.28) & (t < p_t0 + 0.65)
        dt2 = t[idx2] - (p_t0 + 0.28)
        heartbeat[idx2] += 0.35 * np.sin(2 * np.pi * 45.0 * dt2) * np.exp(-dt2 * 14.0)

    # 4. 공허한 통로 바람 노이즈 (Filtered Air / Wind)
    np.random.seed(42)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    # 단순 이동 평균 저역 통과 필터 (Cutoff ~350Hz)
    kernel_size = int(SAMPLE_RATE / 350)
    kernel = np.ones(kernel_size) / kernel_size
    wind = np.convolve(noise, kernel, mode='same') * 0.22
    lfo_wind = 0.6 + 0.4 * np.sin(2 * np.pi * 0.125 * t)
    wind *= lfo_wind

    # 합성
    bgm = drone + detuned_shimmer + heartbeat + wind

    # 심리스 루프 처리 (앞뒤 1.5초 크로스페이드)
    fade_len = int(SAMPLE_RATE * 1.5)
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)
    # 시작과 끝 연결
    head = bgm[:fade_len] * fade_out + bgm[-fade_len:] * fade_in
    tail = bgm[-fade_len:] * fade_out + bgm[:fade_len] * fade_in
    bgm[:fade_len] = head
    bgm[-fade_len:] = tail

    save_wav("bgm_horror.wav", bgm)

def make_footsteps():
    """
    백룸 카펫/장판 바닥 발자국 소리 4종
    - 둔탁한 저음 충격음(100~130Hz) + 카펫 마찰 스커프(400~800Hz)
    - 3종 일반 걷기 변주 + 1종 전력질주 쿵 소리
    """
    dur = 0.22
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    
    variations = [
        {"name": "footstep_1.wav", "freq": 105.0, "decay": 24.0, "noise_weight": 0.28, "pitch_mod": 1.0},
        {"name": "footstep_2.wav", "freq": 118.0, "decay": 26.0, "noise_weight": 0.32, "pitch_mod": 1.08},
        {"name": "footstep_3.wav", "freq": 98.0,  "decay": 22.0, "noise_weight": 0.25, "pitch_mod": 0.94},
        {"name": "footstep_sprint.wav", "freq": 128.0, "decay": 28.0, "noise_weight": 0.42, "pitch_mod": 1.15},
    ]

    for v in variations:
        np.random.seed(int(v["freq"] * 10))
        # 1. 둔탁한 타격 저음 (Thump)
        thump = np.sin(2 * np.pi * v["freq"] * t * np.exp(-t * 18.0)) * np.exp(-t * v["decay"])
        
        # 2. 카펫/장판 마찰 노이즈 (Scuff)
        noise = np.random.uniform(-1.0, 1.0, len(t))
        # 300~700Hz 대역 통과 모사
        kernel = np.ones(25) / 25
        smooth_noise = np.convolve(noise, kernel, mode='same')
        scuff = smooth_noise * np.exp(-t * (v["decay"] * 1.3)) * v["noise_weight"]
        
        # 3. 바닥 클릭/스냅 미세 성분
        snap = np.sin(2 * np.pi * 320.0 * v["pitch_mod"] * t) * np.exp(-t * 60.0) * 0.15
        
        step = thump + scuff + snap
        save_wav(v["name"], step)

def make_serpent_sounds():
    """
    거대 칠흑 뱀 괴물 사운드 2종
    1. serpent_slither.wav: 13.5m 거대 몸통 비늘이 바닥/벽면을 스치는 지속적 마찰음 (~4초 루프)
    2. serpent_hiss.wav: 공격 및 근접 추격 시 쉭쉭거리는 섬뜩한 파충류 포효/치찰음 (~1.8초)
    """
    # 1. Slither (비늘 마찰 및 기어가는 소리, 4초 루프)
    dur = 4.0
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(101)
    
    # 뱀의 거대 비늘이 바닥을 긁는 리드미컬한 파동 (2Hz 슬리더링 리듬)
    slither_rhythm = (np.sin(2 * np.pi * 2.2 * t) ** 2)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    # 400~1200Hz 대역 비늘 마찰음
    kernel = np.array([1, 0, -1] * 8, dtype=float)
    kernel /= np.sum(np.abs(kernel))
    scale_scrape = np.convolve(noise, kernel, mode='same') * slither_rhythm * 0.45
    
    # 묵직한 거구의 저음 진동 (Sub Rumble ~55Hz)
    body_rumble = np.sin(2 * np.pi * 55.0 * t) * (0.3 + 0.2 * slither_rhythm) * 0.35
    
    slither = scale_scrape + body_rumble
    # 루프 크로스페이드
    fl = int(SAMPLE_RATE * 0.5)
    fi = np.linspace(0, 1, fl)
    fo = np.linspace(1, 0, fl)
    slither[:fl] = slither[:fl] * fo + slither[-fl:] * fi
    slither[-fl:] = slither[-fl:] * fo + slither[:fl] * fi
    save_wav("serpent_slither.wav", slither)

    # 2. Hiss (섬뜩한 쉭쉭거리는 파충류 포효, 1.8초)
    dur_hiss = 1.8
    th = np.linspace(0, dur_hiss, int(SAMPLE_RATE * dur_hiss), endpoint=False)
    np.random.seed(202)
    
    # 고음역 치찰 노이즈 (2.5kHz ~ 6kHz 쉭- 소리)
    hiss_noise = np.random.uniform(-1.0, 1.0, len(th))
    # 고주파 강조
    hiss_high = (hiss_noise - np.roll(hiss_noise, 1)) * 0.5
    
    # 쉭- 커졌다가 길게 빠져나가는 엔벨로프
    hiss_env = (np.sin(np.pi * np.clip(th / 0.5, 0, 1)) * (th < 0.5) +
                np.exp(-(th - 0.5) * 2.8) * (th >= 0.5))
    hiss_sound = hiss_high * hiss_env * 0.65
    
    # 목구멍 저음 그르렁 (Throat Growl ~110Hz 진동)
    growl_env = np.exp(-th * 3.5)
    growl = np.sin(2 * np.pi * 95.0 * th + 2.0 * np.sin(2 * np.pi * 24.0 * th)) * growl_env * 0.45
    
    serpent_hiss = hiss_sound + growl
    save_wav("serpent_hiss.wav", serpent_hiss)

def make_skeleton_sounds():
    """
    키 큰 해골 괴물 사운드 2종
    1. skeleton_rattle.wav: 쩍 벌어진 긴 팔과 척추 뼈들이 부딪히는 기괴한 딸깍거림 (~3.5초 루프)
    2. skeleton_groan.wav: 쩍 벌어진 입에서 울려 나오는 공허하고 섬뜩한 바람 비명/신음 (~2.2초)
    """
    # 1. Rattle (뼈 부딪히는 소리, 3.5초 루프)
    dur = 3.5
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    rattle = np.zeros_like(t)
    
    # 불규칙한 뼈 클릭/탁탁 소리 배치
    np.random.seed(303)
    click_times = np.sort(np.random.uniform(0.1, dur - 0.2, 28))
    for ct in click_times:
        idx = (t >= ct) & (t < ct + 0.08)
        dt = t[idx] - ct
        # 목재/건조한 뼈 특유의 400~800Hz 빠른 댐핑 공명
        cfreq = np.random.uniform(420.0, 780.0)
        cdecay = np.random.uniform(55.0, 90.0)
        c_amp = np.random.uniform(0.25, 0.55)
        rattle[idx] += c_amp * np.sin(2 * np.pi * cfreq * dt) * np.exp(-dt * cdecay)
        
    # 루프 크로스페이드
    fl = int(SAMPLE_RATE * 0.4)
    fi = np.linspace(0, 1, fl)
    fo = np.linspace(1, 0, fl)
    rattle[:fl] = rattle[:fl] * fo + rattle[-fl:] * fi
    rattle[-fl:] = rattle[-fl:] * fo + rattle[:fl] * fi
    save_wav("skeleton_rattle.wav", rattle)

    # 2. Groan (쩍 벌어진 턱의 공허한 통로 신음/괴성, 2.2초)
    dur_g = 2.2
    tg = np.linspace(0, dur_g, int(SAMPLE_RATE * dur_g), endpoint=False)
    
    # 모음 포먼트 모사 (공허한 "아아-오오" 신음: 320Hz + 750Hz + 1150Hz)
    pitch = 145.0 + 25.0 * np.sin(2 * np.pi * 0.45 * tg)  # 음산한 피치 흔들림
    formant1 = np.sin(2 * np.pi * pitch * tg)
    formant2 = 0.5 * np.sin(2 * np.pi * (pitch * 2.2) * tg)
    formant3 = 0.3 * np.sin(2 * np.pi * (pitch * 3.8) * tg)
    
    # 턱 안에서 새어 나오는 마찰 바람소리
    np.random.seed(404)
    wind_noise = np.random.uniform(-1.0, 1.0, len(tg)) * 0.25
    
    # 부드러운 스웰 엔벨로프
    env = np.sin(np.pi * (tg / dur_g)) ** 1.8
    groan = (formant1 + formant2 + formant3 + wind_noise) * env * 0.6
    save_wav("skeleton_groan.wav", groan)

def copy_recorded_firearm(source_name, output_name):
    """Restore the real firearm recording; never replace it with synthesized audio.

    Sources, license and preparation are documented in assets/audio/SOURCES.md.
    The bundled PCM masters keep regeneration offline and dependency-free.
    """
    source = os.path.join(os.path.dirname(__file__), "assets", "audio", "recordings", source_name)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    shutil.copyfile(source, os.path.join(OUTPUT_DIR, output_name))
    print(f"Copied recorded firearm: {output_name}")


def make_gunshot():
    """Actual pistol discharge, shared by single and dual pistols."""
    copy_recorded_firearm("pistol.wav", "gunshot.wav")


def make_shotgun_blast():
    """Actual shotgun discharge."""
    copy_recorded_firearm("shotgun.wav", "shotgun_blast.wav")


def make_tactical_sfx():
    """콤보 킬 효과음 및 보급 상자 오픈 효과음 합성"""

    # 2. combo_kill.wav (타격감 넘치는 상승 2음계 콤보 신호음: F# -> A#)
    dur_c = 0.42
    tc = np.linspace(0, dur_c, int(SAMPLE_RATE * dur_c), endpoint=False)
    combo = np.zeros_like(tc)
    # 음 1 (F#5 ~ 740Hz)
    idx1 = tc < 0.16
    t1 = tc[idx1]
    combo[idx1] += (np.sin(2 * np.pi * 740.0 * t1) + 0.3 * np.sin(2 * np.pi * 1480.0 * t1)) * np.exp(-t1 * 12.0)
    # 음 2 (A#5 ~ 932Hz, 더 높고 짜릿한 음)
    idx2 = tc >= 0.14
    t2 = tc[idx2] - 0.14
    combo[idx2] += (np.sin(2 * np.pi * 932.0 * t2) + 0.4 * np.sin(2 * np.pi * 1864.0 * t2)) * np.exp(-t2 * 10.0)
    save_wav("combo_kill.wav", combo * 0.85)

    # 3. crate_open.wav (기계식 래치 해제 찰칵 + 묵직한 상자 개봉음)
    dur_o = 0.65
    to = np.linspace(0, dur_o, int(SAMPLE_RATE * dur_o), endpoint=False)
    # 금속 래치 래칫 찰칵 (Mechanical click)
    np.random.seed(606)
    click = np.random.uniform(-0.8, 0.8, len(to)) * np.exp(-to * 45.0)
    # 묵직한 뚜껑 열림 및 공명 험
    heavy = np.sin(2 * np.pi * (160.0 - 60.0 * to) * to) * np.exp(-to * 8.0) * 0.7
    pneumatic = np.random.uniform(-0.5, 0.5, len(to)) * np.exp(-(to - 0.08)**2 / 0.012) * 0.5
    crate = click + heavy + pneumatic
    save_wav("crate_open.wav", crate * 0.85)

def make_orc_sounds():
    """진흙 오크 괴물 3D 접근 이동음 (쿵쿵 발소리 & 그르렁 포효)"""
    # 1. orc_step.wav (묵직한 거구의 지면 강타 발소리)
    dur = 0.32
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(801)
    thump = np.sin(2 * np.pi * (85.0 * np.exp(-t * 26.0) + 48.0) * t) * np.exp(-t * 18.0) * 1.2
    noise = np.random.uniform(-1.0, 1.0, len(t))
    kernel = np.ones(30) / 30
    scuff = np.convolve(noise, kernel, mode='same') * np.exp(-t * 24.0) * 0.65
    save_wav("orc_step.wav", thump + scuff)

    # 2. orc_growl.wav (성난 진흙 오크의 목구멍 그르렁 포효/거친 숨소리)
    dur_g = 1.4
    tg = np.linspace(0, dur_g, int(SAMPLE_RATE * dur_g), endpoint=False)
    np.random.seed(802)
    pitch = 75.0 + 18.0 * np.sin(2 * np.pi * 3.5 * tg)
    f1 = np.sin(2 * np.pi * pitch * tg + 1.8 * np.sin(2 * np.pi * 32.0 * tg))
    f2 = 0.5 * np.sin(2 * np.pi * pitch * 2.1 * tg)
    env = np.sin(np.pi * (tg / dur_g)) ** 1.6
    rough_noise = np.random.uniform(-0.4, 0.4, len(tg)) * np.exp(-((tg - 0.5)**2) / 0.15)
    save_wav("orc_growl.wav", (f1 + f2 + rough_noise) * env)

def make_witch_sounds():
    """잿더미 마녀 3D 접근 이동음 (공중 부유 위스퍼/읊조림)"""
    dur_w = 1.6
    tw = np.linspace(0, dur_w, int(SAMPLE_RATE * dur_w), endpoint=False)
    np.random.seed(803)
    wnoise = np.random.uniform(-1.0, 1.0, len(tw))
    wk = np.sin(np.linspace(0, 2 * np.pi * 5, 25)) * np.hanning(25)
    wk /= np.sum(np.abs(wk)) + 1e-6
    wfilt = np.convolve(wnoise, wk, mode='same') * 0.4
    wdrone = 0.3 * np.sin(2 * np.pi * (220.0 + 45.0 * np.sin(2 * np.pi * 1.5 * tw)) * tw)
    wdrone += 0.2 * np.sin(2 * np.pi * 330.0 * tw)
    wenv = np.sin(np.pi * (tw / dur_w)) ** 1.5
    save_wav("witch_whisper.wav", (wfilt + wdrone) * wenv)

def make_action_sfx():
    """불릿 타임, 오버차지 폭발탄, 헤드샷 타격감 및 정예 처치 효과음 합성"""
    make_bullet_time_sounds()

    # 3. heartbeat.wav (심장 박동 저주파 더블 쿵-쿵 펄스)
    dur_hb = 0.72
    thb = np.linspace(0, dur_hb, int(SAMPLE_RATE * dur_hb), endpoint=False)
    hb = np.zeros_like(thb)
    # 1st thump (0.0s)
    idx_hb1 = thb < 0.26
    t_hb1 = thb[idx_hb1]
    hb[idx_hb1] += np.sin(2 * np.pi * (62.0 * np.exp(-t_hb1 * 12.0) + 36.0) * t_hb1) * np.exp(-t_hb1 * 14.0) * 1.25
    # 2nd thump (0.24s)
    idx_hb2 = (thb >= 0.22) & (thb < 0.52)
    t_hb2 = thb[idx_hb2] - 0.22
    hb[idx_hb2] += np.sin(2 * np.pi * (52.0 * np.exp(-t_hb2 * 14.0) + 32.0) * t_hb2) * np.exp(-t_hb2 * 15.0) * 0.95
    save_wav("heartbeat.wav", np.tanh(hb * 1.15) * 0.90)

    # 4. overcharge_shot.wav (초강력 플라즈마 폭발 소이탄 격발음)
    dur_oc = 0.75
    toc = np.linspace(0, dur_oc, int(SAMPLE_RATE * dur_oc), endpoint=False)
    # 레이저 스냅
    snap = np.sin(2 * np.pi * (3200.0 * np.exp(-toc * 65.0) + 240.0) * toc) * np.exp(-toc * 38.0) * 1.1
    # 플라즈마 화염 서브베이스 폭발
    plasma_sub = np.sin(2 * np.pi * (380.0 * np.exp(-toc * 16.0) + 48.0) * toc) * np.exp(-toc * 9.0) * 1.4
    # 전기 지직거림
    elec_noise = np.random.uniform(-0.9, 0.9, len(toc)) * np.exp(-toc * 18.0) * np.sin(2 * np.pi * 120.0 * toc)
    elec_k = np.hanning(18) / np.sum(np.hanning(18))
    elec_filtered = np.convolve(elec_noise, elec_k, mode='same') * 0.75
    # 에코 잔향
    oc_raw = snap * 0.9 + plasma_sub * 1.2 + elec_filtered * 0.8
    oc_shot = np.tanh(oc_raw * 1.6)
    save_wav("overcharge_shot.wav", oc_shot * 0.95)

    # 5. headshot_crunch.wav (두개골 파열 뼈 분쇄 치명타음)
    dur_hc = 0.36
    thc = np.linspace(0, dur_hc, int(SAMPLE_RATE * dur_hc), endpoint=False)
    crack = np.sin(2 * np.pi * 3600.0 * thc) * np.exp(-thc * 85.0) * 0.9
    crunch_noise = np.random.uniform(-1.0, 1.0, len(thc)) * np.exp(-thc * 22.0)
    crunch_k = np.array([1, -0.7, 0.4, -0.2])
    crunch_f = np.convolve(crunch_noise, crunch_k, mode='same') * 0.75
    bone_thump = np.sin(2 * np.pi * (240.0 * np.exp(-thc * 30.0) + 75.0) * thc) * np.exp(-thc * 20.0) * 0.85
    headshot = np.tanh((crack + crunch_f + bone_thump) * 1.4)
    save_wav("headshot_crunch.wav", headshot * 0.92)

    # 6. elite_kill.wav (정예 몬스터 격퇴 웅장한 시네마틱 타격음)
    dur_ek = 1.35
    tek = np.linspace(0, dur_ek, int(SAMPLE_RATE * dur_ek), endpoint=False)
    chord = (
        0.50 * np.sin(2 * np.pi * 55.0 * tek) +
        0.35 * np.sin(2 * np.pi * 110.0 * tek) +
        0.30 * np.sin(2 * np.pi * 164.8 * tek) +
        0.25 * np.sin(2 * np.pi * 220.0 * tek) +
        0.20 * np.sin(2 * np.pi * 329.6 * tek)
    ) * np.exp(-tek * 2.8)
    impact_blast = np.random.uniform(-0.8, 0.8, len(tek)) * np.exp(-tek * 16.0) * 0.6
    ek_sound = np.tanh((chord + impact_blast) * 1.35)
    save_wav("elite_kill.wav", ek_sound * 0.92)

def make_shotgun_and_dual_sfx():
    """Restore recorded firing and mechanical actions, never synthesized tones."""
    make_shotgun_blast()
    for name in ("shotgun_pump.wav", "weapon_switch.wav", "empty_click.wav",
                 "reload.wav", "dual_reload.wav", "shotgun_reload.wav", "slide_release.wav"):
        copy_recorded_firearm(name, name)


def make_hound_sounds():
    """지옥의 파수견 (뼈로 된 도베르만) 사운드 효과 합성: 으르렁, 도약 회피, 뼈 발자국, 사망 비명"""
    # 1. hound_growl.wav (포식자 도베르만의 굵은 으르렁거림 & 턱 덜컹임)
    dur_g = 0.85
    tg = np.linspace(0, dur_g, int(SAMPLE_RATE * dur_g), endpoint=False)
    fm = 135.0 + 35.0 * np.sin(2 * np.pi * 14.0 * tg)
    growl_tone = np.sin(2 * np.pi * fm * tg) * np.exp(-tg * 1.2) * 0.8
    np.random.seed(811)
    growl_noise = np.random.uniform(-0.6, 0.6, len(tg)) * (0.6 + 0.4 * np.sin(2 * np.pi * 28.0 * tg)) * np.exp(-tg * 1.5)
    gk = np.hanning(35) / np.sum(np.hanning(35))
    filt_growl = np.convolve(growl_noise, gk, mode='same') * 0.95
    # 이빨 딱딱 부딪히는 클러터
    snap = np.zeros_like(tg)
    for snap_t in [0.15, 0.42, 0.68]:
        s_idx = (tg >= snap_t) & (tg < snap_t + 0.08)
        s_dt = tg[s_idx] - snap_t
        snap[s_idx] += np.sin(2 * np.pi * 1950.0 * s_dt) * np.exp(-s_dt * 85.0) * 0.7
    save_wav("hound_growl.wav", np.tanh((growl_tone + filt_growl + snap) * 1.5) * 0.92)

    # 2. hound_dodge.wav (총알을 피하며 공중으로 도약 회피하는 뼈 덜컹임 & 바람 가르는 소리)
    dur_d = 0.42
    td = np.linspace(0, dur_d, int(SAMPLE_RATE * dur_d), endpoint=False)
    # 급속 공기 가르기 (Air Dash Whoosh)
    dash_whoosh = np.sin(2 * np.pi * 240.0 * td) * np.sin(np.pi * (td / dur_d)) * 0.75
    dash_noise = np.random.uniform(-0.8, 0.8, len(td)) * np.sin(np.pi * (td / dur_d)) ** 2 * 0.85
    # 뼈 관절 급회전 달각거림 (Bone clatter)
    bone_clatter = np.zeros_like(td)
    for c_t in [0.04, 0.11, 0.18, 0.25]:
        c_idx = (td >= c_t) & (td < c_t + 0.06)
        c_dt = td[c_idx] - c_t
        bone_clatter[c_idx] += np.sin(2 * np.pi * (1600.0 + random.uniform(-200, 200)) * c_dt) * np.exp(-c_dt * 65.0) * 0.6
    save_wav("hound_dodge.wav", np.tanh((dash_whoosh + dash_noise + bone_clatter) * 1.4) * 0.92)

    # 3. hound_death.wav (단말마의 하울링 비명 & 뼈 박살)
    dur_k = 0.95
    tk = np.linspace(0, dur_k, int(SAMPLE_RATE * dur_k), endpoint=False)
    howl_f = 620.0 * np.exp(-tk * 2.8) + 95.0
    howl = np.sin(2 * np.pi * howl_f * tk) * np.exp(-tk * 2.2) * 0.85
    crush = np.random.uniform(-1.0, 1.0, len(tk)) * np.exp(-tk * 6.5) * 1.1
    ck = np.hanning(25) / np.sum(np.hanning(25))
    crush_filt = np.convolve(crush, ck, mode='same')
    save_wav("hound_death.wav", np.tanh((howl + crush_filt) * 1.5) * 0.94)

    # 4. hound_step.wav (빠른 4족 골격 발톱의 바닥 타격음)
    dur_st = 0.16
    tst = np.linspace(0, dur_st, int(SAMPLE_RATE * dur_st), endpoint=False)
    claw_tap = np.sin(2 * np.pi * 2800.0 * tst) * np.exp(-tst * 75.0) * 0.95
    sub_tap = np.sin(2 * np.pi * 160.0 * tst) * np.exp(-tst * 38.0) * 0.65
    save_wav("hound_step.wav", np.tanh(claw_tap + sub_tap) * 0.88)

def make_bullet_time_sounds():
    """Seamless warm hum; playback slows its pitch during bullet-time entry."""
    t = np.arange(SAMPLE_RATE * 4) / SAMPLE_RATE
    # Integer cycles at every layer keep the loop free of clicks. Harmonics
    # keep the slowing hum audible on speakers without strong sub-bass.
    phase = 2 * np.pi * 140.0 * t + 0.16 * np.sin(2 * np.pi * 0.5 * t)
    hum = (np.sin(phase) + 0.40 * np.sin(2 * phase)
           + 0.20 * np.sin(3 * phase) + 0.08 * np.sin(4 * phase))
    hum *= 0.94 + 0.06 * np.cos(2 * np.pi * 0.5 * t)
    save_wav("bullet_time_hum.wav", hum)

if __name__ == "__main__":
    print("=== 백룸 호러 사운드 절차적 합성 시작 ===")
    make_bgm()
    make_footsteps()
    make_serpent_sounds()
    make_skeleton_sounds()
    make_orc_sounds()
    make_witch_sounds()
    make_gunshot()
    make_tactical_sfx()
    make_action_sfx()
    make_shotgun_and_dual_sfx()
    make_hound_sounds()
    print("=== 모든 사운드 생성 완료! ===")
