# 탄피 개선 모듈 (CasingEffects) 통합 가이드

Codex가 `combat_system.py`에 `casing_effects.py`를 무결점으로 연결할 수 있도록 작성된 상세 통합 지침입니다.
파일 소유권 원칙에 따라 `combat_system.py`는 수정하지 않았으며, 아래 코드 조각을 해당 위치에 반영해 주시면 됩니다.

---

## 1. 모듈 임포트
`combat_system.py` 상단 임포트 영역에 추가:
```python
from casing_effects import CasingEffects
```

---

## 2. 풀 초기화 (`_init_pools`)
`combat_system.py`의 `_init_pools` 메서드 내 기존 24개 탄피 풀 생성 루프(약 lines 227~245) 대체:

```python
        # 2. 3D 탄피 물리 풀 (24개 고정 풀, CasingEffects 모듈 위임)
        self.casing_effects = CasingEffects(self.world_root, capacity=24)
```

*(기존 `self.casing_pool` 및 `self.casing_cursor` 참조는 호환성을 위해 `self.casing_effects`로 대체)*

---

## 3. 탄피 배출 메서드 (`_eject_casing`)
기존 카메라 기준의 고정 배출 방식 대신, 실제 무기 recoil_node의 배출구 위치와 방향을 `world_root` 좌표계로 변환하여 사출합니다.
카메라 바로 앞이나 조준선을 가리지 않고 총기 우측(좌측 쌍권총은 좌측)으로 자연스럽게 튕겨나갑니다.

`_eject_casing` 구현 코드:

