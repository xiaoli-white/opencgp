"""OpenCGP · 后端应用包。

遵循 Ports & Adapters 架构：

- ``ports/``      定义抽象接口（Python Protocol），业务代码只依赖接口。
- ``adapters/``   提供具体实现（builtin 默认单机实现 + external 生产实现）。
- ``container.py`` 极简依赖注入装配，按配置选择 adapter。

约定：所有基础设施与业务能力皆可插拔，切换 adapter 只改配置、不改业务代码。
"""

__version__ = "0.1.0"
