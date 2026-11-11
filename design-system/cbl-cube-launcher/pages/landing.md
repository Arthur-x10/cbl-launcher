# Landing Page Overrides

> **PROJECT:** CBL Cube Launcher
> **Generated:** 2026-10-28 22:27:54
> **Page Type:** Landing / Marketing

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1200px (standard)
- **Layout:** Full-width sections, centered content
- **Stack:** 仓库无前端框架。发布页按 `html-tailwind` 的响应式规则实现（mobile-first、px-4/md/lg 间距），但不用 Tailwind CDN：运行时注入的 preflight 会盖过像素组件样式。

### Spacing Overrides

- No overrides — use Master spacing (density 3 / spacious)

### Typography Overrides

- English brand / version chips: Press Start 2P
- Chinese display headings: ZCOOL QingKe HuangYou（google-fonts 检索命中，简体子集）
- Body / legal: Microsoft YaHei UI / PingFang SC / system-ui（保证长文对比度与可读性；Press Start 2P / VT323 无中文）

### Color Overrides

Master 默认「Neon purple + rose」与 CBL 草方块品牌冲突。本页覆盖为产品令牌 + color 域检索到的 Arcade & Retro Game（dark + score green）结构：

| Role | Hex | Note |
|------|-----|------|
| Primary | `#2E7D32` | 深绿按钮，白字对比达标 |
| On Primary | `#FFFFFF` | |
| Secondary | `#55FF55` | Minecraft §a |
| Accent/CTA | `#FFAA00` | Minecraft §6 金，深色字 |
| On Accent | `#1A1200` | |
| Background | `#07110A` | 草方块夜色，非紫底 |
| Foreground | `#F4F7F2` | |
| Card | `#122016` | |
| Muted Foreground | `#C5D4C4` | 深底正文对比 ≥ 4.5:1 |
| Border | `#2F5A28` | |
| Destructive | `#FF5555` | |
| Ring | `#55FF55` | |

### Component Overrides

- 按钮使用 Minecraft 倒角斜切（inset highlight / shadow），不要 Master 的 8px 通用圆角 pill
- 卡片使用木板抽屉斜切边，而不是 12px 玻璃圆角
- 禁止伪造评分、用户数、评价轮播（无已验证证言）
- 社交证明改为可核验能力清单：Java 8/17/21、四加载器、整合包格式、镜像源
- CTA：Hero + 功能区后 + 页底；主 CTA 为 Windows 下载
- 动效：短标题字符错落 + 功能卡 ScrollTrigger stagger；最多 1 个 pin；尊重 `prefers-reduced-motion`
- 图标：Phosphor 线框 SVG，禁止 emoji 图标

---

## Page-Specific Components

- 等距草方块 3D（CSS 六面体 + 像素纹理）
- 六主题实时切换（草方块 / 末地 / 下界 / 深海 / 暮色森林 / 樱花林）
- 启动器窗口 CSS 模型（无边框顶栏 + 启动 CTA + 底栏三页）
- 粒子层（经验球 / 萤火虫 / 尘埃），主题变色

---

## Recommendations

- Effects: 等距方块、多层视差、粒子、滚动揭示。避免无内容的纯静态海报。
- 不使用未验证的评价轮播。
