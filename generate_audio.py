import os
import wave
import struct
import math
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

def make_gunshot():
    """
    둔탁하고 웅장한 실감형 권총 발사음
    1. 서브베이스 타격 펀치 (Sub-bass punch: 160Hz -> 38Hz 급격한 피치 드롭, 가슴을 울리는 저음 쿵)
    2. 화약 폭발음 및 강철 슬라이드 파열음 (Gunpowder blast + Saturation snap)
    3. 중저역 바디 공명 (Mid-low body resonance 120~280Hz)
    4. 백룸 거대 홀의 웅장한 공간 잔향 및 메아리 (Grand multi-tap hall reverb & tail)
    """
    dur = 1.35
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(777)

    # 1. 서브베이스 펀치 (둔탁한 저음 쿵)
    pitch_env = 160.0 * np.exp(-t * 38.0) + 38.0
    sub_thump = np.sin(2 * np.pi * pitch_env * t) * np.exp(-t * 15.0)
    sub_thump_2 = np.sin(2 * np.pi * 55.0 * t + 0.3) * np.exp(-t * 11.0) * 0.75

    # 2. 화약 폭발음 및 메탈 파열음 (Gunpowder blast & Mechanical crack)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    blast_env = np.exp(-t * 42.0)
    blast = noise * blast_env
    blast_saturated = np.tanh(blast * 4.5) * 0.95

    # 3. 묵직한 중저역 바디 공명 (Body resonance)
    body_res1 = np.sin(2 * np.pi * 125.0 * t) * np.exp(-t * 18.0) * 0.6
    body_res2 = np.sin(2 * np.pi * 240.0 * t) * np.exp(-t * 25.0) * 0.4

    core_shot = (sub_thump * 1.2 + sub_thump_2 * 0.8 + blast_saturated * 1.1 + body_res1 + body_res2)

    # 4. 백룸 거대 복도 웅장한 다중 반사 & 메아리 (Multi-tap Hall Reverb Tail)
    reverb = np.zeros_like(t)
    delays = [0.018, 0.042, 0.075, 0.115, 0.165, 0.230, 0.310, 0.420, 0.560, 0.720]
    gains =  [0.65,  0.52,  0.42,  0.34,  0.27,  0.21,  0.16,  0.12,  0.08,  0.05]

    for delay_s, gain in zip(delays, gains):
        d_idx = int(delay_s * SAMPLE_RATE)
        if d_idx < len(t):
            lowpass_noise = np.convolve(noise[:len(t)-d_idx], np.ones(12)/12.0, mode='same')
            reverb[d_idx:] += lowpass_noise * np.exp(-(t[:len(t)-d_idx]) * 4.5) * gain
            sub_echo = np.sin(2 * np.pi * 48.0 * t[:len(t)-d_idx]) * np.exp(-(t[:len(t)-d_idx]) * 3.8) * (gain * 0.7)
            reverb[d_idx:] += sub_echo

    full_gunshot = core_shot + reverb * 0.85
    save_wav("gunshot.wav", full_gunshot)

def make_flesh_impact():
    """생체 피격 타격음 (Flesh / Bone Impact Thud)"""
    dur = 0.28
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(888)

    thud_pitch = 120.0 * np.exp(-t * 35.0) + 40.0
    thud = np.sin(2 * np.pi * thud_pitch * t) * np.exp(-t * 22.0)

    noise = np.random.uniform(-1.0, 1.0, len(t))
    crunch_env = np.exp(-t * 28.0) * (1.0 + np.sin(2 * np.pi * 450.0 * t) * 0.4)
    crunch = noise * crunch_env
    crunch_sat = np.tanh(crunch * 3.0) * 0.7

    impact = (thud * 1.3 + crunch_sat * 0.9)
    save_wav("bullet_impact_flesh.wav", impact)

def make_kill_impact():
    """치명타 처치음 (Lethal Elimination Heavy Crunch & Gore Burst)"""
    dur = 0.42
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(999)

    pitch = 140.0 * np.exp(-t * 25.0) + 32.0
    sub = np.sin(2 * np.pi * pitch * t) * np.exp(-t * 12.0)

    noise = np.random.uniform(-1.0, 1.0, len(t))
    shatter = noise * np.exp(-t * 20.0)
    shatter_sat = np.tanh(shatter * 4.0) * 0.85

    kill_snd = sub * 1.4 + shatter_sat * 1.1
    save_wav("bullet_impact_kill.wav", kill_snd)

def make_wall_impact():
    """벽체 탄착음 (Concrete / Plaster Ricochet Chip)"""
    dur = 0.22
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    np.random.seed(111)
    
    chip_freq = 2400.0 * np.exp(-t * 40.0) + 800.0
    chip = np.sin(2 * np.pi * chip_freq * t) * np.exp(-t * 35.0)
    
    noise = np.random.uniform(-1.0, 1.0, len(t))
    debris = noise * np.exp(-t * 32.0)
    
    wall_snd = chip * 0.8 + debris * 0.7
    save_wav("bullet_impact_wall.wav", wall_snd)


