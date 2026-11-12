# 加载器与渲染补丁兼容性

> **复核日期 2026-11-12。** 下面每一条都在给出的链接里对着原文核过一遍。
> `✅` = 点开链接能直接读到这句话（官方文档、官方 FAQ、官网下载页、作者本人的发布帖）。
> `⚠️` = 链接里读不到「不能共存 / 必须二选一」这类原话，结论是从 fork 关系、版本范围或加载器机制推出来的，推理链写在条目里。
> 正文共 **17 条：✅ 13 条、⚠️ 4 条**。复核中与原始结论不一致的 4 处，写在对应条目的「复核备注」里。

这份文档是数据层 [combos.py](core/providers/java/combos.py) 的人读版：数据层只存规则、出处和 `verified` 标记，本文解释为什么是这些规则。
界面侧只读这份数据（[crafting.py](ui/widgets/crafting.py) 里不写死任何一条兼容性判断），所以改规则改数据层，不要改 UI。

## 一句话结论

主加载器之间是**真互斥**（槽位层面只允许一个，不是「建议别同时装」），LiteLoader 是**附加层**，OptiFine 是**渲染补丁**。谁能和谁同框：

|  | Forge | NeoForge | Fabric | Quilt | LiteLoader | OptiFine |
|---|---|---|---|---|---|---|
| **Forge** | — | ⛔ | ⛔ | ⛔ ⁽¹⁾ | ✅ ⁽²⁾ | ✅ ⁽³⁾ |
| **NeoForge** | ⛔ | — | ⛔ ⁽¹⁾ | ⛔ ⁽¹⁾ | ⛔ ⁽¹⁾ | ⛔ |
| **Fabric** | ⛔ | ⛔ ⁽¹⁾ | — | ⛔ | ⛔ ⁽⁴⁾ | ⚠️ ⁽⁵⁾ |
| **Quilt** | ⛔ ⁽¹⁾ | ⛔ ⁽¹⁾ | ⛔ | — | ⛔ ⁽⁴⁾ | ⚠️ ⁽⁵⁾ |
| **LiteLoader** | ✅ ⁽²⁾ | ⛔ ⁽¹⁾ | ⛔ ⁽⁴⁾ | ⛔ ⁽⁴⁾ | — | ✅ |
| **OptiFine** | ✅ ⁽³⁾ | ⛔ | ⚠️ ⁽⁵⁾ | ⚠️ ⁽⁵⁾ | ✅ | — |

- ✅ 可以同框（可能有版本前提）　⚠️ 能同框但必须靠第三方 mod 转，且不保证　⛔ 不能同框
- ⁽¹⁾ 代码里没有这个组合的单条规则，靠「主加载器四选一」的槽位机制挡住（见下文「三个层级」）。
- ⁽²⁾ 仅 1.12.2 及以前：LiteLoader 最高只做到 1.12.2。
- ⁽³⁾ OptiFine 与 Forge 是**版本级**约束：能不能一起装取决于 OptiFine 那一版标注的 Forge 版本号。
- ⁽⁴⁾ LiteLoader ≤ 1.12.2 与 Fabric/Quilt ≥ 1.14 的版本范围不重叠，无所谓兼容不兼容。
- ⁽⁵⁾ 需要 OptiFabric；Quilt 这条没找到任何官方说法。

## 三个层级

不是「四个下拉框选一个」，因为这四类东西在游戏启动链路里处在不同的位置，能被叠加的层数不一样：

| 层级 | 数据层常量 | 成员 | 数量 | 叠加规则 |
|---|---|---|---|---|
| 主加载器 | `combos.PRIMARY` | Forge / NeoForge / Fabric / Quilt | 四选一 | 一个实例只能有一个，谁先接管 tweak/loader 链就是谁 |
| 附加层 | `combos.ADDON` | LiteLoader | 最多一个 | 本身是 tweakclass jar，可以当 mod 塞进 Forge 的 `mods/` |
| 渲染补丁 | `combos.PATCH` | OptiFine | 最多一个 | 不是加载器，是改渲染的 jar；冲突对象是别的渲染 mod，不是加载器 |

为什么必须分开：

1. **加载器回答的是「谁来加载 mod」，渲染补丁回答的是「画面怎么画」。** OptiFine 从来不是加载器 —— 它没有 mod 解析、没有依赖图，装进 `mods/` 后由 Forge/Fabric 负责加载。把它和 Forge 放进同一个「四选一」里，会让人以为 OptiFine 和 Forge 是竞争关系，而实际上它们是「加载器 + 补丁」。
2. **附加层的前提是它得能被主加载器加载。** LiteLoader 的官方说法是它能作为 tweakclass jar 被 FML 加载（见条目 9），所以它是「叠在 Forge 上的一层」，不是「和 Forge 并列的选项」。
3. **互斥和「不建议」不是一回事。** 下拉框表达不了互斥：你选了 Forge，Fabric 就从列表里消失了，用户分不清「被隐藏」和「根本不存在」。合成台把所有材料都摆出来，放不进去的让成品格变红并说明原因 —— 这是 [crafting.py](ui/widgets/crafting.py) 里 `CraftingBench` 的设计动机。

