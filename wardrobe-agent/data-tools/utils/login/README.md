# 登录模块

本模块提供统一的登录状态管理和浏览器登录功能。

## 模块结构

```
login/
├── __init__.py              # 模块入口，导出所有公共接口
├── status_manager.py        # 登录状态管理（读取、检查、写入 status.json）
├── browser_login.py         # 浏览器登录功能
└── status.json              # 登录状态文件（运行时生成）
```

## 主要功能

### 1. 登录状态管理 (status_manager.py)

提供以下功能：

- **读取登录状态**：从 `status.json` 加载登录信息
- **检查登录状态**：检查 Cookie 是否过期
- **写入登录状态**：保存登录信息到 `status.json`
- **准备请求头**：使用 Cookie 准备认证请求头

#### 主要函数

```python
from login import (
    load_status,              # 加载登录状态
    get_cookie,               # 获取 Cookie
    check_login_status,       # 检查登录状态
    is_cookie_expired,        # 检查 Cookie 是否过期
    save_status,              # 保存登录状态
    prepare_headers_from_status,  # 从 status.json 准备请求头
    prepare_headers_with_cookie,  # 使用 Cookie 准备请求头
)
```

#### 使用示例

```python
from login import check_login_status, get_cookie, prepare_headers_from_status

# 检查登录状态
status = check_login_status()
if status["ok"]:
    print("登录状态有效")
else:
    print(f"登录状态无效: {status['message']}")

# 获取 Cookie
cookie = get_cookie()

# 准备请求头
headers = prepare_headers_from_status()
```

### 2. 浏览器登录 (browser_login.py)

提供通过 Playwright 打开浏览器进行手动登录的功能。

#### 主要函数

```python
from login import refresh_status_via_browser

# 打开浏览器登录
result = refresh_status_via_browser(
    status_file=None,  # 默认为 utils/login/status.json
    login_url="https://yun.kujiale.com/cloud/tool/h5/bim",
    wait_timeout_s=600.0,
    poll_interval_s=1.5,
)
```

#### 使用示例

```python
from login import refresh_status_via_browser

try:
    result = refresh_status_via_browser()
    print(f"登录成功: {result['message']}")
except Exception as e:
    print(f"登录失败: {e}")
```

## status.json 格式

```json
{
  "cookie": "qunhe-jwt=xxx; other_cookie=yyy",
  "referer": "https://yun-beta.kujiale.com/cloud/tool/h5/bim",
  "userAgent": "Mozilla/5.0 ...",
  "updatedAt": 1234567890.123
}
```

## 命令行（agent / 脚本）

在 `data-tools/` 目录下：

```bash
# 检查登录（stdout JSON，退出码 0=有效）
python utils/login/browser_login.py check

# 浏览器登录（阻塞至用户关窗或超时）
python utils/login/browser_login.py login --wait-timeout 600
```

可选 `--status-file` 指定非默认的 `status.json` 路径。

## 在其他模块中使用

### 在 Flask 应用中使用

```python
from login import check_login_status, get_cookie, is_cookie_expired, prepare_headers_with_cookie

@app.route("/api/check-login")
def check_login():
    status = check_login_status()
    return jsonify(status)

@app.route("/api/data")
def get_data():
    cookie = get_cookie()
    if is_cookie_expired(cookie):
        return jsonify({"error": "登录已过期"}), 401
    
    headers = prepare_headers_with_cookie(cookie)
    # 使用 headers 发起请求
    ...
```

### 在脚本中使用

```python
from login import get_cookie, prepare_headers_from_status

# 获取 Cookie 并准备请求头
headers = prepare_headers_from_status()

# 发起 API 请求
response = requests.get("https://api.example.com/data", headers=headers)
```

## 注意事项

1. **Cookie 过期检查**：模块会自动检查 JWT Cookie 的 `exp` 字段来判断是否过期
2. **浏览器登录**：需要安装 Playwright：`pip install playwright && playwright install chromium`
3. **状态文件路径**：默认使用 `utils/login/status.json`，可以通过参数指定其他路径

## 迁移指南

如果你之前使用的是分散的登录相关代码，可以按以下方式迁移：

### 之前

```python
# 手动读取 status.json
import json
status_file = Path("utils/login/status.json")
data = json.loads(status_file.read_text())
cookie = data["cookie"]

# 手动检查过期
# ... 复杂的 JWT 解析代码 ...
```

### 之后

```python
# 使用统一的登录模块
from login import get_cookie, is_cookie_expired

cookie = get_cookie()
if is_cookie_expired(cookie):
    # 处理过期
    pass
```

## API 参考

### check_login_status(status_file=None)

检查登录状态。

**参数：**
- `status_file` (Path, optional): 登录状态文件路径

**返回：**
```python
{
    "ok": bool,           # 登录状态是否有效
    "expired": bool,      # 是否已过期
    "message": str        # 状态描述（英文）
}
```

### get_cookie(status_file=None)

从 status.json 获取 Cookie 请求头。

**参数：**
- `status_file` (Path, optional): 登录状态文件路径

**返回：**
- `str`: Cookie 请求头字符串

### is_cookie_expired(cookie_header)

检查 Cookie 中的 JWT 是否已过期。

**参数：**
- `cookie_header` (str): Cookie 请求头字符串

**返回：**
- `bool`: True 表示已过期或无法判断，False 表示未过期

### save_status(cookie_header, referer, user_agent, status_file=None)

保存登录状态到 status.json。

**参数：**
- `cookie_header` (str): Cookie 请求头字符串
- `referer` (str): Referer 请求头
- `user_agent` (str): User-Agent 请求头
- `status_file` (Path, optional): 登录状态文件路径

### prepare_headers_from_status(status_file=None)

从 status.json 读取登录状态并准备请求头。

**参数：**
- `status_file` (Path, optional): 登录状态文件路径

**返回：**
- `dict[str, str]`: 包含请求头的字典

### prepare_headers_with_cookie(cookie_header, referer=None, user_agent=None)

使用 cookie 准备请求头。

**参数：**
- `cookie_header` (str): Cookie 请求头字符串
- `referer` (str, optional): Referer 请求头
- `user_agent` (str, optional): User-Agent 请求头

**返回：**
- `dict[str, str]`: 包含请求头的字典

### refresh_status_via_browser(status_file=None, *, login_url=..., wait_timeout_s=600.0, poll_interval_s=1.5)

打开 Chromium（有界面），等待用户手动登录，检测到 JWT Cookie 后写入 status.json。

**参数：**
- `status_file` (Path, optional): 登录状态文件路径
- `login_url` (str): 登录页面 URL
- `wait_timeout_s` (float): 等待登录超时时间（秒）
- `poll_interval_s` (float): 轮询 Cookie 间隔（秒）

**返回：**
```python
{
    "statusPath": str,      # 状态文件路径
    "elapsedSeconds": float, # 用时（秒）
    "referer": str,         # Referer
    "loginUrl": str,        # 登录 URL
    "message": str          # 操作消息
}
```

**异常：**
- `RuntimeError`: 未安装 playwright 或登录失败
- `TimeoutError`: 超时未完成登录