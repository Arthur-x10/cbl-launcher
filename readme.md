# 🎮 PyMC Launcher — Python Minecraft 启动器

## 📋 项目概述

一个使用 Python + PyQt6 开发的 Minecraft 游戏启动器，支持微软正版登录和离线模式，具备版本管理、Mod 加载器安装、Java 自动检测等功能。

## 🏗️ 技术栈

| 组件 | 技术选择 | 说明 |
|------|----------|------|
| UI 框架 | PyQt6 | 功能强大的跨平台 GUI 框架 |
| MC 核心库 | minecraft-launcher-lib | 处理版本下载、游戏启动、Forge/Fabric 安装等 |
| 微软认证 | minecraft-launcher-lib 内置 | Microsoft OAuth Device Code Flow |
| HTTP | requests | 网络请求（皮肤获取等） |
| 配置存储 | JSON | 轻量级本地配置 |

## 📁 项目结构

```
minecraft启动器/
├── main.py                     # 程序入口
├── readme.md                   # 设计文档
├── requirements.txt            # Python 依赖
├── core/                       # 核心业务逻辑
│   ├── __init__.py
│   ├── config.py               # 配置管理（读写 config.json）
│   ├── auth.py                 # 认证系统（微软 + 离线）
│   ├── java_utils.py           # Java 检测与自动下载
│   ├── version_manager.py      # MC 版本管理
│   ├── launcher.py             # 游戏启动逻辑
│   ├── mod_manager.py          # Forge / Fabric 安装
│   └── skin_manager.py         # 皮肤获取与缓存
├── ui/                         # UI 界面
│   ├── __init__.py
│   ├── main_window.py          # 主窗口（侧边栏导航 + 页面切换）
│   ├── styles.py               # QSS 全局样式
│   ├── pages/                  # 页面模块
│   │   ├── __init__.py
│   │   ├── home_page.py        # 首页 / 启动页
│   │   ├── versions_page.py    # 版本管理页
│   │   ├── settings_page.py    # 设置页
│   │   └── mods_page.py        # Mod 加载器页
│   └── widgets/                # 可复用组件
│       ├── __init__.py
│       └── progress_dialog.py  # 下载进度对话框
└── resources/                  # 资源文件
    └── (图标等)
```

## ✨ 核心功能

### 1. 认证系统
- **离线模式**：输入用户名即可游玩（无需联网）
- **微软正版登录**：通过 Device Code Flow 完成 OAuth 认证，获取 MC 令牌

### 2. 版本管理
- 查看所有可用版本（Release / Snapshot / Old）
- 一键下载安装指定版本
- 显示已安装版本列表
- 下载进度实时显示

### 3. 游戏启动
- 选择版本 + 点击启动
- 自动拼接 JVM 参数
- 支持自定义游戏目录（多实例）

### 4. JVM 设置
- 最小/最大内存分配
- Java 路径手动选择或自动检测
- 自定义 JVM 参数

### 5. Java 自动检测
- 扫描系统已安装的 Java
- 自动检测 PATH、注册表、常见安装目录
- 支持通过 Mojang 官方 Runtime 下载 Java

### 6. Mod 加载器
- 安装 Forge（选择版本）
- 安装 Fabric（选择版本）
- 查看已安装的加载器版本

### 7. 皮肤预览
- 微软登录后自动获取皮肤
- 在启动页显示玩家皮肤头像

## 🎨 UI 设计 (v0.4 — Glass Sidebar)

### 设计参考
- **XMCL**: 半透明侧边栏 + 背景渐变穿透，游戏启动器标杆
- **BakaXL**: 视觉冲击力，全屏背景 + 玻璃浮层
- **HMCL**: Material Design 导航逻辑，清晰信息层级
- **UI/UX Pro Max Skill**: Glassmorphism + Gaming 风格系统

### 设计语言
采用 **Glassmorphism + Gaming Dark** 风格：