界面上的实现：

- 材料格排成 3 列 × 2 行（横向铺开是为了给下面的版本列表留高度）：第一行 Forge / NeoForge / Fabric，第二行 Quilt / LiteLoader / OptiFine（`CraftingBench.__init__` 里按 `loaders_of(PRIMARY)` + `loaders_of(ADDON)` + `loaders_of(PATCH)` 顺序生成）。
- 点中一个主加载器时，`CraftingBench._on_toggled` 会把其它主加载器全部取消勾选并清空版本 —— **这就是「四选一」真正生效的地方**，它不依赖 `PAIR_RULES` 里有没有对应条目。
- 三种槽位状态：`ok`（可装）、`na`（当前 MC 版本没有这个加载器，**仍可点**，点了成品格变红并说明原因）、`manual`（LiteLoader，本启动器只判断兼容性、不代装）。三种都不禁用：让用户放进去看到原因，比让按钮变灰要猜有用。
- LiteLoader 被选中时合成台会多出一条 warn「不会自动安装」，并且它不进自动安装配方（`install_plan()["manual"]`），装完由启动器提示用户手动加。
- OptiFine 的槽位不列版本号，只让用户选本地 jar，版本号从文件名里抠（`tag_from_optifine_jar`）；装完由启动器把 jar 放进实例的 `mods/`。

## 逐条结论与出处

### 1. Forge × Fabric 不能共存 ✅

> No. Forge mods must run on Forge, and Fabric mods must run on Fabric. You cannot mix mods.
> — Fabric 官方 FAQ，<https://wiki.fabricmc.net/faq:user>

同一段下面还有两条更容易被忽略的补充：

> - Fabric does not work on top of Forge.
> - It is theoretically possible to create a way to do so - that is to say, there are no known major technical obstacles in accomplishing such.

中文：Forge 的 mod 只能在 Forge 上跑，Fabric 的 mod 只能在 Fabric 上跑，两边不能混。Fabric 不是「装在 Forge 上的插件」；技术上做一个兼容层是可能的（后来也确实有了 Sinytra Connector 这类项目），但官方明确说 Fabric 不跑在 Forge 上面。

**落到代码**：`PAIR_RULES` 里 `forge|fabric` → `BLOCKED`，`verified=True`，提示语指向 Sinytra Connector（仍然是「只有一个加载器」的 mod 层兼容，见「常见误解」）。

### 2. Fabric 支持 1.14 及以上 ✅

> For most cases, the answer is "snapshot 18w43b and above, releases 1.14 and above".
> — Fabric 官方 FAQ，<https://wiki.fabricmc.net/faq:user>

中文：绝大多数情况下，Fabric 支持 18w43b 及之后的快照、1.14 及之后的正式版。1.13.2 及以前没有 Fabric（那时只有 Forge 和 LiteLoader 这类老方案）。

**落到代码**：`LOADERS` 里 `Loader("fabric", ..., min_mc="1.14")`，`availability()` 在低于 1.14 时返回「需要 Minecraft 1.14 及以上」。

### 3. Quilt 直接吃 Fabric mod ✅

> A powerful mod loader compatible with all your favourite Fabric mods, with lots of configuration options, more APIs for mod developers, and more!
> — Quilt 官网首页，<https://quiltmc.org/en/>

中文：Quilt 是一个 mod loader，兼容你最喜欢的那些 Fabric mod。这句话只说明「mod 能跑」，**不说明「能和 Fabric 加载器同时存在」** —— 这是本文最容易被读错的一句。

Quilt 自己的源码 README 给了更强的旁证（说明它内部自带 Fabric 的实现，而不是外挂）：

> The loader for mods under Quilt. It provides mod loading facilities and useful abstractions for other mods to use.
> When adding classes that contain code from fabric-loader they should use the modified header file
> — quilt-loader README，<https://github.com/QuiltMC/quilt-loader>（原文见 <https://raw.githubusercontent.com/QuiltMC/quilt-loader/master/README.md>）

仓库里 `src/fabric/api/java` 被描述为 "contains all fabric-loader apis (Non deprecated apis that any fabric mods can use)" —— 即 Quilt 自己实现了一份 Fabric 的 API/加载器类。

**落到代码**：`PAIR_RULES` 里 `fabric|quilt` → `BLOCKED`，提示语「Quilt 能直接加载 Fabric mod，换过去不用换 mod」。

### 4. Quilt × Fabric 只能二选一 ⚠️

**这一条是推论。** Quilt 官网从头到尾没有一句「不能和 Fabric 共存」；复核时我把首页整段文本拉下来搜过，"Fabric" 只出现在「兼容 Fabric mod」和博客里「Fabric mods for these versions will work fine」这两个位置。

