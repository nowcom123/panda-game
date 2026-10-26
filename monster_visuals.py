"""Render-only optimizations that preserve animation and hit-test NodePaths."""
from panda3d.core import NodePath, PandaNode, GeomNode


def group_shared_tint(nodes):
    """Batch same-tint decorations by joint; never move them across joints."""
    groups = {}
    for node in nodes:
        parent = node.getParent()
        if parent not in groups:
            groups[parent] = parent.attachNewNode('shared_tint_parts')
        node.reparentTo(groups[parent])
    for group in groups.values():
        group.flattenStrong()
    return list(groups.values())


def set_shared_tint(monster, color):
    if getattr(monster, '_last_vein_tint', None) == color:
        return
    for group in monster.hellfire_vein_nodes:
        group.setColorScale(*color)
    monster._last_vein_tint = color


def animation_dt(monster, dt, is_attacking=False):
    """Throttle only pose work; callers must update gameplay timers first.

    Retain skipped time so motion phase does not slow down. Critical poses and
    transitions back to near distance consume pending time immediately.
    """
    elapsed = getattr(monster, '_animation_pending', 0.0) + dt
    interval = getattr(monster, '_animation_interval', 0.0)
    immediate = is_attacking or any(getattr(monster, flag, False) for flag in (
        'is_dodging', 'is_casting', 'is_slamming', 'is_striking', 'is_lashing'))
    if getattr(monster, 'stun_timer', 0.0) > 0:
        immediate = True
    # Draw the first pose immediately, even for a newly spawned far enemy.
    if (not getattr(monster, '_animation_started', False) or immediate
            or interval <= 0 or elapsed + 1e-9 >= interval):
        monster._animation_started = True
        monster._animation_pending = 0.0
        return elapsed
    monster._animation_pending = elapsed
    return None


def referenced_nodes(monster):
    """Model handles may be stored in nested limb dictionaries and lists."""
    seen = set()
    def visit(value):
        if isinstance(value, NodePath):
            if not value.isEmpty():
                yield value
        elif isinstance(value, (dict, list, tuple)) and id(value) not in seen:
            seen.add(id(value))
            items = value.values() if isinstance(value, dict) else value
            for item in items:
                yield from visit(item)
    yield from visit(vars(monster))


def optimize_monster_geometry(monster):
    """Merge unreferenced static siblings, never across a live model handle.

    Stored joints, hit meshes, lights, and their ancestors retain identity and
    transforms. Only plain geometry subtrees without such handles are flattened.
    Call once after construction, before attaching elemental effects.
    """
    root = monster.node
    protected = set()
    for path in referenced_nodes(monster):
        if path != root and not root.isAncestorOf(path):
            continue
        while path != root:
            protected.add(path)
            path = path.getParent()
    protected.add(root)

    def static_geometry(path):
        if path in protected or type(path.node()) not in (PandaNode, GeomNode):
            return False
        return all(static_geometry(child) for child in path.getChildren())

    def merge(parent):
        children = list(parent.getChildren())
        candidates = []
        for child in children:
            if static_geometry(child):
                candidates.append(child)
            else:
                merge(child)
        if len(candidates) > 1:
            batch = parent.attachNewNode('static_parts')
            for child in candidates:
                child.reparentTo(batch)
            batch.flattenStrong()
    merge(root)
