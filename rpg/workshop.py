"""Deterministic upgrades using secured materials; no engine or save side effects."""
from dataclasses import dataclass
import copy

from rpg.items import ItemAffix, ValidationError


@dataclass(frozen=True)
class UpgradeRecipe:
    name: str
    material_id: str
    cost: int
    affix_id: str
    increment: float
    cap: float


RECIPES = {
    'reinforce': UpgradeRecipe('총열 보강', 'scrap_metal', 8, 'damage_mult', .02, 1.30),
    'weakpoint': UpgradeRecipe('약점 각인', 'bone_fragment', 6, 'weakpoint_mult', .05, 1.50),
}


@dataclass(frozen=True)
class UpgradeQuote:
    profile_id: str
    item_uid: str
    recipe_id: str
    material_id: str
    cost: int
    available: int
    before: float
    after: float


def material_count(profile, definition_id):
    """Only unlocked materials in the permanent profile are spendable."""
    return sum(item.quantity for item in profile.items.values()
               if item.definition_id == definition_id and not item.locked)


def quote_upgrade(profile, catalog, item_uid, recipe_id):
    profile.validate(catalog)
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        raise ValidationError('알 수 없는 강화 방식입니다.')
    item = profile.items.get(item_uid)
    if item is None or catalog[item.definition_id].kind != 'weapon':
        raise ValidationError('영구 보관함의 무기를 선택하세요.')
    if item.locked:
        raise ValidationError('잠금을 해제한 뒤 강화하세요.')
    before = next((a.value for a in item.affixes if a.id == recipe.affix_id), 1.0)
    if before >= recipe.cap - 1e-9:
        raise ValidationError('이미 강화 상한에 도달했습니다.')
    available = material_count(profile, recipe.material_id)
    if available < recipe.cost:
        raise ValidationError(f'{catalog[recipe.material_id].name} 부족: {available}/{recipe.cost} (잠금 제외)')
    return UpgradeQuote(profile.profile_id, item_uid, recipe_id, recipe.material_id,
                        recipe.cost, available, before, round(min(recipe.cap, before + recipe.increment), 6))


def upgrade_candidate(profile, catalog, quote):
    """Revalidate the preview, then return an independent, fully validated profile."""
    if not isinstance(quote, UpgradeQuote):
        raise ValidationError('강화 미리보기를 다시 열어 주세요.')
    current = quote_upgrade(profile, catalog, quote.item_uid, quote.recipe_id)
    if current != quote:
        raise ValidationError('장비 또는 재료가 변경되었습니다. 미리보기를 다시 확인하세요.')
    candidate = copy.deepcopy(profile)
    remaining = quote.cost
    for uid, item in list(candidate.items.items()):
        if item.definition_id != quote.material_id or item.locked:
            continue
        used = min(remaining, item.quantity)
        item.quantity -= used
        remaining -= used
        if item.quantity == 0:
            del candidate.items[uid]
        if remaining == 0:
            break
    recipe = RECIPES[quote.recipe_id]
    target = candidate.items[quote.item_uid]
    target.affixes = [a for a in target.affixes if a.id != recipe.affix_id]
    target.affixes.append(ItemAffix(id=recipe.affix_id, value=quote.after))
    candidate.validate(catalog)
    return candidate