推理链：

1. Quilt 官网自己把它定义成 "mod loader"（加载器），Fabric 也是加载器。
2. 一个实例在启动时只能有一条 tweakclass/loader 链接管游戏，两个加载器都要接管，就会互相盖掉对方的类转换。
3. quilt-loader 的源码里带着 fabric-loader 的 API 包（条目 3），说明它是 Fabric 的**替代实现**，而不是能叠在 Fabric 上面的插件。
4. Quilt 官方文档里最接近「同源」的一句是（<https://wiki.quiltmc.org/en/faq>）：

   > On Quilt, you'll always have access to Fabric API and Fabric Loader, so all of these tutorials can be used without issue.

   中文：在 Quilt 上你**始终**能用到 Fabric API 和 Fabric Loader，所以那些 Fabric 教程直接照抄就行。这句说的是「Quilt 自己就提供 Fabric 那一套」，仍然不是「Quilt 不能和 Fabric 共存」的原话，但方向一致：它是替身，不是插件。

结论可以写「二选一」，但要按 ⚠️ 呈现：界面用金色提示 +「（推论，未见官方明文）」，不用红色断言。这也是 `Rule.verified=False` 这个字段存在的意义 —— `CraftingBench._render_issues` 对未验证的规则统一追加那句后缀。

**落到代码**：`PAIR_RULES` 里 `fabric|quilt` → `BLOCKED`，`verified=False`。

**版本备注**：代码里 Quilt 的 `min_mc` 写的是 `"1.14"`（照抄 Fabric 的下限）；Quilt 官方 meta 的游戏版本清单里最老一条是 **1.14.4**（<https://meta.quiltmc.org/v3/versions/game>）—— 1.14 ~ 1.14.3 不在那份清单里。这个边界差三档，属于「按 Fabric 的下限近似」，不是官方声明。

### 5. NeoForge 是基于 Forge 的分叉 ✅

> A modding API for Minecraft: Java Edition, based on Forge
> — NeoForge 仓库描述，<https://github.com/neoforged/NeoForge>

中文：NeoForge 是「基于 Forge」的 Minecraft Java 版 modding API。这句是项目自述（GitHub 仓库的 title 与 meta description 都是这句），可以当官方明文引用。

**落到代码**：`PAIR_RULES` 里 `forge|neoforge` 的 `reason` 与 `source`。

### 6. Forge × NeoForge 同一实例只能装一个 ⚠️

**这一条是推论。**NeoForge 自述「based on Forge」，但「based on」不等于「不能同时装」；官方没有一句「NeoForge 与 Forge 不能共存」。

推理链：NeoForge 分叉自 Forge 的代码库，两边提供的是**同一套东西**（FML、mods.toml 解析、事件总线）的不同版本实现。同一个实例的加载链只能有一个 FML，两个都得接管 `--launchTarget`/`--fml.mcVersion` 那套参数。

**落到代码**：`PAIR_RULES` 里 `forge|neoforge` → `BLOCKED`，`verified=False`。

### 7. NeoForge 官方最早的版本是 Minecraft 1.20.1（47.x）✅

官方 Maven 上能直接读到这条分界：

- `net.neoforged:forge`（<https://maven.neoforged.net/releases/net/neoforged/forge/maven-metadata.xml>）里 63 个版本全是 `1.20.1-47.x` 格式，最新 `1.20.1-47.1.106`。
- `net.neoforged:neoforge`（<https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml>）里 1.20.x 的正式版从 `20.2.x` 开始，一路到 `21.x` / `26.x`。

中文：NeoForge 的 1.20.1 时期用 47.x 版本号、发布在 `net.neoforged:forge` 这个坐标下；从 1.20.2 起换成 `net.neoforged:neoforge` 坐标和「MC 版本对齐」的版本号（1.20.2 → 20.2.x，1.21.1 → 21.1.x）。所以「NeoForge 首个版本是 1.20.1（47.x）」这句话是能核的，但**版本号前缀和坐标不是同一个**，写文档时别简写成「NeoForge 47.x 起」。

**落到代码**：`LOADERS` 里 NeoForge 的 `limit_note` 明确写了「NeoForge 官方其实有 1.20.1 的 47.x」，用来和下面这条区分开。

### 8. 本启动器只做到 NeoForge 1.20.2+（项目限制，不是 NeoForge 的限制）✅

[loaders.py](core/providers/java/loaders.py) 里：

```python
# minecraft-launcher-lib 8.0 的 neoforge 通道只覆盖 1.20.2 及以上
_NEOFORGE_MIN_MC = "1.20.2"
_NEOFORGE_HINT = "NeoForge 需要 Minecraft 1.20.2 及以上；1.20.1 请改用 Forge。"
```

