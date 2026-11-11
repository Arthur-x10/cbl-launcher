"""首次启动服务授权协议弹窗 — 用户必须同意后才能使用启动器。"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QTextBrowser, QTabWidget, QWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt


# ═══════════════════ 条款内容 ═══════════════════

TERMS_OF_USE = """
<h2>用户使用条款</h2>
<p><i>生效日期：2026 年 10 月 23 日　　版本：1.0</i></p>

<h3>一、性质与定位</h3>
<p>CBL Cube Launcher（以下简称"本软件"）是一款开源的本地 Minecraft: Java Edition 启动辅助工具，
用于帮助用户管理本地游戏版本、配置 Java 运行环境及启动已安装的游戏客户端。</p>
<p>本软件与 Mojang Studios、Microsoft Corporation、网易公司（NetEase）及其各自的关联方
<b>不存在任何授权、代理、合作或隶属关系</b>。"Minecraft"为 Mojang Studios 的注册商标。</p>

<h3>二、合法使用前提</h3>
<p>使用本软件前，您应当确认：</p>
<ol>
<li>您已通过合法渠道获得 Minecraft: Java Edition 的使用许可（即拥有有效的正版账号）；</li>
<li>您已阅读并同意 Mojang Studios《最终用户许可协议》(EULA) 及《商业使用准则》；</li>
<li>您将遵守您所在国家或地区适用的法律法规。</li>
</ol>

<h3>三、离线模式</h3>
<p>本软件提供的离线模式功能仅供用户在已拥有正版许可的前提下，于无网络环境中进行本地测试。
该功能不得用于规避 Mojang 正版身份验证或协助未经授权的访问。
用户因使用离线模式所产生的法律责任由其自行承担。</p>

<h3>四、游戏文件获取</h3>
<p>本软件所涉及的 Minecraft 游戏本体文件（客户端 JAR、资源文件、库文件等）
均由用户的设备直接从 Mojang / Microsoft 官方服务器下载，本软件不自行托管、
缓存或再分发任何游戏本体文件。</p>

<h3>五、第三方内容</h3>
<p>本软件支持安装 Forge、Fabric、Quilt、NeoForge 等由各自社区独立维护的第三方模组加载器。
这些加载器及通过它们加载的第三方模组（Mod）、资源包、光影包等内容：</p>
<ul>
<li>由各自的作者或组织独立开发和发布，与本软件无关；</li>
<li>可能包含本软件无法审查的代码或内容；</li>
<li>其安全性、稳定性、兼容性及合法性由用户自行判断。</li>
</ul>
<p><b>本软件不对任何第三方内容做出推荐、背书或担保。</b></p>

<h3>六、第三方服务器</h3>
<p>用户通过本软件启动游戏后连接的多人游戏服务器（包括但不限于私人服务器、公共服务器），
均由该服务器的运营方独立运营和管理。</p>
<ul>
<li>本软件不运营、不推荐、不索引任何游戏服务器；</li>
<li>用户在第三方服务器上的行为（包括但不限于聊天、交易、充值、付费）
由用户与该服务器运营方之间的约定约束；</li>
<li>因第三方服务器引起的任何纠纷、财产损失或其他后果，与本软件无关。</li>
</ul>

<h3>七、修改与再分发</h3>
<p>本软件以开源形式提供。用户或第三方对本软件进行修改、衍生或再分发时，
应遵守适用的开源许可协议，且修改版本的行为和后果由修改者自行负责。
<b>本软件的原始开发者不对任何修改版本或衍生版本承担责任。</b></p>

<h3>八、禁止行为</h3>
<p>用户不得利用本软件从事以下行为：</p>
<ol>
<li>规避正版验证，协助盗版传播；</li>
<li>制作、传播含有恶意代码的修改版本；</li>
<li>利用本软件实施违反法律法规的活动；</li>
<li>诱导未成年人进行非理性消费或参与不适宜的活动。</li>
</ol>

<h3>九、未成年人使用</h3>
<p>如用户为未满 18 周岁的未成年人，应在监护人知情同意的前提下使用本软件。
监护人有责任对未成年人的使用行为进行监督和指导。</p>

<h3>十、条款修订</h3>
<p>本条款可能根据法律法规或功能变化进行更新。更新后的版本将在软件内展示，
继续使用本软件即视为接受修订后的条款。</p>
"""

PRIVACY_POLICY = """
<h2>用户隐私条款</h2>
<p><i>生效日期：2026 年 10 月 23 日　　版本：1.0</i></p>

