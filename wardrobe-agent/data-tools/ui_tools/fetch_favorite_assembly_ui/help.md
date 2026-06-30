# 收藏组合柜模型 → 参数化组合柜（Flask UI）

本地三栏网页：用 `login/status.json` 中的登录态拉取酷家乐收藏夹 → 选商品 → 导出 `abd.json`、封面图、`parammodel_param_list.json`、`assembly.json`，并可一键写入智能体工作区。

**启动（工作目录为 `data-tools`，不是仓库根目录）：**

```powershell
cd F:\code\wardrobe-agent\data-tools
python ui_tools/fetch_favorite_assembly_ui/app.py
```

可选参数：

```powershell
python ui_tools/fetch_favorite_assembly_ui/app.py --port 8765
python ui_tools/fetch_favorite_assembly_ui/app.py --no-browser
```

终端会打印实际 URL（端口可能自动分配）。页面打开后左侧为 **登录与目录**，中间为 **商品**，右侧为 **导出与拷贝到智能体**。

---

## 前置：Python 依赖与 Chromium

均在 **`data-tools`** 目录执行：

```powershell
cd F:\code\wardrobe-agent\data-tools
pip install -r requirements.txt
```

`requirements.txt` 已包含 **playwright** Python 包，一般**不必**再单独 `pip install playwright`。

浏览器登录还需要 **Chromium 二进制**。国内推荐（避免 `playwright install chromium` 的 `builds/cft/` 404）：

```powershell
.\scripts\install_playwright_browsers_cn.ps1
```

脚本只下载浏览器到 `%USERPROFILE%\AppData\Local\ms-playwright`；输出全是 `[skip]` 表示已装好。勿设置 `PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST`。

海外或网络正常时可选：`playwright install chromium`（仍在 `data-tools` 目录）。

---

## 1. 更新登录态（推荐：浏览器登录）

### 界面操作

1. 点击 **「打开浏览器登录」**（其下方有登录说明）。

2. 在弹出的 **Chromium** 中自行输入账号密码（脚本不保存密码）→ 进入云图并打开方案 → 标签页标题出现 **「[已登录] 请关闭此窗口…」** → **关闭整个 Chromium 窗口**（关窗后才写入 `status.json`）。

3. 回到 UI，状态应提示已更新 → 点击 **「加载收藏夹目录」** 验证。

鉴权仅使用 `login/status.json` 里的 **Cookie**（含 `qunhe-jwt`），与浏览器请求一致；界面**无** Authorization Bearer 选项。

### 备选：手动更新 status.json

云图 F12 → Network → 查看 `favorite_folder` 等请求头 → 提取 Cookie → 手动写入 `utils/login/status.json`：

```json
{
  "cookie": "从浏览器复制的 Cookie 字符串",
  "referer": "https://yun-beta.kujiale.com/cloud/tool/h5/bim",
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "updatedAt": 1234567890.123
}
```

### 安全提示

`login/status.json` 含登录态，**勿提交 git、勿外传**；建议每人本机一份或放在个人目录。

### 排查

- 终端日志：`[browser_login]`、`[ffa_ui]`
- JWT 过期会导致 401，需重新浏览器登录或更新 `status.json`
- 若关窗后 UI 无反应：确认已重启过 Flask，且是在标题出现「已登录」之后再关窗

**「无法自动检测加密格式」**（点「加载收藏夹目录」时）：

- 表示 HTTP 已成功，但响应体不是预期的 H5 三层密文（Vigenère → Base64 → GZIP），`crypt_h5.auto_decrypt` 无法识别。
- 常见原因：
  1. **接口已直接返回明文 JSON**（以 `{` 开头）——新版 `fetch_common` 会自动当明文处理；若仍报错请看下一条。
  2. **返回 HTML 登录页/错误页**（鉴权或 Referer/URL 不对）——需重新浏览器登录或从云图请求头里更新 Cookie。
  3. **响应为空或非文本**（网关异常）——看 Flask 终端或命令行加 `--raw-response` 保存原始字节。
- 命令行复现（在 `data-tools` 目录）：

  ```powershell
  python utils/fetch_favorite_assembly/fetch_favorite_folder.py --raw-response tmp_fav_raw.bin
  ```

  看终端 HTTP 状态、Content-Type，并用编辑器查看 `tmp_fav_raw.bin` 开头是 `{`、密文字符串还是 `<html`。

### 调试

本机已装好时，无需卸载，可查看错误文案排版：

- **API**：
  - `/api/browser-login/check` - 检查登录状态文件是否存在以及 cookie 是否过期

默认 URL **不显示** 调试区块。

未安装 Python 包时，页面会提示在 `data-tools` 目录任选：

- 方式 A（推荐）：`pip install -r requirements.txt`
- 方式 B：`pip install playwright`

---

## 2. 浏览收藏并导出

1. **加载收藏夹目录** → 点击某个 folder  
2. 在中间栏点击商品 → 右侧自动导出并展示  
3. 导出目录示例：  
   `data-tools\ui_tools\fetch_favorite_assembly_ui\exports\folder_106528057_bg_587306256\`

**拷贝到智能体**（需先完成导出）：

- 清空 `workspace/tmp`
- `abd.json`、封面 → `workspace/tmp/input/`
- 备份并替换 `workspace/data/param-model-library/parammodel_param_list.json`

**恢复智能体模型库设置**：用该导出目录下的 `parammodel_param_list_backup.json` 还原 workspace 内模型库列表（须先执行过「拷贝到智能体」才会生成备份）。

---

## 3. 在智能体中建模

将 `abd.json`、`cover.png`（如有）放到 `workspace/tmp/input/`，`parammodel_param_list.json` 已覆盖到 `workspace/data/param-model-library/` 后，在 Cursor 中按建模流程操作。

---