同文件的注释还记了实测结论：「1.20.1 的 47.x 构建既不在 neoforge 通道，也不在 forge 通道」。这不是 NeoForge 的限制，是本项目依赖的安装库的限制 —— 上文条目 7 已经在官方 Maven 上验到 47.x 存在。

**落到代码**：`LOADERS` 里 NeoForge 的 `min_mc="1.20.2"` + `limit_note`；`availability()` 命中下限时优先用 `limit_note` 这句文案，而不是默认的「需要 Minecraft x 及以上」。这样界面不会把项目限制说成上游限制。

### 9. LiteLoader 可以作为模组装在 Forge 下 ✅

作者 Mumfrey 在 Minecraft Forum 的官方发布帖里写得很直白：

> LiteLoader is a lightweight mod bootstrap designed to provide very basic loader functionality for mods which don't need to modify game mechanics. It is designed to run alongside Minecraft Forge and Forge Mod Loader (FML) and LiteLoader mods will virtually never conflict with Forge mods.
> — Minecraft Forum 官方帖，<https://www.minecraftforum.net/forums/mapping-and-modding-java-edition/minecraft-mods/1290155-liteloader>

同一帖的功能列表里还有一句（原文拼写就是 `Compatibile`）：

> Compatibile with Minecraft Forge and FML thanks to dynamic injection

以及在 2014-02-15 的更新日志（LiteLoader 1.7.2_04）里：

> Support for being loaded as a tweakclass jar, eg. loaded by FML by just extracting the jar and dropping it in "mods"

中文：「可以直接解压丢进 mods 文件夹，由 FML 当成 tweakclass jar 加载」—— 这就是「LiteLoader 能作为 mod 装在 Forge 下」的原始出处。官方帖同时声明它是**为与 Forge 并行运行而设计**的。

**落到代码**：`PAIR_RULES` 里 `forge|liteloader` → `NOTE`（不是 `BLOCKED`，也不是 `WARN`）；提示语保留了现实约束「Forge 太新 + LiteLoader 太老会出问题」。

### 10. LiteLoader 已停更，最高支持到 1.12.2 ✅

MC百科条目（<https://www.mcmod.cn/class/610.html>）页面上直接标着：**「停更」** 标签、`运作方式: Forge , LiteLoader , 文件覆盖`、`支持的MC版本` 两个列表各 16 个版本，最高一条都是 **1.12.2**。

中文：MC百科是社区编辑的第三方百科（不是厂商自述），但「停更 + 最高 1.12.2」这种版本事实与 Forum 帖的时间线一致：作者的更新日志停在 1.12.2 时代，之后再无新版本。

**落到代码**：`Loader("liteloader", ..., ADDON, max_mc="1.12.2")`；界面侧 `CraftingBench._refresh` 把 LiteLoader 槽位固定为 `manual`（「已停更，本启动器只做兼容性提示、不自动安装」），点不动。

### 11. LiteLoader × OptiFine 可以共存 ✅（1.7.10 / 1.12.2 时代的经典三件套）

还是同一帖的更新日志（LiteLoader 1.7.2_04）：

> Support for loading jars containing tweakclasses in their metadata - this means that this version of liteloader and future versions can load Optifine, and also Forge
> — <https://www.minecraftforum.net/forums/mapping-and-modding-java-edition/minecraft-mods/1290155-liteloader>

中文：这一版起的 LiteLoader 能加载「元数据里带 tweakclass 的 jar」，也就是能直接吃 OptiFine（也能吃 Forge）。作者用的是「this version ... and future versions」，即向后生效。

配合条目 9 的「为与 Forge 并行运行而设计」，`Forge + LiteLoader + OptiFine` 这个 1.7.10 时代的经典三件套是有作者原文支撑的，不是社区口口相传。

另有一条第三方旁证（MC百科 OptiFine 条目）：`1.12.2 及之前版本一般与任意 Forge 版本兼容。` —— 意思是老三件套不必逐版本对 Forge 版本号，这条只对 1.12.2 及以前成立。

**落到代码**：`PAIR_RULES` 里 `liteloader|optifine` → `NOTE`，`verified=True`，`reason` =「LiteLoader 能直接加载 OptiFine」。

### 12. OptiFine × Forge 是版本级约束，不是加载器级互斥 ✅

optifine.net 的下载页上，每个 OptiFine 版本那一行都标了它要求/配合的 Forge 版本号；对不上的写 `Forge N/A`。举例（2026-11-12 抓取到的页面内容）：

| OptiFine 构建 | 页面上的 Forge 列 |
|---|---|
| OptiFine HD U J9（Minecraft 1.21.11） | `Forge 61.0.8` |
| OptiFine HD U E4（Minecraft 1.13.1） | `Forge N/A` |

中文：这不代表「OptiFine 和 Forge 不能一起用」，而是「这一版 OptiFine 只认这个 Forge 版本」。所以规则是 `WARN` 不是 `BLOCKED`，并且校验放在 `check_combo` 的第 3 段（版本级提示），不是两两冲突那一段。

