"""
통합 PoC 공용 헬퍼 함수.
"""
from __future__ import annotations

from typing import Optional


def parse_raw_champ_name(raw: str) -> str:
    """
    Live Client API의 rawChampionName → 영문 챔피언명.
    예) 'game_character_displayname_Lucian' → 'Lucian'
    패턴이 맞지 않으면 마지막 '_' 이후를 반환하고, 그래도 안 되면 raw 그대로.
    """
    prefix = "game_character_displayname_"
    if raw.startswith(prefix):
        return raw[len(prefix):]
    parts = raw.rsplit("_", 1)
    return parts[-1] if len(parts) == 2 else raw


def bbox_center(obj) -> Optional[list]:
    """
    box 또는 MyPosition 객체 → [cx, cy] 정수 리스트.
    .bbox 속성이 없으면 None.
    """
    if obj is None:
        return None
    b = getattr(obj, "bbox", None)
    if b is None:
        return None
    return [round((b[0] + b[2]) / 2), round((b[1] + b[3]) / 2)]
