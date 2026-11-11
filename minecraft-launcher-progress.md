# CBL Cube Launcher 开发进度

## 项目路径
`C:\Users\ethan\Desktop\minecraft启动器`

## 当前版本: v0.9.3（多产品 + 中文路径修复）

## 技术栈
- Python + PyQt6
- minecraft-launcher-lib
- requests

## v0.7 修复（本轮）

针对代码审计出的 34 条问题做了集中修复，22 项自动验收全部通过（`22/22`，见 `.review/shots/final/` 的渲染截图）。

- **阻塞 3 条**：NeoForge 改用 8.0 的 `mod_loader` 接口（1.20.1 明确提示改用 Forge）；镜像补丁从 `requests.get` 移到 `requests.sessions.Session.request`，二进制下载才真正走镜像；QThread 引用拆分 + 重入保护，连点两次不再 abort。
- **高危 8 条**：整合包 zip slip 加 realpath 前缀校验；进度对话框的"取消"改为在库回调里抛异常真中断（实测 0.26s 停下）；游戏日志句柄关闭 + 日志清理不再一遇占用就永久放弃；Java 兼容性判定统一（不给 1.7.10 塞 JDK 26）；微软登录补 state 校验；令牌改用 Windows DPAPI 加密落盘并在启动时迁移旧明文；只读目录不再启动即崩；启动测速移到后台（不再卡 6 秒）。
- **中危 13 条**：补 `import minecraft_launcher_lib`；配置键补齐默认值；`close_on_launch` / `game_directories` 接线（后者是隔离 mods、避免 1.7.10 加载 1.20.1 mod 的正解）；config 原子写 + 损坏备份；JVM 参数引号感知切分；Java 下载进度不再覆盖登录提示；安装流程不再误报成功；删除失败可见；老 Forge 目录精确匹配；authlib-injector 校验 + 官方源优先；发布页 ico/下载/构建脚本；PyInstaller spec 改 onedir。
- **低危 10 条**：加载器命名、体积递归统计、首页标题、下载源显示、归档未使用的 `mods_page.py`、删除不可用死代码、皮肤失败可见、动画最小化暂停、版本列表失败可区分、mods 目录路径校验。

新增文件：`core/secret.py`（DPAPI 封装）、`tools/build_release.py`（出包 + 投放）。

## v0.8 主题扩展

背景主题 6 → 14 套，新增：蘑菇岛 `mushroom`、雪原 `snowy`、沙漠 `desert`、深暗之域 `deep_dark`、
恶地 `badlands`、繁茂洞穴 `lush_caves`、紫水晶洞 `amethyst`、红树林 `mangrove`。

- 每套仍是「上天空/草皮 + 下地面 + 可选锯齿带 + orb/dust/flies 三层粒子」的数据结构，没有新增绘制逻辑；
- 设置页主题下拉每项带 16×16 像素色块，按经典/新增分组，切换即预览、保存才落盘；
- 发布页 `index.html` / `main.css` / `main.js` 同步 14 套，key 与 `ui/background.py` 交叉校验一致；
- 顺手修掉 `grad_top` 主题在 `top_ratio=0` 时渐变被底部纹理盖住的问题（深海、深暗之域）。

## v0.9 重铸

架构从"Java 版专用"改为"产品 + 实例 + 下载器 + 诊断"四层：

- `core/providers/`：`base.py`（协议/能力标记）、`java/`（6 个模块迁入 + mod 依赖解析）、`bedrock/`（AppX 唤醒 + 内容包导入）、`server/`（BDS 导入/启动/控制台）
- `core/instances.py`：实例注册表，老 `selected_version`/`game_directories` 一次性迁移
- `core/download.py`：Range 续传 + 分块并发 + SHA1 校验，接管库内 11 个模块
- `core/diagnose.py`：18 条崩溃规则
- `core/paths.py` / `core/i18n.py`：跨平台系统层、中英骨架
- `ui/pages/library_page.py`：按能力渲染的产品树 + 实例详情 + 安装面板；`home_page` 改为按实例启动
- 旧实现归档在 `.review/removed/legacy/`

验收：核心 24/24（provider 注册、实例生命周期、迁移、下载器续传与校验、诊断真实日志、236 jar 依赖扫描）、
界面 7 张离屏渲染（登录/首页/库/Java 详情/服务端详情/设置/英文）。