MC百科的同一条目补了历史背景，值得一起读：

> Minecraft Forge 在 1.13 时期的变动致使 Forge 不兼容高清修复，直到 1.14.4 开始 Forge 和高清修复冲突的问题才被解决。

> 大部分第三启动器在安装高清修复时会列出相对应的 Forge 版本。

**复核备注（与原始结论有出入）**：原始结论里说「每个版本只有 Installer 和 Forge 两列」—— **这一版页面已经不是这个结构**。2026-11-12 抓到的页面里没有任何 `Installer` 字样（`installer` 不区分大小写也是 0 次），每行的列是：文件名 / Download / (Mirror) / Changelog / **Forge 版本号或 `Forge N/A`** / 日期。也就是说「OptiFine 的 jar 本身就是安装器，页面只额外标 Forge 版本」这个事实没变，但「两列」的说法过期了。**结论不变，依据的形态变了。**
另外这次抓取被截断在 100,000 字符（覆盖 Minecraft 26.2 → 1.12.2 段），1.12.2 以下的老版本行没抓到，所以「整页都没有 NeoForge」只能对已抓到的段落断言。

### 13. OptiFine 官方下载页没有 NeoForge 构建 ✅（当前状态）

复核方式：把 <https://optifine.net/downloads> 拉下来，在已抓到的 100,000 字符里数关键字：

| 关键字 | 出现次数 |
|---|---|
| `Forge`（区分大小写） | 187 |
| `colForge`（表格列） | 94 |
| `Forge N/A` | 36 |
| `NeoForge` / `neoforge` | **0** |
| `Fabric` | **0** |

中文：官方下载页只提供「独立安装器形式」的 jar 和「标了 Forge 版本号」的 jar，没有 NeoForge 构建，也没有 Fabric 构建。所以「想在新版本用 OptiFine + NeoForge」这条路，在官方下载页上不存在。

**复核备注（与原始结论有出入）**：说「OptiFine **没有** NeoForge 版」时要注意时态。MC百科 OptiFine 条目里写着：

> NeoForge 作者曾发表声明正在开发高清修复的 NeoForge 版本，但是目前计划是支持新版本，会在新版本稳定后继续 NeoForge 版本的开发。

也就是说官方曾公开表态在做（至今未发布）。所以准确的写法是「**当前官方下载页没有 NeoForge 构建**」，而不是「OptiFine 永远不会有 NeoForge 版」。规则仍然该挡（现在确实没有可下的构建），但理由要写成现状，不是断言。

**落到代码**：`PAIR_RULES` 里 `optifine|neoforge` → `BLOCKED`，`source` 指向 downloads 页；提示语给替代方案「Sodium + Iris，或退回 Forge」。

### 14. OptiFine × Fabric 要靠 OptiFabric 转，且不保证兼容 ✅

Fabric 官方 FAQ 是这句话最硬的出处：

> Consider using alternatives to OptiFine like Sodium and Iris, as unofficial mods such as OptiFabric may not be compatible with your mods.
> In particular, OptiFabric 1.14.25 is currently incompatible with Architectury API and Replay Mod.
> — <https://wiki.fabricmc.net/faq:user>

中文：Fabric 官方建议用 Sodium/Iris 替代 OptiFine，因为 OptiFabric 这类非官方 mod **可能**与你的其它 mod 不兼容，并且点名了具体的不兼容组合。

OptiFabric 自己的 README 也把边界说清楚了：

> **Note:** This project is not related or supported by either Fabric or Optifine.
> Note Fabric, Optifine and OptiFabric are still all in beta, so things will be broken.
> — OptiFabric README，<https://github.com/Chocohead/OptiFabric>（<https://raw.githubusercontent.com/Chocohead/OptiFabric/master/README.md>）

中文：OptiFabric 与 Fabric、OptiFine 双方都没有隶属关系，两边都不为它背书；它自己承认「东西会坏」。所以这条只能是 `WARN`，且提示语要写「能不用就不用」。

**复核备注（与原始结论有出入）**：「OptiFabric 自己说不保证兼容」这句的**归属写错了**。逐字原文 "may not be compatible with your mods" 出自 **Fabric 官方 FAQ**，不是 OptiFabric 的自述；OptiFabric 自己的 README 说的是「not related or supported by either Fabric or Optifine」和「things will be broken」。结论（需 OptiFabric、不保证兼容）不变，但引用时要引 Fabric FAQ，别写成 OptiFabric 的官方 FAQ。
另外 [combos.py](core/providers/java/combos.py) 里这条规则的 hint 现在写的是「OptiFabric 官方 FAQ 自己也说……」，与上面的核实结果不符 —— 数据层那句话需要改成「Fabric 官方 FAQ 说 OptiFabric 这类 mod 可能不兼容」。文档按核实结果写，代码本轮不动。

