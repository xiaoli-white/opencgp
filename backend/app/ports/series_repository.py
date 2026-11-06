"""课程文档持久化端口（SeriesRepository）。

定义课程 / 讲 / 讲版本的仓库接口。业务代码（service、API）只依赖本协议，
具体的 SQL 方言与驱动由 adapter 实现，容器按配置装配。

约定：
- 版本号从 1 开始单调递增，同一 ``unit_id`` 内唯一。
- 每次内容变更（生成、回滚）都必须新增一条 ``UnitVersion``，不覆盖历史。
- 回滚不删除历史，而是以目标版本内容追加一个新版本（类 git revert）。
- 每个版本记录生成模式 ``mode``（``strict`` 严格引用 / ``loose`` 大模型自由写作 /
  空串表示人工草稿），``units.last_mode`` 跟随最近一次生成模式。
- 找不到实体时返回 ``None``，由上层决定错误语义。
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.series import Series, Unit, UnitVersion


@runtime_checkable
class SeriesRepository(Protocol):
    def create_series(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "",
        difficulty: str = "intermediate",
        language: str = "zh",
        tenant_id: str = "",
        user_id: str = "",
    ) -> Series:
        ...

    def get_series(self, series_id: str, tenant_id: str | None = None) -> Series | None:
        ...

    def list_series(self, tenant_id: str | None = None) -> list[Series]:
        ...

    def update_series(
        self,
        series_id: str,
        title: str | None = None,
        subtitle: str | None = None,
        audience: str | None = None,
        difficulty: str | None = None,
        language: str | None = None,
        profile_id: str | None = None,
    ) -> Series | None:
        ...

    def delete_series(
        self, series_id: str, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        ...

    def create_unit(
        self,
        series_id: str,
        title: str,
        order_index: int | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        content: str = "",
        status: str = "draft",
    ) -> Unit:
        ...

    def get_unit(self, unit_id: str) -> Unit | None:
        ...

    def list_units(self, series_id: str) -> list[Unit]:
        ...

    def update_unit(
        self,
        unit_id: str,
        title: str | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        status: str | None = None,
        order_index: int | None = None,
        content: str | None = None,
    ) -> Unit | None:
        ...

    def delete_unit(self, unit_id: str) -> dict[str, int] | None:
        ...

    def reorder_units(
        self, series_id: str, unit_ids: Sequence[str]
    ) -> list[Unit]:
        ...

    def append_version(
        self,
        unit_id: str,
        content: str,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        status: str | None = None,
        mode: str = "",
    ) -> tuple[Unit, UnitVersion] | None:
        ...

    def list_versions(self, unit_id: str) -> list[UnitVersion]:
        ...

    def get_version(self, unit_id: str, version: int) -> UnitVersion | None:
        ...

    def revert_to_version(
        self, unit_id: str, version: int, note: str = ""
    ) -> tuple[Unit, UnitVersion] | None:
        ...