def make_medieval_inversion_sounds():
    """심층 이계화 나팔 및 그림자 스토커 음향 합성"""
    # 1. Abyssal Horn
    dur = 3.6
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    f0 = 70.0 - 5.0 * (1.0 - np.exp(-t * 1.5))
    flutter = 1.0 + 0.04 * np.sin(2 * np.pi * 5.2 * t)
    phase = 2 * np.pi * np.cumsum(f0 * flutter) / SAMPLE_RATE

    horn_raw = (
        1.0 * np.sin(phase) +
        0.75 * np.sin(2 * phase) +
        0.55 * np.sin(3 * phase) +
        0.40 * np.sin(4 * phase) +
        0.28 * np.sin(5 * phase) +
        0.18 * np.sin(6 * phase)
    )
    horn_dist = np.tanh(horn_raw * 3.2)
    attack = np.minimum(1.0, t / 0.28)
    decay = np.exp(-np.maximum(0.0, t - 2.0) * 1.8)
    core_horn = horn_dist * (attack * decay)

    reverb = np.zeros_like(core_horn)
    delays = [0.16, 0.32, 0.58, 0.92, 1.35]
    gains = [0.45, 0.32, 0.22, 0.14, 0.08]
    for d, g in zip(delays, gains):
        d_idx = int(d * SAMPLE_RATE)
        if d_idx < len(core_horn):
            reverb[d_idx:] += core_horn[:len(core_horn)-d_idx] * g
    abyssal_horn = core_horn + reverb * 0.75
    save_wav("abyssal_horn.wav", abyssal_horn)
    save_wav("siren_alarm.wav", abyssal_horn)

    # 2. Eclipse Purify Bell
    dur_b = 3.2
    tb = np.linspace(0, dur_b, int(SAMPLE_RATE * dur_b), endpoint=False)
    partials = [
        (293.66, 1.0, 1.2),
        (440.0, 0.75, 1.6),
        (587.33, 0.60, 2.1),
        (880.0, 0.40, 2.8),
        (1174.66, 0.25, 3.6),
    ]
    bell = np.zeros_like(tb)
    for freq, amp, dec in partials:
        bell += amp * np.sin(2 * np.pi * freq * tb) * np.exp(-tb * dec)
    noise = np.random.uniform(-1, 1, len(tb)) * np.exp(-tb * 28.0) * 0.25
    save_wav("eclipse_purify.wav", bell + noise)
    save_wav("power_restored.wav", bell + noise)

    # 3. Stalker Shriek & Lunge
    dur_s = 1.35
    ts = np.linspace(0, dur_s, int(SAMPLE_RATE * dur_s), endpoint=False)
    pitch_sweep = 1450.0 * np.exp(-ts * 1.8) + 450.0
    mod = np.sin(2 * np.pi * 92.0 * ts) * 480.0
    shriek_phase = 2 * np.pi * np.cumsum(pitch_sweep + mod) / SAMPLE_RATE
    screech = np.sin(shriek_phase) * np.exp(-ts * 2.2)
    hiss_noise = np.random.uniform(-1, 1, len(ts)) * np.exp(-ts * 3.0) * 0.65
    shriek = np.tanh((screech + hiss_noise) * 2.5)
    save_wav("stalker_shriek.wav", shriek)

    dur_l = 0.50
    tl = np.linspace(0, dur_l, int(SAMPLE_RATE * dur_l), endpoint=False)
    whoosh = np.random.uniform(-1, 1, len(tl)) * (np.sin(np.pi * np.minimum(1.0, tl / 0.45)) ** 2)
    save_wav("stalker_lunge.wav", whoosh)

def make_attack_warnings():
    """공격 준비 시간에 맞춘 종별 모노 예고음. 기존 효과음은 변경하지 않습니다."""
    for filename, duration, start_hz, end_hz in (
        ('orc_slam_charge.wav', 0.5, 95.0, 165.0),
        ('witch_cast_charge.wav', 0.4, 480.0, 1250.0),
        ('stalker_lunge_charge.wav', 0.45, 1500.0, 650.0),
    ):
        t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
        phase = 2 * np.pi * (start_hz * t + (end_hz - start_hz) * t * t / (2 * duration))
        envelope = np.sin(np.pi * t / duration) ** 0.7
        tone = np.sin(phase) + 0.3 * np.sin(phase * 2.03)
        if filename.startswith('orc'):
            tone += 0.35 * np.sin(phase * 0.5)
        elif filename.startswith('stalker'):
            envelope *= 0.35 + 0.65 * np.sin(np.pi * 2 * t / duration) ** 2
        save_wav(filename, tone * envelope * 0.5)


if __name__ == "__main__":
    print("=== 백룸 호러 사운드 절차적 생성 시작 ===")
    make_bgm()
    make_footsteps()
    make_serpent_sounds()
    make_skeleton_sounds()
    make_gunshot()
    make_flesh_impact()
    make_kill_impact()
    make_wall_impact()
    make_medieval_inversion_sounds()
    make_attack_warnings()
    print("=== 모든 사운드 생성 완료! ===")