- **色彩系统**: Minecraft 草地绿 (#4CAF50) 主色，#6FCF73 亮绿文字，#42A5F5 蓝色辅助，#EF5350 危险色
- **表面层级**: 全半透明 rgba 体系，背景渐变穿透所有面板
  - 侧边栏: `rgba(10,12,22,0.82)` — 深色但透光
  - 内容面板: `rgba(14,18,32,0.52)` — 轻量玻璃
  - 登录面板: `rgba(12,14,28,0.82)` — 稍重，聚焦
- **边框策略**: `rgba(255,255,255,0.06~0.09)` 超细边框，不依赖阴影
- **间距**: 4px 网格 (XS=4, SM=8, MD=12, LG=16, XL=24, XXL=32)
- **圆角**: 面板 12px / 按钮 6-8px / 启动按钮 26px pill 形
- **字体**: Microsoft YaHei UI / Segoe UI 字体栈
- **图标**: QPainter 矢量绘制，零外部依赖
- **背景**: QPainter 深蓝渐变 + 绿/蓝径向微光晕

### 布局结构 (v0.4 — 侧边栏)

```
┌─────────────┬────────────────────────────────────────┐
│  [◆] PyMC   │                                        │
│   LAUNCHER  │                                        │
│             │                                        │
│   首页      │         [Content Area]                 │
│   版本管理   │                                        │
│   加载器     │    首页: 居中英雄区 + 大启动按钮          │
│   设置      │    版本: 左右分栏 (已安装/下载)           │
│             │    加载器: Forge/Fabric 双栏            │
│             │    设置: 滚动表单面板                    │
│   ─────── ─│                                        │
│  [头像] 用户 │                                        │
│  离线  [退出]│                                        │
└─────────────┴────────────────────────────────────────┘
```

### 组件风格
- **侧边栏**: 200px 固定宽，半透明深色 + 右侧 1px 分隔线
- **导航按钮**: 3px 绿色左侧指示条 (活跃态) + 8px 圆角 + 图标文字左对齐
- **玻璃面板**: `rgba(14,18,32,0.52)` + 1px 边框 + 12px 圆角
- **启动按钮**: 绿色线性渐变 + 26px pill 圆角 + DropShadow 发光 + 1.5px 字间距
- **输入框**: `rgba(0,0,0,0.32)` 暗底 + 聚焦时绿色边框
- **进度条**: 6px 细条，#2E7D32→#66BB6A 渐变填充

### Cursor Skill 安装
已安装 `pyqt6-ui-designer` Skill 到 `~/.cursor/skills/`，包含：
- Design Tokens 参考 (色板/字体/间距/圆角/层级)
- QSS 模式参考 (完整组件状态模板)
- 组件库参考 (侧边栏/表格/卡片/对话框/按钮等)

## 🚀 使用方式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

## 📝 开发日志

- v0.7 — 全量缺陷修复（阻塞 3 / 高 8 / 中 13 / 低 10），详见下方「v0.7 修复清单」
- v0.4 — UI 第三次重构：Glass Sidebar 布局
  - 从顶栏+底部HUD改为左侧边栏布局 (对标 XMCL/HMCL)
  - 全部辅助模块创建: tokens.py / background.py / icons.py / common.py
  - QPainter 矢量图标 (CubeMark/AvatarBadge/nav_icon)，零外部依赖
  - Glassmorphism 玻璃面板 + 深蓝渐变背景 + 绿/蓝微光晕
  - 导航活跃态: 3px 绿色指示条 + property selector
  - 使用 UI/UX Pro Max Skill 生成设计系统
  - 修复 mods_page.py 缺失的 Qt import
- v0.3 — 半透明渐变风格 (方向正确但缺文件，无法运行)
- v0.2 — Design Token + 卡片布局 (被否决: 太像企业仪表盘)
- v0.1 — 初始版本，全功能实现

---

## 🔮 v0.6 重构计划

### 核心改动：三页变两页 + 自动 Java + 版本全生命周期

**页面结构重构:**
```
旧: 首页 | 版本 | 加载器 | 设置  (4页，版本和加载器割裂)
新: 首页 | 版本管理 | 设置        (3页，版本全生命周期统一)
```

**「版本管理」统一页 — 核心重构:**
```
┌─────────────────────────────────────────────────┐
│  版本管理                          [+ 安装新版本] │
├──────────────┬──────────────────────────────────┤
│              │                                  │
│ ▸ 1.21.1     │  版本: 1.7.10-Forge             │
│   1.20.4     │  类型: Forge                     │
│ ▸ 1.7.10     │  Java: jre-legacy (Java 8)      │
│   1.7.10-F.. │  大小: 245 MB                    │
│              │                                  │
│              │  [安装 Forge] [安装 Fabric]       │
│              │                                  │
│              │  Mods (3个):                      │
│              │   OptiFine_1.7.10.jar            │
│              │   NEI_1.7.10.jar                 │
│              │                                  │
│              │  [打开 mods 文件夹] [删除版本]    │
└──────────────┴──────────────────────────────────┘
```

安装新版本流程（一步到位）:
```
选择 MC 版本 → 可选: 加 Forge 或 Fabric → 一键下载安装
```

**自动 Java 环境:**
- 首次启动自动下载 Mojang 官方运行时:
  - `jre-legacy` (Java 8) → MC 1.0~1.16
  - `java-runtime-gamma` (Java 17) → MC 1.17~1.20.4
  - `java-runtime-delta` (Java 21) → MC 1.20.5+
- 用户零配置，启动器自动匹配版本
- 设置页 Java 部分改为"自动管理"开关

**版本删除:**
- 版本详情页「删除版本」按钮
- 确认对话框提示会删除的内容
- 删除 versions/{id}/ 目录

**Mod 管理 (基础版):**
- 显示版本对应 mods 文件夹内的 .jar 列表
- 「打开 mods 文件夹」在文件管理器中打开
- 拖拽 .jar 到列表可安装 mod (后续)

### 实现步骤:
1. ✅ 自动 Java 环境下载（首次启动）
2. 合并版本+加载器页为统一「版本管理」页
3. 添加安装流程（版本+可选加载器一步完成）
4. 添加删除版本功能
5. 添加 Mod 文件列表 + 打开文件夹
6. 从导航栏移除「加载器」

---

## 🤔 已知问题与改进方向

### 已知问题
1. **微软登录 Client ID**：当前使用的是公开 Client ID (`00000000402b5328`)，正式发布前应注册自己的 Azure AD 应用
2. **皮肤头像获取**：依赖 Crafatar 第三方 API，该服务可能不稳定或有速率限制
3. **Forge 安装**：部分旧版本 Forge 的安装流程可能与新版不兼容
4. **Java 扫描**：Windows 注册表扫描未实现，可能遗漏部分非标准安装路径的 Java
5. **错误处理**：网络请求超时/失败的用户提示可以更友好

### 改进方向
1. **🌐 多语言支持**：当前仅中文，可加入 i18n 框架
2. **📦 版本搜索**：版本列表添加搜索/过滤功能
3. **📊 下载限速控制**：添加下载带宽限制选项
4. **🔐 令牌刷新**：微软登录的 token 过期自动刷新
5. **📁 独立游戏目录**：按版本隔离 saves、mods、config 等
6. **🎨 主题切换**：深色/浅色主题切换
7. **📋 游戏日志查看器**：实时显示游戏控制台输出
8. **⬆️ 自动更新**：启动器自动检查更新
9. **💾 导入/导出配置**：支持配置文件的导入导出
10. **🖼️ 3D 皮肤预览**：使用 OpenGL 渲染 3D 皮肤模型
11. **🔌 整合包支持**：CurseForge / Modrinth 整合包一键导入
12. **⌨️ 快捷键**：添加键盘快捷键支持

### 反思

**v0.4 (Glass Sidebar) 重构总结：**
- 侧边栏布局是游戏启动器的标准范式（XMCL/HMCL/Prism Launcher 都用），比 v0.3 的「顶栏+底部HUD」更自然
- QPainter 矢量图标（icons.py）虽然绘制代码较长，但零外部依赖，适合轻量级项目
- `[active="true"]` 属性选择器 + `unpolish/polish` 是 PyQt6 动态切换 QSS 状态的标准做法
- 将设计令牌集中到 tokens.py 让所有页面引用一致的间距/尺寸/颜色
- UI/UX Pro Max Skill 的 `--design-system` 搜索有效收敛了色板和风格方向，避免「随便选颜色」
- 全 rgba 半透明体系让背景渐变穿透所有面板，整体感和游戏感比实色方案强很多

**历史教训：**
- v0.2 失败原因: Design Token + 卡片 = 企业仪表盘气质，不适合游戏
- v0.3 失败原因: 设计方向对了，但辅助模块缺失导致无法运行
- v0.4 关键: 先确保所有文件完整可运行，再追求细节打磨

**通用经验：**
- `minecraft-launcher-lib` 极大减少核心开发量
- PyQt6 QSS 不支持 transition/animation，动画只能用 QPropertyAnimation 或 QTimer
- 微软登录必须后台线程，否则 UI 冻结
- JSON 配置适合当前规模，功能增多后可考虑 SQLite

---

## 🛠 v0.7 修复清单

一次针对全量缺陷的集中修复。每条都做过可复现的验证，不是"看起来改了"。

### 阻塞级

1. **NeoForge 全链路不可用** — `core/mod_manager.py` 曾用 `list_mod_loader("neoforge", mc)`、`get_mod_loader("neoforge", ver)` 调用 8.0 的 0 参/1 参接口，必抛 `TypeError`，而查询线程无 try，信号永不发射 → 按钮永久停在"查询中"。
   现改用 `mod_loader.get_mod_loader("neoforge")` + `is_minecraft_version_supported` / `get_loader_versions` / `install(mc_ver, dir, loader_version=…)`；1.20.1 明确提示"需要 1.20.2+，请用 Forge"（8.0 的库确实不提供 1.20.1 的 NeoForge）。所有查询线程都加了异常兜底，失败会发空结果而不是卡死。
2. **镜像对二进制无效** — 之前只补 `requests.get`，而库的下载全部走 `requests.session()`（`install.py` 里 session 传递给 `_helper.download_file`）。现在补在 `requests.sessions.Session.request` 上，模块级 `requests.get/head` 与库内部 Session 全部覆盖，并附带可配置的失败重试（整合包安装时 5 次）。
3. **QThread 引用被覆盖导致进程 abort** — `settings` 的测速/扫描、`versions` 的远程列表各自共用一个 `self._st` / `self._rt`。现拆成独立属性 + `isRunning()` 重入保护，按钮在任务期间禁用。

### 高危

4. **整合包 zip slip** — `core/modpack.py` 统一走 `_safe_join()`：拒绝绝对路径/盘符，并用 `realpath` 校验前缀。实测 `mods/../../evil.txt`、`../outside.txt` 均被拒绝，正常文件照常落盘。
5. **"取消"是假的** — `ProgressDialog` 现在在库的 `setStatus/setProgress` 回调里抛 `TaskCancelled`，能在下一个文件边界真正中断；取消后对话框保持打开直到线程结束，杜绝"取消后又开一个任务双写同一目录"。实测：400 步任务在 0.31 秒内停下（回调执行 29 次）。
6. **日志句柄泄漏** — `launcher` 记录 `process._log_file` 并新增 `close_game_log()`，UI 在进程退出时关闭；`cleanup_old_logs` 不再"一个删不掉就永久放弃"。
7. **Java 版本兜底不兼容** — `find_best_java` 的兜底分支与 `java_manager.find_java_for_version` 都补上兼容性判断：`required <= 8` 只认 Java 8（8~17 可接受），不再把 JDK 26 交给 1.7.10。
8. **微软登录丢弃 state** — 登录窗口改为基地址 + code + state 三重校验，state 不符只置 `invalid_callback_seen` 并忽略，不会误接受注入的授权码。
9. **令牌明文落盘** — 新增 `core/secret.py`：Windows DPAPI（当前用户 + 当前机器绑定）加密 `access_token` / `refresh_token`，落盘形如 `dpapi:…`；读到老的明文令牌会在启动时静默迁移；换了机器/用户解不开时返回空串，不会被当成令牌使用。
10. **只读目录启动即崩** — `Config.save()` 改为临时文件 + `os.replace` 原子写，失败只记录 `last_error` 不抛异常；`main.py` 的 `chdir` 与窗口创建都有兜底提示。
11. **启动同步测速卡 6 秒** — 主程序先用上次测到的源秒开，测速改到 `_SourceSpeedThread` 后台进行，结果显示在顶部独立的环境标签上。

### 中危

12. `versions_page` 补上缺失的 `import minecraft_launcher_lib`（整合包名映射之前每次都静默失败）。
13. `auto_performance`、`download_source`、`theme`、`modpack_names` 等键纳入 `DEFAULT_CONFIG`，缺键不再靠临时默认值漂移。
14. `close_on_launch` 接线：启动成功后按设置关闭启动器。
15. `game_directories` 接线：版本详情页新增「设置独立目录 / 恢复默认」，启动时工作目录也随之切换 —— 这是 1.7.10 加载 1.20.1 mod 导致 `MixinTweaker ClassNotFound` 的根治办法。
16. `config.json` 损坏时备份为 `config.json.corrupt-<时间>` 再回落默认值，绝不静默覆盖（原实现会连凭证一起销毁）。
17. JVM 自定义参数改为引号感知切分，含空格的 Windows 路径不再被拆坏。
18. 首次启动的 Java 运行时下载不再覆盖"请先登录"提示，改由 `env_label` 承载进度。
19. 安装流程不再误报成功：选了加载器却没选版本会拦下；加载器安装失败/取消 → 整体失败并说明"原版已装好"。
20. 删除版本把失败暴露出来（游戏占用/权限不足时会明确提示，而不是假装删掉又出现）。
21. 老 Forge 目录修复改为版本号精确匹配，不再用子串交集（以前可能把 1.12.2 的目录认成 1.7.10 并删除）。
22. authlib-injector 下载先官方源、再镜像，落盘前校验 zip 结构与 `META-INF/MANIFEST.MF`，日志记录 SHA-256 前缀；`api_root` 做协议校验。
23. 发布页：多尺寸 `resources/cbl.ico`、`website/downloads/README.txt`、`tools/build_release.py`（一条命令出包并投放）。
24. PyInstaller spec 改为 onedir（首启不必再解压 WebEngine），保留 onefile 产物路径说明。

### 低危

25. `_loader_label` 覆盖现代 NeoForge（`neoforge-21.1.77`）、OptiFine 与大小写混写。
26. 版本体积改为递归统计（含子目录）。
27. 首页大标题显示 `Forge 47.4.23` 这类可读名，不再回落到内部 id。
28. `_show_source_info` 从空实现改为真实显示下载源与延迟。
29. 未使用的旧 `ui/pages/mods_page.py` 归档到 `.review/removed/`（可恢复，不是删除）。
30. `auth.open_microsoft_login` 这类不可用的死代码删除；设备码流程保留为备用登录路径并支持取消回调。
31. 本地皮肤部署失败不再完全吞掉，写入 stderr。
32. 背景粒子与启动按钮光效在最小化/切页时暂停，不再恒定 50fps 空转。
33. 版本列表获取失败与"确实没有版本"区分开，UI 提示换源/重试。
34. `open_mods_folder` 校验游戏目录为绝对路径，空配置不会再打开当前目录。

---

## 🎨 主题系统（v0.8：6 → 14 套）

背景主题从 6 套扩到 14 套，全部沿用同一套像素语法（上半天空/草皮、下半地面、可选锯齿带、三层粒子），
配色仍取自 MC 的 §格式码色系，因此和 QSS 的浮雕面板天然合拍。

| key | 名称 | 主色 | 特点 |
|---|---|---|---|
| `grass_block` | 草方块 | 草绿 / 泥土 | 锯齿草皮过渡 |
| `the_end` | 末地 | 深紫 / 末地石 | 星空渐变天空 |
| `nether` | 下界 | 暗红 / 岩浆 | 无天空，全地面 |
| `ocean` | 深海 | 深蓝 / 水色 | 渐变天空带（修了被纹理盖住的老 bug） |
| `twilight` | 暮色森林 | 深绿 / 暗土 | 锯齿 + 萤火虫 |
| `cherry` | 樱花林 | 樱粉 / 褐土 | 锯齿 + 花瓣粒子 |
| `mushroom` | 蘑菇岛 | 菌丝紫灰 | 孢子白 + 红蘑菇点 |
| `snowy` | 雪原 | 雪白 / 冰蓝 | overlay 120（最亮的一套，特意压暗保可读） |
| `desert` | 沙漠 | 沙金 / 砂岩 | 沙尘 + 金甲虫 |
| `deep_dark` | 深暗之域 | 幽匿青黑 | `#00FFD4` 幽匿脉冲，渐变天空 |
| `badlands` | 恶地 | 陶瓦橙 / 层岩 | `top_ratio` 0.22 做层状条带 |
| `lush_caves` | 繁茂洞穴 | 苔藓 / 洞穴石 | 荧光孢子青绿 |
| `amethyst` | 紫水晶洞 | 紫晶 / 深板岩 | 紫光粒子 |
| `mangrove` | 红树林 | 红树根 / 沼泽水 | 暖橙萤火 |

配套改动：

- `ui/background.py` 新增 `theme_swatch()` / `random_swatch()`：用主题自身的 top/bot/jag 画 16×16 像素色块；
- 设置页的「背景主题」下拉现在每项带色块、按「经典 / v0.8 新增」分组，并且**切换即预览**（只有保存才写配置）；
- 发布页同步：`website/index.html` 14 个切换按钮、`main.css` 14 组主题变量、`main.js` 14 组粒子配色，
  三处 key 与 `ui/background.py` 由脚本交叉校验一致；
- 顺手修掉 `paintEvent` 的老问题：`grad_top` 主题在 `top_ratio=0` 时渐变会被底部纹理整体盖住（深海一直如此）。

---

## 🏗 v0.9 重铸：从"Java 版启动器"到"多产品启动器"

### 一句话
把硬编码的「Java 版一次性启动」拆成 **Provider（产品） + Instance（实例） + Downloader + Diagnose** 四层，
于是「再加一个产品」= 新增一个 provider 包，而不是给每个页面开分支。

### 新目录

```
core/
  providers/
    base.py            # GameProvider 协议 + GameVersion/Instance/LaunchHandle + CAP_* 能力标记
    __init__.py        # 注册表 + ProviderContext，单个产品加载失败不影响其它
    java/              # 原 version_manager / launcher / mod_manager / modpack / java_manager
      version.py  launch.py  loaders.py  packs.py  runtime.py  deps.py（mod 依赖解析）
    bedrock/           # AppX 探测 + 唤醒 + .mcpack/.mcaddon/.mcworld 导入
    server/            # 基岩 BDS：导入 zip、启动、stdin 控制台、日志跟随
  instances.py         # 实例存储（注册表 + 独立游戏目录 + 一次性老配置迁移）
  download.py          # Range 续传 + 分块并发 + SHA1 校验，并接管库内 11 个模块的 download_file
  diagnose.py          # 18 条崩溃/日志规则，输出 fatal/error/warn + 可操作建议
  paths.py             # 跨平台：open_folder / open_uri / java 可执行文件 / AppX 目录
  i18n.py              # 中英双语的界面骨架文案
  config.py secret.py mirror.py auth.py yggdrasil.py java_utils.py performance.py
  log_manager.py skin_manager.py skin_local.py
ui/
  pages/library_page.py   # 新的「库」：产品树 + 实例详情 + 按能力渲染的安装面板
  pages/home_page.py      # 首页按实例启动
  pages/settings_page.py  # 增加界面语言
```

### 能力标记驱动的 UI
provider 声明 `capabilities()`，界面只按标记渲染，**没有一处 `if provider == "java"`**：

| 能力 | 含义 | 谁有 |
|---|---|---|
| `version_list` / `uninstall` | 可枚举、可卸载远端版本 | Java |
| `modloader` | Forge/Fabric/Quilt/NeoForge | Java |
| `jvm` / `java_runtime` | 内存、JVM 参数、Java 运行时 | Java |
| `pack_import` | 整合包 / mcpack 导入 | Java、基岩 |
| `console` | 控制台与 stdin 命令 | 服务端 |
| `store_managed` | 商店安装与更新，启动器只唤醒 | 基岩 |
| `instance_dir` | 实例拥有独立游戏目录 | Java、服务端 |

### 实例模型
`config.json` 里的 `selected_version` + `game_directories` 会在首次启动时**一次性迁移**成实例，
每个实例有独立 `game/` 目录、自己的内存/JVM/Java 配置、最后游玩时间与累计时长。
这才是「1.7.10 的 mods 里混进 1.20.1 的 mod → MixinTweaker 崩」的根治办法（旧版只是加了一个目录映射补丁）。

### 下载器
库内下载是串行、无续传的。现在：
- HEAD 探测 `Content-Length` / `Accept-Ranges`，支持则**分块并发**（默认 4，可配）；
- 断流从 `.part` 续传，指数退避重试 3 次；
- 落盘前校验 SHA1，不符直接丢弃；
- 用 `install_into_mll()` 把实现绑到库内 11 个模块（`_helper`/`install`/`forge`/`fabric`/`quilt`/`runtime`/`mrpack`/`mod_loader.*`）——只 patch `_helper` 是无效的，因为它们都是 `from ._helper import download_file`。

实测：本地 Range 服务器 6 MB 文件 0.02 s 下完并校验通过；预置 2 MB `.part` 后能续传；错误 SHA1 会报错。

### 崩溃诊断
18 条规则覆盖 OOM、`UnsupportedClassVersionError`、MixinTweaker 缺失、缺前置 mod、重复 mod、GLFW/OpenGL、
`Could not reserve enough space`、`Unrecognized VM option`、`Unable to access jarfile`、网络失败、EULA、
`hs_err_pid` 原生崩溃、`Exception in server tick loop`、Mixin apply 失败等。
真实对照：正常的 `latest.log`（12 882 行）0 条；1.7.10 混入 1.20 mod 的崩溃日志命中 2 条并指出真因。

### 基岩版与 BDS：诚实的能力边界
- **基岩版（Windows）**：只做「探测已安装 AppX → `explorer shell:appsFolder` 唤醒 → 导入 .mcpack/.mcaddon/.mcworld」。
  `list_remote()` 返回 `None`，`install()` 明确拒绝并指向 Microsoft Store，不注入账号、不降级、不伪造 pid。
- **BDS 服务端**：导入官方 zip → 启动 `bedrock_server.exe` → stdout 落盘 + stdin 控制台（`send_command`/`tail`）。
  **绝不代写 `eula.txt`**：缺 EULA 时直接拒绝启动并给出要改的文件与值。

### 兼容与迁移
被取代的旧实现（`core/version_manager.py`、`launcher.py`、`mod_manager.py`、`modpack.py`、`ui/pages/versions_page.py`）
归档在 `.review/removed/legacy/`，可恢复。`core/java_manager.py` 保留，只作为 provider 缺失时的兜底。

### v0.9.1 修复：镜像缺文件 + lzma 压缩

真机安装 1.7.10 时暴露了两个问题（截图里报错的 URL 是 `client-1.7.xml`——那是 **log4j 配置**，不是客户端 jar）：

1. **镜像缺文件没有回退**。BMCLAPI 没有镜像全部 object：`client-1.7.xml`、`lwjgl-platform-2.9.1.jar`、
   `jinput-platform-2.0.5.jar`、`twitch-platform-5.16.jar`、`twitch-external-platform-4.5.jar` 在镜像上 404，
   `netty-1.8.8.jar`、`splash2x.gif` 甚至 403。于是"换国内源反而装不上老版本"。
   现在 `Session.request` 补丁命中 403/404/410 时会用原始 URL 再请求一次，并把该 URL 记进进程级黑名单；
   安装完成时 UI 会说明"本次 N 个文件在当前源缺失，已自动改走官方源"（`mirror.fallback_events()`）。
2. **下载器接管漏了 lzma 语义**（v0.9 引入的回归）。库在 `lzma_compressed=True` 时要先解压再校验 sha1，
   接管实现把压缩体直接落盘 → JRE 安装必然 `SHA1 校验失败`。现已实现完整语义：
   下载 `.lzma` → 解压 → 校验解压后的哈希 → 落盘。
3. 安装/导入失败的弹窗改用 `friendly_error()`：404 说明是源缺文件（不是网络问题），
   超时提示换源/查代理，SHA1 不符提示重试。

端到端验证：1.7.10 全新安装 **106.8 秒完成** —— client jar 5.2 MB、libraries 33 个文件、
assets 674 个对象、jre-legacy 就位；期间 6 个文件在镜像缺失，全部自动回退官方源。
### v0.9.2：把「实例」和「版本」两个概念分清楚

真机反馈：「删了实例，安装面板里还显示 ✓已安装」。这不是 bug，是两个概念没被区分：

- **版本**（`versions/<id>/` + 共享的 `libraries` / `assets` / `runtime`）装在磁盘上，可被多个实例共用；
- **实例**（`instances/<id>/game/`）是「用哪个版本 + 独立存档/mods/配置」。

删实例只动后者，所以版本仍然「已安装」。现在：

- 列表标记区分 **`✓已安装`**（有实例）与 **`✓已安装 · 无实例`**；
- 安装面板新增 **「卸载版本」**（删除 `versions/<id>/`，共享库不动）；有实例在用时禁用并提示「先删实例」；
- 「删除实例」对话框写明：版本本体不会被删，要删它在安装面板点「卸载版本」；
- 启动时为「已安装但无实例」的版本自动补建实例（`InstanceStore.sync_installed`），
  主动删过的记进 `instance_tombstones` 不再补建；手动建实例 / 卸载版本时清掉对应墓碑。

顺带修掉两个真问题：

1. `get_installed_versions` 以前对任何一个坏掉的版本 json 整批抛异常（缺 `releaseTime` 就 KeyError），
   结果一个坏文件让**所有**版本从界面消失；现在逐个解析，坏文件只跳过自己。
2. 「卸载版本」按钮明明该亮却永远灰：`CAP_UNINSTALL` 没被 import，`NameError` 被 `except Exception` 吞了。
### v0.9.3：中文安装目录下的 Java 8（真机 "no zip in java.library.path"）

真机报错：

```
Error occurred during initialization of VM
java.lang.UnsatisfiedLinkError: no zip in java.library.path
```

挖下去是三个层次，全都只在 Java 8 上出现（Java 17/21 不受影响）：

| 含中文的路径 | 现象 | 修法 |
|---|---|---|
| `java.home` | `no zip in java.library.path` | Mojang 运行时迁到 `%LOCALAPPDATA%\CBL\runtime` |
| `java.library.path` | `lwjgl64.dll: Can't find dependent libraries` | JVM 走 ASCII 目录联接 + native 库复制兜底 |
| `-cp` | `找不到或无法加载主类`（同一个 jar 换 ASCII 路径就正常） | 全部路径经 `%LOCALAPPDATA%\CBL\mc` 联接改写 |

实测对照（同一份 jre-legacy、同一个 1.7.10.jar）：

```
C:\...\minecraft启动器\...\bin\java.exe -version        -> rc=1
%LOCALAPPDATA%\CBL\runtime\...\bin\java.exe -version    -> rc=0 (1.8.0_51)
-cp <中文路径 1.7.10.jar> net.minecraft.client.main.Main  -> 找不到主类
-cp <CBL\mc 下同一个 jar> ... Main                       -> 进入主类（缺 joptsimple，说明已加载）
```

实现：

- `core/paths.py: ascii_mirror()` —— `mklink /J %LOCALAPPDATA%\CBL\mc <真实 .minecraft>`，
  零拷贝、不需要管理员权限、对 Java 透明；每次启动校验联接是否还指向正确目录，不对就重建。
- `core/providers/java/runtime.py` —— 运行时根按需切到 `%LOCALAPPDATA%\CBL\runtime`；
  启动时把旧位置（含中文）的运行时自动迁移过去；并 patch 库的 `install_jvm_runtime`，
  让新下载的 JRE 也落在 ASCII 根（否则 `install_minecraft_version` 又会把它装回中文目录）。
- `core/providers/java/launch.py` —— `rewrite_root()` 把 classpath / `-Djava.library.path` / `--gameDir`
  一次性换成联接前缀；`prepare_ascii_natives()` 在联接不可用时仍把 native 库复制到英文目录。
- 联接建不起来（例如目标跨磁盘）且用的是 Java 8 时，直接抛可读错误，不再让人对着 "no zip" 猜。