```python
    def _eject_casing(self, is_left=False, is_shotgun=False):
        """격발/펌프 시 총기 배출구의 3D 월드 좌표에서 무기별 특화 탄피 배출"""
        if not hasattr(self, 'casing_effects') or not self.casing_effects:
            return

        cam_quat = self.camera.getQuat()
        cam_right = cam_quat.getRight()
        cam_up = cam_quat.getUp()
        cam_fwd = cam_quat.getForward()
        cam_pos = self.camera.getPos()

        # (1) 샷건 (12게이지 붉은색 헐 + 황동 베이스 셸)
        if is_shotgun or self.current_weapon == "SHOTGUN":
            weapon_type = "SHOTGUN"
            node = getattr(self, 'sg_recoil_node', None)
            if node and not node.isEmpty():
                # 리시버 우측 배출창 (0.045, 0.040, 0.035)
                eject_pos = self.world_root.getRelativePoint(node, Vec3(0.045, 0.040, 0.035))
                r = self.world_root.getRelativeVector(node, Vec3(1, 0, 0))
                u = self.world_root.getRelativeVector(node, Vec3(0, 0, 1))
                f = self.world_root.getRelativeVector(node, Vec3(0, 1, 0))
            else:
                eject_pos = cam_pos + cam_fwd * 0.55 + cam_right * 0.20 - cam_up * 0.16
                r, u, f = cam_right, cam_up, cam_fwd
            
            # 묵직한 12게이지 셸 우측 사출 속도
            vel = r * random.uniform(1.8, 2.6) + u * random.uniform(1.0, 1.8) - f * random.uniform(0.2, 0.6)
            self.casing_effects.emit("SHOTGUN", eject_pos, vel, is_left=False)
            return

        # (2) 아킴보 쌍권총 (9mm 글록 탄피)
        if self.current_weapon == "DUAL_PISTOL":
            weapon_type = "DUAL_PISTOL"
            if is_left:
                node = getattr(self, 'dual_left_recoil', None)
                if node and not node.isEmpty():
                    # 좌측 글록 배출창 (-0.030, 0.045, 0.045)
                    eject_pos = self.world_root.getRelativePoint(node, Vec3(-0.030, 0.045, 0.045))
                    l = self.world_root.getRelativeVector(node, Vec3(-1, 0, 0))
                    u = self.world_root.getRelativeVector(node, Vec3(0, 0, 1))
                    f = self.world_root.getRelativeVector(node, Vec3(0, 1, 0))
                else:
                    eject_pos = cam_pos + cam_fwd * 0.50 - cam_right * 0.22 - cam_up * 0.18
                    l, u, f = -cam_right, cam_up, cam_fwd
                vel = l * random.uniform(2.0, 3.0) + u * random.uniform(1.2, 1.8) - f * random.uniform(0.1, 0.4)
                self.casing_effects.emit("DUAL_PISTOL", eject_pos, vel, is_left=True)
            else:
                node = getattr(self, 'dual_right_recoil', None)
                if node and not node.isEmpty():
                    # 우측 글록 배출창 (0.030, 0.045, 0.045)
                    eject_pos = self.world_root.getRelativePoint(node, Vec3(0.030, 0.045, 0.045))
                    r = self.world_root.getRelativeVector(node, Vec3(1, 0, 0))
                    u = self.world_root.getRelativeVector(node, Vec3(0, 0, 1))
                    f = self.world_root.getRelativeVector(node, Vec3(0, 1, 0))
                else:
                    eject_pos = cam_pos + cam_fwd * 0.50 + cam_right * 0.22 - cam_up * 0.18
                    r, u, f = cam_right, cam_up, cam_fwd
                vel = r * random.uniform(2.0, 3.0) + u * random.uniform(1.2, 1.8) - f * random.uniform(0.1, 0.4)
                self.casing_effects.emit("DUAL_PISTOL", eject_pos, vel, is_left=False)
            return

        # (3) 돌격소총 (HK416 5.56mm 라이플 탄피)
        if self.current_weapon == "AR":
            node = getattr(self, 'ar_recoil_node', None)
            if node and not node.isEmpty():
                # 상부 리시버 배출구 및 케이스 디플렉터 기준 (0.042, 0.050, 0.038)
                eject_pos = self.world_root.getRelativePoint(node, Vec3(0.042, 0.050, 0.038))
                r = self.world_root.getRelativeVector(node, Vec3(1, 0, 0))
                u = self.world_root.getRelativeVector(node, Vec3(0, 0, 1))
                f = self.world_root.getRelativeVector(node, Vec3(0, 1, 0))
            else:
                eject_pos = cam_pos + cam_fwd * 0.55 + cam_right * 0.18 - cam_up * 0.15
                r, u, f = cam_right, cam_up, cam_fwd
            # 케이스 디플렉터에 맞고 튕겨나가는 경쾌한 우측 사출
            vel = r * random.uniform(2.4, 3.4) + u * random.uniform(1.4, 2.2) + f * random.uniform(-0.3, 0.2)
            self.casing_effects.emit("AR", eject_pos, vel, is_left=False)
            return

        # (4) 기본 권총 (.50 AE 데저트 이글 대구경 매그넘 탄피)
        node = getattr(self, 'recoil_node', None)
        if node and not node.isEmpty():
            # 슬라이드 우측 약실 배출창 (0.040, 0.040, 0.045)
            eject_pos = self.world_root.getRelativePoint(node, Vec3(0.040, 0.040, 0.045))
            r = self.world_root.getRelativeVector(node, Vec3(1, 0, 0))
            u = self.world_root.getRelativeVector(node, Vec3(0, 0, 1))
            f = self.world_root.getRelativeVector(node, Vec3(0, 1, 0))
        else:
            eject_pos = cam_pos + cam_fwd * 0.55 + cam_right * 0.20 - cam_up * 0.16
            r, u, f = cam_right, cam_up, cam_fwd
        vel = r * random.uniform(2.2, 3.2) + u * random.uniform(1.2, 2.0) - f * random.uniform(0.1, 0.5)
        self.casing_effects.emit("PISTOL", eject_pos, vel, is_left=False)
```

---

## 4. 샷건 펌프 배출 타이밍 점검
- `shoot()` 시 샷건은 `_eject_casing`을 직접 호출하지 않습니다 (기존 코드 유지).
- `_update_shotgun_pump(dt)`에서 펌프 진행도 35% 도달 시:
```python
        if progress >= 0.35 and not self.sg_pump_cycled:
            self.sg_pump_cycled = True
            self._eject_casing(is_left=False, is_shotgun=True)
```
이 호출로 12게이지 샷건 셸이 정확한 타이밍에 배출됩니다.

---

## 5. 프레임 갱신 (`update`)
`combat_system.py`의 `update(dt)` 내 기존 탄피 루프(lines 2413~2434)를 다음 한 줄로 대체:

```python
        # 3. 3D 탄피 물리 풀 갱신 (CasingEffects 모듈 위임)
        if hasattr(self, 'casing_effects') and self.casing_effects:
            self.casing_effects.update(dt)
```

---

## 6. 리셋 및 종료 정리 (`reset`, `destroy`)
- `reset(self)` 내:
```python
        if hasattr(self, 'casing_effects') and self.casing_effects:
            self.casing_effects.clear()
```
- `destroy(self)` 내:
```python
        if hasattr(self, 'casing_effects') and self.casing_effects:
            self.casing_effects.destroy()
```
