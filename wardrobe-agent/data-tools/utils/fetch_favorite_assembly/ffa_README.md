# fetch_favorite_assembly

说明文档文件名为 **[ffa_README.md](ffa_README.md)**（原名 `fetch_favorite_assembly_README.md`）。

本目录工具用于在浏览器已登录酷家乐云环境的前提下，从 **`data-tools/utils/login/status.json`** 读取 Cookie / 请求头，**拉取收藏夹相关 H5 接口**的响应体，并用 **`crypt_h5`** 按与前端一致的链路解密（Vigenère 变种 → Base64 → 可选 GZIP），得到明文 JSON。另可用 **`fetch_assembly.py`** 按 **`bgId`** 请求 **assemblyattach**（请求体为 **`crypt_zstd`** 压缩的 JSON，响应多为 Zstd 再 Base64），拉取单商品的装配/参数详情。

另含 **`crypt_zstd.py`**：处理 ParamModel V7 请求体一类 **Base64 ↔ Zstd ↔ UTF‑8 JSON**（与 TS 侧 `decryptRequestBody` / `prepareRequestData` 对齐；口语里的「加解密」实为压缩与 Base64，不含对称密钥加密）。用法与参数见下文 [crypt_zstd 命令行](#crypt-zstd-cli)。

## 前置条件

- **Python 3**（脚本使用标准库 + 同目录模块；无额外安装即可跑通不含 Zstd 的 `fetch_*.py` 与 `crypt_h5.py`。使用 **`crypt_zstd.py`** 或 **`fetch_assembly.py`** 时需安装 **`zstandard`**。）
- 先通过登录工具刷新 **`data-tools/utils/login/status.json`**；脚本默认从该文件读取登录态，也可通过 `--status-file` 指定其它路径。

## 可选依赖（`crypt_zstd.py` / `fetch_assembly.py`）

**只使用本目录工具**时，安装同目录 [requirements.txt](requirements.txt)（目前仅 **`zstandard`**）：

```bash
pip install -r requirements.txt
```

若需与 **`data-tools`** 下其它脚本（Flask UI、`requests` 等）共用同一环境，请在 **`data-tools`** 目录执行：

```bash
pip install -r requirements.txt
```

或在仓库根目录：

```bash
pip install -r data-tools/requirements.txt
```

也可单独 `pip install zstandard`。

## 脚本概览

| 脚本 | 作用 |
|------|------|
| [fetch_favorite_folder.py](fetch_favorite_folder.py) | 使用 `status.json` 请求 **favorite_folder**（GET），解密响应体 |
| [fetch_bg_collections.py](fetch_bg_collections.py) | 使用 `status.json` 中的鉴权信息，**构造** `bgcollections/v2` 查询 URL，按 `folder_id` 拉取列表并解密 |
| [fetch_assembly.py](fetch_assembly.py) | 按 **`bgId`** POST **`…/assemblyattach/zstd`**，请求体为 `crypt_zstd` 加密的 JSON（`useLatestReleaseAllLevel`、`zstdWithBase64` 等与前端一致）；响应优先按 Zstd 解密，失败再走 H5 解密 |
| [fetch_common.py](fetch_common.py) | 补全/修正请求头、`urllib` 发起请求（含可选 **POST body**）、**`decrypt_response_body`**（优先 `full_decrypt`，失败则 `auto_decrypt`） |
| [crypt_h5.py](crypt_h5.py) | H5 响应 / 样本的离线加解密 CLI（与 `decrypt.js` / Vigenère 密钥一致） |
| [crypt_zstd.py](crypt_zstd.py) | ParamModel body 的 Zstd + Base64 CLI（子命令：`decrypt` / `encrypt` / `self-test`） |

## 示例：favorite_folder

确保 `status.json` 已刷新，然后：

```bash
python fetch_favorite_folder.py -o favorite_folder.json
```

**不落盘、直接打印到标准输出：**

```bash
python fetch_favorite_folder.py
```

**同时保存上游原始响应字节（调试）：**

```bash
python fetch_favorite_folder.py --raw-response raw_body.bin -o out.json
```

## 示例：bgcollections/v2

按收藏夹文件夹 ID 请求列表（分页等参数见下表）：

```bash
python fetch_bg_collections.py 12345678 -o bg_collections.json
```

**调试鉴权 / 网关 401 时** 可尝试与脚本说明一致的选项（例如覆盖 Referer、或 `--jwt-bearer`）。详见下方参数说明。

## 示例：assemblyattach（`fetch_assembly.py`）

需已安装 **`zstandard`**（见上文可选依赖）。脚本内置固定接口地址与查询参数（与浏览器侧 **custom-model-task** 的 `assemblyattach/zstd` 一致），**不读取**实现时参考用的 `fetch_attach.txt`。

```bash
python fetch_assembly.py 601268768 -o assembly.json
```

不落盘时输出到标准输出；调试可加 `--raw-response resp.bin` 保存原始响应字节。

## 示例：离线处理密文（`crypt_h5.py`）

**完整解密（Vigenère → Base64 → GZIP → JSON）：**

```bash
python crypt_h5.py --all -i test_data/bg_collections_h5_encrypt.txt -o plain.json
```

**从标准输入读入密文：**

```bash
type test_data\bg_collections_h5_encrypt.txt | python crypt_h5.py --all -i -
```

**仅做 Zstd + Base64 链路（与 H5 Vigenère 无关）** 请用 [下文 `crypt_zstd.py` 示例](#crypt-zstd-cli)。

<a id="crypt-zstd-cli"></a>

## 示例：`crypt_zstd.py`（ParamModel body）

（参数与选项见 [参数说明 · `crypt_zstd.py`](#params-crypt-zstd)。）

**解压 `test_data` 中的 base64 样本，得到紧凑 JSON 原文：**

```bash
python crypt_zstd.py decrypt \
  -i test_data/assembly_attach_payload_zstd_encrypt.txt \
  -o payload.json
```

**同上，但输出带缩进（便于阅读）：**

```bash
python crypt_zstd.py decrypt \
  -i test_data/assembly_attach_payload_zstd_encrypt.txt \
  -o payload.pretty.json \
  --pretty
```

**从标准输入读 base64，写出到标准输出：**

```bash
type test_data\assembly_attach_payload_zstd_encrypt.txt | python crypt_zstd.py decrypt -i - -o -
```

**将 JSON 文件压成与 TS 默认一致的 body（level=1）并输出 base64：**

```bash
python crypt_zstd.py encrypt \
  -i payload.json \
  -o body.b64.txt \
  --newline \
  --validate-json
```

**运行内置测试（默认扫描脚本同级的 `test_data/`）：**

```bash
python crypt_zstd.py self-test
```

指定其它测试根目录：

```bash
python crypt_zstd.py self-test --test-root path/to/cases
```

## 参数说明

### `fetch_favorite_folder.py`

- **`--status-file`**：登录状态 JSON 路径，默认 **`data-tools/utils/login/status.json`**。
- **`--foldertype`**：文件夹类型，默认 **`4`**。
- **`--timeout`**：请求超时秒数，默认 `60`。
- **`-o` / `--output`**：解密后 UTF‑8 JSON 输出路径；省略则写入 **标准输出**。
- **`--raw-response`**：同时将原始响应体写入指定路径（调试）。

### `fetch_bg_collections.py`

- **`folder_id`**（位置参数）：对应接口查询参数 **`folderid`**。
- **`--num`** / **`--start`**：分页，`num` 默认 `40`，`start` 默认 `0`。
- **`--foldertype`**：文件夹类型，默认 **`4`**（与常见示例一致）。
- **`--status-file`**：登录状态 JSON 路径，默认 **`data-tools/utils/login/status.json`**。
- **`--timeout`**：同上。
- **`-o` / `--output`**：解密后 JSON 路径；省略则 **标准输出**。
- **`--raw-response`**：保存原始响应体。
- **`--referer` / `--origin`**：强制 Referer、Origin（默认脚本会按场景补全，避免 dcs-search 与 dcscms 上下文不一致导致 **401**）。
- **`--no-header-fix`**：不调整 Referer / Origin / Sec-Fetch-*（仅调试；易出现鉴权失败）。
- **`--jwt-bearer`**：将 Cookie 中的 **`qunhe-jwt`** 同时写入 **`Authorization: Bearer`**（默认不加，与典型浏览器 fetch 一致）。

### `fetch_assembly.py`

- **`bg_id`**（位置参数）：写入请求 JSON 的 **`bgId`** 整数。
- **`--status-file`**：登录状态 JSON 路径，默认 **`data-tools/utils/login/status.json`**。
- **`--timeout`**：请求超时秒数，默认 `60`。
- **`-o` / `--output`**：解密后的 UTF‑8 JSON 路径；省略则 **标准输出**。
- **`--raw-response`**：保存原始响应体（调试）。
- **`-l` / `--level`**：请求体 Zstd 压缩等级，默认 **`1`**（与 `crypt_zstd` / TS 默认一致）。
- **`--referer` / `--origin`**、**`--no-header-fix`**、**`--jwt-bearer`**：含义与 **`fetch_bg_collections.py`** 相同（复用 **`prepare_bgcollections_headers`**）。

请求 JSON 为紧凑 UTF‑8：`bgId`、`useLatestReleaseAllLevel: true`、`needResource: false`、`zstdWithBase64: true`。脚本会设置 **`Content-Type: application/zstd`**、**`x-raw-data-length`**（明文 JSON 字节长度）及与浏览器一致的若干业务头。

### `crypt_h5.py`

- **`-i` / `--input`**：输入文件，或 **`-`** 表示从 **标准输入**读取；也可在省略 `-i` 时用**位置参数**传入整段字符串。
- **`-o` / `--output`**：结果写入文件；省略则标准输出。
- 模式互斥其一：**`--all`**、**`--all-no-gzip`**、**`--gunzip`**、**`--vigenere`**、**`--auto`**（未指定时默认自动检测）、**`--encrypt`**、**`--encrypt-all`**、**`--encrypt-all-no-gzip`**。完整说明见 `python crypt_h5.py -h`。

<a id="params-crypt-zstd"></a>

### `crypt_zstd.py`

**子命令概览：**

| 子命令 | 别名 | 作用 |
|--------|------|------|
| `decrypt` | `decode`, `d` | Base64 解码 → Zstd 解压 → 输出原始 UTF‑8（可选美化 JSON） |
| `encrypt` | `encode`, `e` | 读入 UTF‑8 JSON → Zstd 压缩（默认 level=1）→ Base64 一行 |
| `self-test` | — | 扫描目录下成对测试文件并校验 |

#### `decrypt`

- **`-i` / `--input`**：输入文件路径；`-` 表示从标准输入读取整段 base64 文本（默认 `-`）。
- **`-o` / `--output`**：输出路径；`-` 表示标准输出（二进制 UTF‑8）。
- **`--pretty`**：若内容为 JSON，则 `json.loads` 后以缩进 2 空格、`ensure_ascii=False` 再写出。
- **`--max-output-size`**：解压结果最大字节数（默认 512 MiB），用于防止异常膨胀。

#### `encrypt`

- **`-i` / `--input`**：JSON 文件或 `-`（stdin，按字节读取）。
- **`-o` / `--output`**：base64 文本输出路径或 `-`。
- **`-l` / `--level`**：Zstd 压缩等级，默认 **1**（与 `index.ts` 中 `prepareRequestData` 一致）。
- **`--validate-json`**：压缩前强制 `json.loads`，非法 JSON 则报错退出。
- **`--newline`**：输出末尾追加换行符。

#### `self-test`

- **`--test-root`**：包含成对文件的目录，默认 `crypt_zstd.py` 所在目录下的 `test_data`。
- **`--max-output-size`**：同 `decrypt`，用于每组的解压上限。

**测试文件命名约定**（与 [「`test_data` 约定」](#test-data-convention) 一节一致）：

- `某个前缀_zstd_encrypt.txt`：整段 Base64（Zstd 帧再 base64）。
- `某个前缀_zstd_decrypt.txt`：解压并 `json.loads` 后应与加密侧 **JSON 语义完全一致**（允许空白、键顺序等排版差异；脚本用对象/数组深度比较）。

对每一组会校验：① 解密结果与参照 JSON **相等**；② 将解密得到的对象用紧凑 JSON 再 **encode → decode** 后对象仍一致。

#### 与 Node / `zstd-codec` 的差异

Python `zstandard` 生成的 Zstd **帧字节**可能与 Node 侧 `zstd-codec` **不完全相同**，但通常可与服务端及 TS 客户端 **互相解压**。若需与抓包字节级一致，应用同一实现（例如仍在 Node 中处理）。

<a id="test-data-convention"></a>

## `test_data` 约定

| 前缀 / 模式 | 含义 |
|-------------|------|
| `*_h5_encrypt.txt` / `*_vigenere_encrypt.txt` | H5 侧密文样本，供 **`crypt_h5`** 解密对照 |
| `*_h5_decrypt.txt` 等 | 对应明文或解密参照 |
| `*_zstd_encrypt.txt` | Base64（Zstd 帧），供 **`crypt_zstd`** |
| `*_zstd_decrypt.txt` | 与加密侧 JSON **语义一致**的参照（`self-test` 深度比较） |

## 解密策略（`fetch_common.decrypt_response_body`）

适用于 **`fetch_favorite_folder`**、**`fetch_bg_collections`** 等仅依赖 `fetch_common` 默认解密的脚本：

1. 响应体按声明 charset 或 UTF‑8 解码为文本；
2. 优先 **`crypt_h5.full_decrypt`**（与 CLI **`--all`** 一致的三层包）；
3. 若失败则 **`crypt_h5.auto_decrypt`**（自动识别多种形态）。

**`fetch_assembly.py`** 另有一套顺序：若响应已为明文 JSON（以 **`{`** / **`[`** 开头）则直接使用；否则 **先尝试** **`crypt_zstd.decrypt_body_base64`**（Base64 → Zstd → UTF‑8），失败再调用上面的 **`decrypt_response_body`**。

## 安全提示

- `status.json` 含 **Cookie / 可能含 JWT**，仅限本机调试使用，勿入版本库、勿外传。
- 401、空响应体多与 **token 过期** 或 **Referer/Origin 与接口域不匹配** 有关；按脚本 stderr 提示刷新登录状态或调整参数。

## 相关文件

- H5 加解密实现：[crypt_h5.py](crypt_h5.py)
- 依赖清单（本目录）：[requirements.txt](requirements.txt)
- 依赖清单（整个 data-tools）：[data-tools/requirements.txt](../../requirements.txt)
- Zstd CLI：[crypt_zstd.py](crypt_zstd.py)
- 按 bgId 拉 assemblyattach：[fetch_assembly.py](fetch_assembly.py)
- 本说明：[ffa_README.md](ffa_README.md)
