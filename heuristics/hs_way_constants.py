"""Harmony Search 路由常量 — way 值的单一来源。

所有 HS 个体和种群模块应从此处导入 way 常量，
避免硬编码字符串导致的 silent fallthrough。
"""

WAY_RANDOM = "way1"
WAY_MEMORY = "way2"
WAY_PITCH = "way3"
WAY_CROSS = "way4"

VALID_CLASSIC_WAYS = frozenset({WAY_RANDOM, WAY_MEMORY, WAY_PITCH})
VALID_EDGE_UAV_WAYS = frozenset({WAY_RANDOM, WAY_MEMORY, WAY_PITCH, WAY_CROSS})
