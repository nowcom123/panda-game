"""World representation and interaction for dropped RPG loot items."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

try:
    from panda3d.core import LColor, LVector3, NodePath, Point3
    from geometry import make_cube_to, make_sphere_to, make_cylinder_to
    HAS_PANDA3D = True
except ImportError:
    HAS_PANDA3D = False
    NodePath = object  # type: ignore
    LColor = None  # type: ignore
    LVector3 = None  # type: ignore
    Point3 = None  # type: ignore

try:
    from collision import get_nearby_colliders
    from world_gen import check_line_of_sight
except ImportError:
    get_nearby_colliders = None  # type: ignore
    check_line_of_sight = None  # type: ignore

from rpg.equipment_ui import RARITY_COLORS, RARITY_NAMES
from rpg.items import ItemInstance
from rpg.run_loot import RunLootBag
from rpg.session import RPGSession

MAX_WORLD_LOOT_CAPACITY = 40
INTERACTION_MAX_DIST = 2.5
INTERACTION_MAX_DZ = 1.5

ITEM_NAMES = {
    "weapon_pistol": "데저트 이글 권총",
    "weapon_dual_pistol": "쌍권총 (듀얼 피스톨)",
    "weapon_ar": "돌격소총 (AR)",
    "weapon_shotgun": "산탄총 (샷건)",
    "scrap_metal": "고철 파편",
    "bone_fragment": "해골 뼛조각",
}


def get_item_name(item: ItemInstance, catalog: Mapping[str, Any] | None = None) -> str:
    if catalog and item.definition_id in catalog:
        return catalog[item.definition_id].name
    return ITEM_NAMES.get(item.definition_id, item.definition_id)


class LootWorldItem:
    """A 3D physical representation of a dropped RPG item in the game world."""

    def __init__(
        self,
        parent_node: Any,
        pos: tuple[float, float, float] | Any,
        item: ItemInstance,
        catalog: Mapping[str, Any] | None = None,
    ) -> None:
        self.item = item
        self.catalog = catalog
        self.is_collected: bool = False
        self.anim_time: float = 0.0

        # Unpack position coordinates
        if hasattr(pos, "x") and hasattr(pos, "y"):
            self.base_x = float(pos.x)
            self.base_y = float(pos.y)
            self.base_z = float(getattr(pos, "z", 0.35)) + 0.15
        elif isinstance(pos, (tuple, list)):
            self.base_x = float(pos[0])
            self.base_y = float(pos[1])
            self.base_z = float(pos[2]) if len(pos) > 2 else 0.35
        else:
            self.base_x = 0.0
            self.base_y = 0.0
            self.base_z = 0.35

        self.node: Any = None
        self._build_visual(parent_node)

    @property
    def display_name(self) -> str:
        rarity_ko = RARITY_NAMES.get(self.item.rarity, "일반")
        name = get_item_name(self.item, self.catalog)
        if self.item.quantity > 1:
            return f"[{rarity_ko}] {name} x{self.item.quantity}"
        return f"[{rarity_ko}] {name}"

    def _build_visual(self, parent_node: Any) -> None:
        if not HAS_PANDA3D or parent_node is None:
            return

        rgba = RARITY_COLORS.get(self.item.rarity, (0.85, 0.85, 0.85, 1.0))
        color = LColor(rgba[0], rgba[1], rgba[2], rgba[3])

        self.node = parent_node.attachNewNode(f"loot_{self.item.uid[:8]}")
        self.node.setPos(self.base_x, self.base_y, self.base_z)

        is_weapon = self.item.definition_id.startswith("weapon_")
        if is_weapon:
            # Floating rotating diamond crystal
            core = make_cube_to(
                self.node, 0.26, 0.26, 0.26, color, 0, 0, 0, rot_h=45, rot_p=45, rot_r=0
            )
            core.setLightOff()
            accent = make_cube_to(
                self.node, 0.34, 0.34, 0.04, LColor(1.0, 1.0, 1.0, 0.8), 0, 0, 0, rot_h=45, rot_p=45, rot_r=0
            )
            accent.setLightOff()
        else:
            # Material scrap or canister
            mat_col = color if self.item.rarity != "common" else LColor(0.75, 0.80, 0.85, 1.0)
            core = make_cube_to(
                self.node, 0.22, 0.22, 0.22, mat_col, 0, 0, 0, rot_h=0, rot_p=0, rot_r=0
            )
            core.setLightOff()
            ring = make_cylinder_to(
                self.node, 0.30, 0.30, 0.04, LColor(0.95, 0.90, 0.40, 0.9), 0, 0, 0, axis="z"
            )
            ring.setLightOff()

    def update(self, dt: float) -> None:
        if self.is_collected or not self.node:
            return
        self.anim_time += dt
        # Light yaw rotation without per-frame geometry creation
        yaw = (self.anim_time * 65.0) % 360.0
        bob = math.sin(self.anim_time * 3.2) * 0.07
        self.node.setH(yaw)
        self.node.setZ(self.base_z + bob)

    def destroy(self) -> None:
        self.is_collected = True
        if self.node and not self.node.isEmpty():
            self.node.removeNode()
            self.node = None


class LootWorldManager:
    """Manages active ground loot drops, limits, LOS checks, and player pickup."""

    def __init__(
        self,
        render: Any,
        world_root: Any,
        catalog: Mapping[str, Any] | None,
        run_loot_bag: RunLootBag,
    ) -> None:
        self.render = render
        self.world_root = world_root
        self.catalog = catalog
        self.run_loot_bag = run_loot_bag
        self.world_items: list[LootWorldItem] = []

    def spawn_loot(
        self,
        pos: tuple[float, float, float] | Any,
        item: ItemInstance,
    ) -> LootWorldItem:
        """Spawn a loot drop in the world. Enforces 40 item ground cap by pruning oldest."""
        while len(self.world_items) >= MAX_WORLD_LOOT_CAPACITY:
            oldest = self.world_items.pop(0)
            oldest.destroy()

        parent = self.world_root if self.world_root else self.render
        world_item = LootWorldItem(parent, pos, item, catalog=self.catalog)
        self.world_items.append(world_item)
        return world_item

    def update(self, dt: float) -> None:
        """Update animation for all active world loot items."""
        for item in self.world_items:
            item.update(dt)

    def get_nearest_loot(
        self,
        px: float,
        py: float,
        pz: float,
        chunks: Any = None,
    ) -> tuple[LootWorldItem | None, float]:
        """Find the nearest visible ground loot item within interaction distance and height."""
        best_item: LootWorldItem | None = None
        best_dist = float("inf")

        colliders = None
        if chunks is not None and get_nearby_colliders is not None:
            colliders = get_nearby_colliders(chunks, px, py, search_dist=3.0, curr_z=pz)

        for w_item in self.world_items:
            if w_item.is_collected:
                continue

            dx = px - w_item.base_x
            dy = py - w_item.base_y
            dz = abs(pz - w_item.base_z)

            # Check height bounds
            if dz > INTERACTION_MAX_DZ:
                continue

            dist = math.hypot(dx, dy)
            if dist > INTERACTION_MAX_DIST:
                continue

            # Line-of-sight check to prevent picking up through walls
            if colliders is not None and check_line_of_sight is not None:
                if not check_line_of_sight(px, py, w_item.base_x, w_item.base_y, colliders):
                    continue

            if dist < best_dist:
                best_dist = dist
                best_item = w_item

        return best_item, best_dist

    def try_pickup(
        self,
        w_item: LootWorldItem,
        session: RPGSession | None = None,
    ) -> tuple[bool, str]:
        """Attempt to pick up a world loot item and place it into the run bag."""
        if w_item.is_collected or w_item not in self.world_items:
            return False, "이미 획득한 전리품입니다."

        success, msg = self.run_loot_bag.add_item(w_item.item, session=session)
        if success:
            w_item.destroy()
            if w_item in self.world_items:
                self.world_items.remove(w_item)
            return True, msg
        return False, msg

    def clear_world_drops(self) -> None:
        """Clear all physical ground drops (used on stage transition or run reset)."""
        for w_item in self.world_items:
            w_item.destroy()
        self.world_items.clear()