## v0.9.1 修复（真机安装 1.7.10 暴露）

- **镜像缺文件回退**：BMCLAPI 对 1.7 时代的 `client-1.7.xml`（log4j 配置）、`lwjgl-platform-2.9.1.jar`、
  `jinput-platform-2.0.5.jar`、`twitch-platform-*.jar` 返回 404，对 `netty-1.8.8.jar`/`splash2x.gif` 返回 403。
  现在命中 403/404/410 自动用原始地址重试，并记入进程级黑名单；`mirror.fallback_events()` 供 UI 提示。
- **lzma 语义**：接管下载器时漏了 `lzma_compressed`，导致 `install_jvm_runtime` 必然 SHA1 失败。
  已实现"下载 .lzma → 解压 → 校验解压后哈希 → 落盘"。
- **错误文案**：`friendly_error()` 把裸异常翻成可操作建议。
- 端到端：1.7.10 全新安装 106.8 s 成功（client jar 5.2 MB / libraries 33 / assets 674 / jre-legacy）。

## 已完成功能
### 核心功能 (v0.1)
- 离线登录 + 微软正版 OAuth 登录
- MC 版本列表获取/下载/安装
- Forge / Fabric 加载器安装
- Java 自动检测 + 手动配置
- 游戏启动 (JVM 参数/内存分配)
- 皮肤头像获取缓存
- JSON 配置持久化

### UI 第一次重构 (v0.2) — 已废弃
- 安装了 pyqt6-ui-designer Cursor Skill
- Design Token 系统 + 4px 网格
- 卡片式布局
- 问题: 太像企业仪表盘，不像游戏启动器

### UI 第二次重构 (v0.3) — 已废弃
- 设计参考: XMCL + BakaXL + HMCL
- 布局: 顶栏(品牌+头像) + 中区(内容) + 底栏HUD(导航)
- 全 rgba 半透明体系 + QPainter 渐变背景
- 问题: 辅助模块未创建(background.py/tokens.py/icons.py/common.py)，无法运行

### UI 第三次重构 (v0.4) — Glass Sidebar (已替换)
- 侧边栏布局 + 半透明玻璃面板 + QPainter 渐变背景
- 所有辅助模块创建 (tokens/background/icons/common)
- 问题: 用户认为不够 Minecraft 主题化，偏通用深色风格

### UI 第四次重构 (v0.5) — Minecraft 主题 ✅ 当前版本
设计参考: Minecraft 游戏原版 UI + Pixel Art 风格系统

核心设计改变:
- **配色**: Minecraft §格式码色系 — `#55FF55`(§a绿) / `#FFAA00`(§6金) / `#55FFFF`(§b钻石蓝) / `#FF5555`(§c红)
- **按钮**: MC 经典浮雕/凸起按钮 — 亮色上/左边框 + 暗色下/右边框，按压时翻转
- **面板**: MC 浮雕面板 — 同样的 3D 凸起边框，深色背景
- **输入框**: MC 物品栏凹槽风格 — 暗色上/左边框 + 亮色下/右边框（凹陷感）
- **圆角**: 全部 `border-radius: 0` — 方块世界没有圆角
- **品牌**: 像素艺术草方块图标（QPainter 8×8 像素格绘制）
- **导航图标**: 像素艺术 7×7 格 — 房子/箱子/命令方块/齿轮
- **头像**: 方形（不是圆形，符合 MC 风格）
- **背景**: 草方块正面纹理 — 草地(顶)+锯齿过渡+泥土(底) 平铺 + 暗色遮罩
- **粒子动画**: 40 个漂浮像素粒子 (绿/黄绿/白尘) 持续上升 + 渐隐重生
- **启动按钮光效**: 呼吸式绿色附魔脉冲 (sin 波 blur 22±12, alpha 60±50)
- **Tooltip**: MC 经典紫色风格 — `#100010` 底 + `#5000AA` 边框
- **进度条**: 经验条风格 — `#55FF55` → `#80FF20` 绿色渐变
- **Hover 文字**: `#FFFF55` 黄色（MC 按钮 hover 时的黄色文字）
- **Section 标题**: `#55FF55` MC 绿色