<h3>一、基本原则</h3>
<p>本软件遵循最小化数据收集原则。全部用户数据仅存储于用户本地设备，
不上传至任何远程服务器，不经本软件传递至任何第三方。</p>

<h3>二、本地存储信息</h3>
<p>本软件在运行过程中会在其安装目录下生成并读写以下文件：</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; border-color:#444;">
<tr><td><b>文件</b></td><td><b>内容</b></td></tr>
<tr><td>config.json</td><td>Java 路径、内存设置、JVM 参数、游戏目录、
微软登录凭证（OAuth 访问令牌与刷新令牌）、界面偏好</td></tr>
<tr><td>.minecraft/</td><td>游戏版本文件、库文件、资源文件、
模组加载器、游戏存档、Mod 文件等</td></tr>
</table>
<p>上述文件均位于本软件所在目录内，不写入系统注册表或其他系统目录。</p>

<h3>三、网络通信</h3>
<p>本软件在以下场景中发起网络请求：</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; border-color:#444;">
<tr><td><b>目的</b></td><td><b>目标服务器</b></td></tr>
<tr><td>微软 / Minecraft 账号验证</td><td>login.live.com / login.microsoftonline.com</td></tr>
<tr><td>下载游戏本体文件</td><td>launchermeta.mojang.com / piston-data.mojang.com 等</td></tr>
<tr><td>下载 Java 运行时</td><td>launchermeta.mojang.com</td></tr>
<tr><td>下载 Forge / Fabric / Quilt / NeoForge</td><td>各加载器官方服务器</td></tr>
<tr><td>获取玩家皮肤头像（可选）</td><td>crafatar.com</td></tr>
</table>
<p>本软件不包含任何数据分析、用户行为追踪或广告 SDK。</p>

<h3>四、账号凭证安全</h3>
<p>微软登录采用 OAuth 2.0 标准协议（PKCE 模式），本软件<b>不接触、不存储用户的微软账号密码</b>。
访问令牌以明文形式保存于本地 config.json 文件中。用户应当：</p>
<ul>
<li>妥善保管 config.json 文件，避免与他人共享；</li>
<li>不要将启动器目录上传至公开的代码仓库或网盘。</li>
</ul>

<h3>五、第三方服务的隐私政策</h3>
<p>用户通过本软件安装的第三方模组、加载器或连接的第三方游戏服务器，
可能有各自独立的数据收集与隐私政策。本软件无法控制或审查第三方的数据行为，
用户应自行查阅相关方的隐私条款。</p>

<h3>六、未成年人隐私</h3>
<p>本软件不主动收集任何用户年龄信息。如用户为未成年人，
监护人应协助其了解本隐私条款的内容，并指导其正确使用。</p>

<h3>七、数据删除</h3>
<p>删除本软件所在目录即可完全、不可恢复地清除全部本地数据。
卸载后不会在操作系统中留存任何文件或注册表项。</p>
"""

DISCLAIMER = """
<h2>免责声明</h2>
<p><i>生效日期：2026 年 10 月 23 日　　版本：1.0</i></p>

<h3>一、"按原样"提供</h3>
<p>本软件按"现状"（AS IS）和"可获得"（AS AVAILABLE）基础提供，不附带任何明示或暗示的保证，
包括但不限于适销性、特定用途适用性或不侵权的保证。</p>

<h3>二、功能可用性</h3>
<p>本软件的功能依赖于外部服务器（Mojang、Microsoft 及各加载器项目方）的正常运行。
如因上述服务器的变更、停服、访问限制或网络环境问题导致的功能不可用，
本软件的开发者不承担责任。</p>

<h3>三、第三方模组与加载器</h3>
<p>本软件提供 Forge、Fabric、Quilt、NeoForge 等第三方加载器的安装辅助功能，
并支持用户自行放置第三方模组文件。</p>
<ul>
<li><b>本软件不审查、不认证、不担保</b>任何第三方模组或加载器的安全性、
稳定性、合法性及与特定游戏版本的兼容性；</li>
<li>因第三方模组或加载器引起的游戏崩溃、存档损坏、数据丢失或安全问题，
由用户自行承担风险。</li>
</ul>

