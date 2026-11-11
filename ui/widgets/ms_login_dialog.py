"""内嵌浏览器微软登录 — 自动拦截授权回调，用户零操作。"""

from urllib.parse import urlparse, parse_qs

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView


def _url_base(url_str: str) -> tuple:
    """取 URL 的 (scheme, netloc, path)，用于与 redirect_uri 做精确比对。

    只比基地址，忽略查询串/片段——授权码和 state 都在查询串里。
    """
    try:
        u = urlparse(url_str)
        return (u.scheme.lower(), u.netloc.lower(), u.path or "/")
    except Exception:
        return ("", "", "")


class MsLoginDialog(QDialog):
    """内嵌浏览器微软登录窗口。

    打开后自动导航到微软登录页，用户正常登录。
    登录完成后微软重定向到 redirect_uri?code=XXX&state=YYY，
    本窗口校验基地址、授权码与 state 后自动提取 code，
    通过 code_received 信号返回。
    """
    code_received = pyqtSignal(str)

    def __init__(self, login_url: str, redirect_uri: str, state: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("微软账号登录")
        self.setMinimumSize(520, 680)
        self.resize(520, 680)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._redirect = redirect_uri
        self._redirect_base = _url_base(redirect_uri)
        self._state = (state or "").strip()
        self._code = ""
        # 收到过形似回调、但 state/code 校验不通过的 URL
        self.invalid_callback_seen = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hint = QLabel("  在下方完成微软账号登录，登录后将自动返回启动器")
        hint.setFixedHeight(28)
        hint.setObjectName("statusLabel")
        lay.addWidget(hint)

        self._browser = QWebEngineView()
        self._browser.urlChanged.connect(self._on_url)
        lay.addWidget(self._browser, 1)

        self._browser.load(QUrl(login_url))

    def _on_url(self, url: QUrl):
        """每次浏览器 URL 变化时检查是否为合法回调。"""
        try:
            url_str = url.toString()
        except Exception:
            return
        if not url_str:
            return

        # 1) 基地址必须就是 redirect_uri（scheme + host + path），
        #    否则任何带 ?code= 的子串页面都能骗过判定。
        if _url_base(url_str) != self._redirect_base:
            return

        _base, _sep, query = url_str.partition("?")
        try:
            params = parse_qs(query, keep_blank_values=True)
        except Exception:
            self.invalid_callback_seen = True
            return

        # 2) 授权码必须非空
        code = (params.get("code", [""])[0] or "").strip()
        if not code:
            if params.get("error"):
                # 用户在微软页面取消授权：正常流程的失败分支
                self.reject()
            else:
                # 缺 code：忽略这次跳转，不打断用户继续登录
                self.invalid_callback_seen = True
            return

        # 3) state 必须完全相等（防 CSRF / 授权码注入）
        if self._state:
            got_state = (params.get("state", [""])[0] or "").strip()
            if got_state != self._state:
                self.invalid_callback_seen = True
                return

        self._code = code
        self.code_received.emit(code)
        self.accept()

    def get_code(self) -> str:
        return self._code

    def get_state(self) -> str:
        return self._state