## 项目结构
```
minecraft启动器/
├── main.py                  # 入口 (Fusion style + MAIN_STYLE)
├── readme.md
├── minecraft-launcher-progress.md
├── requirements.txt         # PyQt6, minecraft-launcher-lib, requests
├── core/
│   ├── config.py            # JSON 配置管理
│   ├── auth.py              # 离线 + 微软 OAuth
│   ├── java_utils.py        # Java 检测
│   ├── version_manager.py   # 版本管理
│   ├── launcher.py          # 游戏启动
│   ├── mod_manager.py       # Forge/Fabric
│   └── skin_manager.py      # 皮肤
├── ui/
│   ├── main_window.py       # MainWindow (侧边栏 + 内容区)
│   ├── styles.py            # MAIN_STYLE (Glass Sidebar 主题)
│   ├── background.py        # BackgroundWidget (QPainter 渐变)
│   ├── tokens.py            # 设计令牌 (间距/尺寸/颜色)
│   ├── pages/
│   │   ├── home_page.py     # LoginWidget + HomePage (英雄启动区)
│   │   ├── versions_page.py # 版本管理 (左右分栏)
│   │   ├── settings_page.py # 设置 (滚动表单)
│   │   └── mods_page.py     # Forge/Fabric 安装 (双栏)
│   └── widgets/
│       ├── icons.py         # QPainter 矢量图标 (CubeMark/AvatarBadge/nav_icon)
│       ├── common.py        # 可复用组件 (make_sheet/page_title/labeled_field/vline)
│       └── progress_dialog.py
└── resources/
```

## 已安装的 Cursor Skill
- `~/.cursor/skills/pyqt6-ui-designer/` — PyQt6 UI 设计参考
- `~/.cursor/skills/ui-ux-pro-max/` — UI/UX 设计智能系统

## 用户反馈历史
1. v0.1: "面板太AI了" — 要求搜索主题和UI设计skill
2. v0.2: "布局和设计完全不认同，太AI太丑" — 企业仪表盘风格不适合游戏启动器
3. v0.3: 半透明渐变风格方向正确，但辅助文件缺失无法运行
4. v0.4: Glass Sidebar 布局 — 侧边栏+渐变背景+全面板玻璃效果，参考 XMCL

## 下一步可能的改进
- 支持自定义背景图片 (用户选择 MC 截图作背景)
- 背景图上方加暗色渐变遮罩
- 添加启动按钮发光/脉冲动画效果
- 侧边栏可折叠 (icon-only 模式)
- 主题色可自定义 (不只绿色)
- 添加新闻/更新信息展示区
- 更精致的版本列表项 (带图标/类型标签)
- 导航按钮悬浮微动画
- 3D 皮肤预览 (OpenGL)

## 关键设计决策记录
- 不用 pyqtdarktheme 库 (Python 版本限制 <3.12, 项目用 3.14)
- 不用 Material Symbols 字体 (需要额外安装字体文件)
- 使用 QPainter 绘制背景渐变 + 矢量图标 (零外部资源依赖)
- 全部颜色用 rgba() 实现半透明，背景渐变穿透所有层
- v0.4 从顶栏+底部HUD改为侧边栏布局 (更符合游戏启动器惯例: XMCL/HMCL/Prism)
- 导航活跃态用 property selector `[active="true"]` + unpolish/polish 强制刷新
- CubeMark 品牌图标用 QPainterPath 绘制等轴方块 (Minecraft 风格)
- AvatarBadge 支持 pixmap 和首字母回退两种模式

---
最后更新: 2026-11-10（v0.7 全量修复）

## v0.9.3 修复（中文路径下的 Java 8）

- `no zip in java.library.path` / `lwjgl64.dll: Can't find dependent libraries` / `找不到主类` 三个现象同源：
  Java 8 不能从含中文的路径加载 bootstrap native、`java.library.path` 里的 DLL、以及 classpath 里的 jar。
- 运行时迁到 `%LOCALAPPDATA%\CBL\runtime`（自动迁移 + 重定向库的 `install_jvm_runtime`）；
  `.minecraft` 通过 `mklink /J %LOCALAPPDATA%\CBL\mc` 暴露成 ASCII 路径，命令里 classpath / library.path / gameDir 全部改写；
  native 库另有复制兜底；联接失败且 Java 8 时直接报可读错误。
- 实测：ASCII 路径的 jre-legacy `-version` rc=0；用改写后的完整 classpath 能进入 `net.minecraft.client.main.Main`。