**落到代码**：`PAIR_RULES` 里 `optifine|fabric` → `WARN`，`verified=True`，`source` = Fabric FAQ。

### 15. OptiFine × Quilt 只能走 OptiFabric，且没有任何官方说法 ⚠️

**这一条是推论。**Quilt 官网、Quilt 的开发文档（<https://wiki.quiltmc.org/en/faq>）、optifine.net 下载页都没有提到 Quilt + OptiFine 这个组合；optifine.net 上 `Fabric` 出现 0 次（见条目 13），更没有 Quilt。

推理链：

1. Quilt 能吃 Fabric mod（条目 3），所以理论上 OptiFabric 也能被 Quilt 加载。
2. 但 OptiFabric 是「给某个版本的 Fabric Loader 打补丁」的 mod，它依赖 Fabric Loader 的具体实现细节（README 里那段 "How it works" 就是一连串对 loader 的假设）。Quilt 虽然兼容 Fabric 的 API，内部实现是自己的。
3. 因此「Quilt 能吃 OptiFabric」只能算**可能**，装之前要备份存档。

**落到代码**：`PAIR_RULES` 里 `optifine|quilt` → `WARN`，`verified=False`，提示语「装之前先备份存档」。

### 16. OptiFine 与 Sodium / Lithium / Canvas 冲突 ✅

MC百科 OptiFine 条目（<https://www.mcmod.cn/class/36.html>）原文：

> 高清修复与 钠 、 锂 及 Canvas 渲染器 冲突。 若使用 钠 请使用 Iris Shaders 加载光影。

同一段还有一条更具体的（钠的 Forge 移植版）：

> 高清修复与任何 钠 的 Forge 移植版（如 Embeddium 、 铷 等）冲突。

以及为什么冲突：

> 由于 OptiFine 对核心渲染器的修改较大，在使用其它视觉效果和渲染优化的模组时请提前查询。 并且由于其闭源并进行侵入性修改，出现冲突时模组作者很难寻找原因，加上已出现不同功能的替代品，其在高版本（1.16.5+）兼容性较差，大部分模组作者不愿为其做兼容，建议单独添加。

中文：钠 = Sodium，锂 = Lithium，Canvas 是另一个渲染器。OptiFine 直接改核心渲染器且闭源，跟这几个「直接换渲染管线」的 mod 天然打架。注意这是**mod 层**冲突，和加载器无关 —— OptiFine 与这些 mod 是否冲突，取决于你装了什么 mod，不是选了哪个加载器。

**落到代码**：这个冲突在数据层里目前只写在 `Loader("optifine", ...)` 的 `note` 里（「与 Sodium / Iris / Lithium 冲突」），没有进 `PAIR_RULES` —— 因为 `PAIR_RULES` 只描述加载器之间，而 Sodium/Lithium/Canvas 都不是加载器。UI 的 OptiFine 槽位 tooltip 会带出这句。

### 17. OptiFine 与 Iris 不构成原文里的「冲突」⚠️

**这一条是推论。**复核 MC百科原文时，Iris 出现的两处都是「替代方案」语境（`若使用 钠 请使用 Iris Shaders 加载光影`），**没有**「Iris 与高清修复冲突」这句话。

推理链：Iris 是给 Sodium 用的光影加载器，装 Iris 的前提是装 Sodium；而 Sodium 与 OptiFine 明确冲突（条目 16）。所以 Iris + OptiFine 在实践中同样装不到一起，但原因是**间接的**（Iris → 需要 Sodium → Sodium 与 OptiFine 冲突），不是官方对 Iris + OptiFine 的直接判断。

**复核备注（与原始结论有出入）**：原始结论把 Iris 和 Sodium/Lithium/Canvas 并列成「OptiFine 与它们冲突」，并挂 MC百科 OptiFine 页作出处 —— 页面原文只点名了钠、锂、Canvas 三个，没点 Iris。Iris 那半句应降级为推论（⚠️），并在文档里说明是间接冲突。

**落到代码**：`Loader("optifine", ...)` 的 `note` 现在写的是「与 Sodium / Iris / Lithium 冲突」—— 准确的说法是「与 Sodium / Lithium / Canvas 冲突（Iris 需 Sodium，属间接）」。文档按核实结果写，代码本轮不动。

## 版本级 vs 加载器级

同一个「能不能一起装」的问题，其实是两个不同层级的问题，代码里也分两段处理（`check_combo`）：

| 层级 | 问的是什么 | 典型例子 | 结果 | 代码位置 |
|---|---|---|---|---|
| **加载器级** | 这两个东西**能不能**同时存在 | Forge × Fabric、Fabric × Quilt、Forge × NeoForge、OptiFine × NeoForge | `BLOCKED`，成品格变红，不允许安装 | `check_combo` 第 1、2 段（`availability()` + `PAIR_RULES`） |
| **版本级** | 能装，但**这一版**对得上吗 | OptiFine 的 Forge 版本号、NeoForge 的 47.x/20.2.x 分界、Quilt/Fabric 的 MC 下限 | `WARN` / `NOTE`，黄色提示，允许继续 | `check_combo` 第 3 段 + `Loader.min_mc/max_mc` |