<h3>四、第三方服务器与在线交互</h3>
<p>用户使用本软件启动游戏后，自行选择连接的多人游戏服务器由其运营方独立管理。</p>
<ul>
<li>本软件不运营、不推荐、不提供任何游戏服务器列表或索引；</li>
<li>用户在第三方服务器上的任何行为（包括但不限于充值、消费、交易、社交互动）
及由此产生的纠纷或财产损失，由用户与该服务器运营方之间依据双方约定处理；</li>
<li><b>本软件的开发者不对用户在任何第三方服务器上的体验、财产安全或权益纠纷承担任何责任。</b></li>
</ul>

<h3>五、修改版本与衍生软件</h3>
<p>任何第三方对本软件进行修改、魔改、二次打包或再分发所产生的版本，
均不在本软件开发者的控制和审查范围内。</p>
<ul>
<li>用户应仅从本软件的官方发布渠道获取安装包；</li>
<li>使用来源不明的修改版可能面临恶意代码、数据窃取等安全风险；</li>
<li><b>本软件的开发者不对任何修改版本或衍生版本的行为及后果承担责任。</b></li>
</ul>

<h3>六、未成年人保护</h3>
<p>本软件是一款本地工具软件，不提供网络社交、充值付费或虚拟物品交易功能。
如用户为未成年人，监护人应当：</p>
<ul>
<li>了解未成年人使用本软件的情况及其在游戏中的在线活动；</li>
<li>引导未成年人合理安排游戏时间，避免非理性消费；</li>
<li>对未成年人连接第三方服务器的行为予以关注和监督。</li>
</ul>
<p>因监护人未尽到监护义务而产生的相关后果，本软件的开发者不承担责任。</p>

<h3>七、法律合规</h3>
<p>本软件的开发者尊重各国家和地区的法律法规。如因法律法规变更、
行政要求或司法裁定需要调整本软件的功能范围，开发者将积极配合执行。
用户如发现本软件的任何功能可能违反其所在地区的法律法规，应停止使用该功能。</p>

<h3>八、责任限制</h3>
<p>在适用法律允许的最大范围内，本软件的开发者不对因使用或无法使用本软件
而产生的任何直接、间接、附带、特殊或后果性损害承担责任，
包括但不限于利润损失、数据损失、商誉损害或业务中断。</p>

<h3>九、开源说明</h3>
<p>本软件使用了 PyQt6、minecraft-launcher-lib 等开源项目，
各项目受其自身许可协议约束。本软件对第三方开源库的使用不构成对其的修改或再发行，
除非另有说明。</p>
"""


# ═══════════════════ 协议弹窗 ═══════════════════

class AgreementDialog(QDialog):
    """首次启动协议弹窗 — 必须同意三份条款。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CBL Cube Launcher — 服务条款")
        self.setFixedSize(680, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.accepted_result = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        title = QLabel("欢迎使用 CBL Cube Launcher")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        hint = QLabel("在使用前，请仔细阅读以下条款。您需要同意全部条款才能继续。")
        hint.setObjectName("mutedLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        lay.addWidget(hint)

        tabs = QTabWidget()
        tabs.addTab(self._make_doc(TERMS_OF_USE), "用户使用条款")
        tabs.addTab(self._make_doc(PRIVACY_POLICY), "用户隐私条款")
        tabs.addTab(self._make_doc(DISCLAIMER), "免责声明")
        lay.addWidget(tabs, 1)

        self.agree_chk = QCheckBox("我已阅读并同意《用户使用条款》《用户隐私条款》和《免责声明》")
        self.agree_chk.stateChanged.connect(self._on_check)
        lay.addWidget(self.agree_chk)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.reject_btn = QPushButton("不同意，退出")
        self.reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reject_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.reject_btn)

        self.accept_btn = QPushButton("同意并继续")
        self.accept_btn.setObjectName("btnPrimary")
        self.accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self._do_accept)
        btn_row.addWidget(self.accept_btn)

        lay.addLayout(btn_row)

    def _make_doc(self, html: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            "QTextBrowser { background-color: #1A172A; color: #CCCCCC; "
            "border: none; padding: 12px; font-size: 12px; }"
        )
        lay.addWidget(browser)
        return w

    def _on_check(self, state):
        self.accept_btn.setEnabled(state == Qt.CheckState.Checked.value)

    def _do_accept(self):
        self.accepted_result = True
        self.accept()