OptiFine 是唯一一个**两级都占**的东西，这也是一句话结论里它总带脚注的原因：

1. **加载器级**：OptiFine 不是加载器，所以它跟 Forge/Fabric/Quilt 之间不存在「谁接管启动链」的冲突 —— 这几对全是 `WARN`/`NOTE`，不是 `BLOCKED`。唯一的 `BLOCKED` 是 NeoForge，理由不是加载器冲突，而是**官网上根本没有对应构建**（条目 13）。
2. **版本级**：能不能真跑起来，取决于 optifine.net 那一行标的 Forge 版本号和你选的 Forge 版本是否一致。1.21.11 那行给的是 `Forge 61.0.8`，你装 61.0.9 或 60.x 都可能出问题；`Forge N/A` 的行（如 1.13.1）则表示该 MC 版本没有官方匹配的 Forge 构建。

所以界面上的呈现也不同：加载器级冲突让成品格变红、`can_compose()` 返回 `False`（`can_install()` 只认 `blocking_issues`）；版本级只出一条黄色提示，用户自己决定。

## 常见误解

### 「能跑对家的 mod」≠「两个加载器能共存」

这是最容易搞混的一点，三个不同的东西在讲三件不同的事：

| 说法 | 原文 | 讲的是 | 不等于 |
|---|---|---|---|
| Quilt 兼容 Fabric mod | "compatible with all your favourite Fabric mods"（Quilt 官网） | **mod 层**：Fabric 的 mod 能被 Quilt 加载 | Quilt 能叠在 Fabric 上 |
| Sinytra Connector | "Lets you play Fabric mods on NeoForge"（<https://modrinth.com/mod/connector>） | **mod 层**：NeoForge 实例里能跑 Fabric mod | NeoForge 和 Fabric 能同时当加载器 |
| Fabric FAQ 说不能混 | "You cannot mix mods." | **加载器层**：一个实例只有一个加载器 | 只要装了 Connector 就能反过来说两个加载器共存 |

Sinytra Connector 的定位是「在 NeoForge 里加一层 Fabric mod 的运行环境」，**加载器仍然只有一个（NeoForge）**。这就是 `PAIR_RULES` 里 `forge|fabric` 的提示语写成「装 Sinytra Connector（仍然只有一个加载器）」的原因。

代码里对「mod 层兼容」有另一份独立数据，别和加载器互斥混在一起：[deps.py](core/providers/java/deps.py) 的 `_COMPATIBLE_LOADERS`：

```python
_COMPATIBLE_LOADERS = {
    "forge": {"forge"},
    "neoforge": {"neoforge", "forge"},   # Forge mod 能在 NeoForge 上跑
    "fabric": {"fabric"},
    "quilt": {"quilt", "fabric"},        # Fabric mod 能在 Quilt 上跑
}
```

注意这份数据里的「兼容」是**判定某个 jar 能不能装进当前实例**用的，和 `PAIR_RULES` 的「两个加载器能不能同框」是两套东西。把两套合并会直接推出错误结论（例如「deps 说 neoforge 兼容 forge，所以 Forge + NeoForge 可以同框」—— 错，那说的是 mod 的元数据）。

### 「OptiFabric 能跑」≠「OptiFine 在 Fabric 上没问题」

OptiFabric 是第三方补丁 mod，Fabric 官方 FAQ 明确说它「may not be compatible with your mods」，还点名了具体冲突组合（条目 14）。所以 OptiFine + Fabric 这条规则是 `WARN`，不是 `NOTE`。

### 「OptiFine 是加载器」

不是。它没有 mod 解析和依赖图，装进 `mods/` 之后由 Forge 或 Fabric 负责加载它自己。把它当成「第四种加载器」会导出两个错误结论：以为它和 Forge 互斥；以为它不能和其它 mod 一起装。

### 「LiteLoader 已经不能用了」

它确实停更（条目 10），但它停更的那个版本范围（≤1.12.2）里，它是**被官方明确说能配合 Forge 用**的（条目 9）。本启动器对它的定位是「只认不装」：槽位禁用、只提示兼容性（`CraftingBench._refresh` 里固定 `manual` 状态），因为它已经不可能被自动安装流程正确处理。

## 数据在哪

| 内容 | 位置 | 说明 |
|---|---|---|
| 加载器定义（名称、层级、MC 版本范围、文案） | [combos.py](core/providers/java/combos.py) 的 `LOADERS` / `Loader` | 加一个新加载器 = 往这个列表加一条 |
| 两两兼容规则 + 出处 + `verified` | 同文件 `PAIR_RULES` / `Rule` | 11 条规则，每条带 `source` 与 `verified` |
| 组合校验（版本范围 → 互斥 → 版本级提示） | 同文件 `check_combo()` / `blocking_issues()` / `can_install()` | UI 只调这三个，不自己判断 |
| 从版本目录名反推材料 | 同文件 `detect_from_version_id()` | 认不出就返回空 dict，不猜 |
| OptiFine 版本号从 jar 文件名抠 | 同文件 `tag_from_optifine_jar()` | 形如 `OptiFine_1.12.2_HD_U_G5.jar` → `HD_U_G5` |
| mod 层的加载器兼容（jar 能不能装） | [deps.py](core/providers/java/deps.py) 的 `_COMPATIBLE_LOADERS` | 和 `PAIR_RULES` 是两套数据 |
| 加载器版本枚举与安装（含 NeoForge 通道的下限） | [loaders.py](core/providers/java/loaders.py) 的 `LOADERS` / `_NEOFORGE_MIN_MC` | 版本下限若来自依赖库，注释里写清楚 |
| 界面：槽位 / 材料清单 / 成品格 / 提示 | [crafting.py](ui/widgets/crafting.py) 的 `CraftingBench` / `LoaderSlot` | 只读 combos，不写死任何兼容性结论 |
| 未验证规则在 UI 上怎么显示 | `CraftingBench._render_issues` | 金色 `⚠` + 「（推论，未见官方明文）」；有 `source` 的挂 tooltip |

规则怎么加一条：

1. 在 `PAIR_RULES` 里加 `_key("a", "b")` 条目，写 `level`（`BLOCKED`/`WARN`/`NOTE`）、`reason`、`hint`、`source`。
2. **有没有原文决定 `verified`**：链接里能读到「不能共存 / 必须二选一 / 官方声明兼容」这类话才写 `True`；只能从 fork 关系推出来的写 `False`，UI 会自动加「（推论，未见官方明文）」。
3. 如果是版本范围问题（不是互斥），别塞进 `PAIR_RULES` —— 改 `Loader.min_mc`/`max_mc` 或 `check_combo` 的第 3 段。

## 复核记录

| 链接 | 结果 |
|---|---|
| https://wiki.fabricmc.net/faq:user | ✅ 抓到原文，「You cannot mix mods.」「1.14 and above」「may not be compatible with your mods」三句都在 |
| https://quiltmc.org/en/ | ✅ 抓到原文，「compatible with all your favourite Fabric mods」在；**没有**任何「不能与 Fabric 共存」的字样 |
| https://raw.githubusercontent.com/QuiltMC/quilt-loader/master/README.md | ✅ 抓到，含 `src/fabric/api/java` 的说明 |
| https://github.com/neoforged/NeoForge | ✅ title 与 meta description 均为「A modding API for Minecraft: Java Edition, based on Forge」 |
| https://www.minecraftforum.net/.../1290155-liteloader | ✅ 抓到「designed to run alongside Minecraft Forge」「can load Optifine, and also Forge」「dropping it in "mods"」 |
| https://www.mcmod.cn/class/610.html | ✅ LiteLoader 条目：「停更」标签、`运作方式: Forge , LiteLoader , 文件覆盖`、最高 1.12.2 |
| https://www.mcmod.cn/class/36.html | ✅ OptiFine 条目：「高清修复与 钠 、 锂 及 Canvas 渲染器 冲突。」等 |
| https://optifine.net/downloads | ⚠️ 抓到但被截断在 100,000 字符（覆盖 26.2 → 1.12.2 段）；无 `NeoForge`、无 `Fabric`、无 `Installer` 字样；93 行均带 Forge 版本号或 `Forge N/A` |
| https://maven.neoforged.net/releases/net/neoforged/forge/maven-metadata.xml | ✅ 63 个版本全为 `1.20.1-47.x` |
| https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml | ✅ 1.20.x 正式版从 `20.2.x` 起 |
| https://meta.quiltmc.org/v3/versions/game | ✅ 最老一条为 `1.14.4` |
| https://modrinth.com/mod/connector | ✅ 简介「Lets you play Fabric mods on NeoForge」（抓的 Modrinth API 项目描述） |
| https://raw.githubusercontent.com/Chocohead/OptiFabric/master/README.md | ✅ 抓到「not related or supported by either Fabric or Optifine」「things will be broken」；原仓库 `modmuss50/OptiFabric` 的 README 只剩一句「OptiFabric Development has moved」，所以按新仓库引用 |
| https://wiki.quiltmc.org/en/faq | ✅ 抓到「On Quilt, you'll always have access to Fabric API and Fabric Loader」；全文 `OptiFine` 出现 0 次，没有关于 OptiFine 或加载器互斥的说明 |
| https://quiltmc.org/en/install/ | ❌ 抓取失败（`fetch failed`），未作为任何结论的依据 |
