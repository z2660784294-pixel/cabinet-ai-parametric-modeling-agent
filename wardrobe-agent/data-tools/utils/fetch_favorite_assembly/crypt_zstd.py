#!/usr/bin/env python3
"""
ParamModel V7 请求 body 的 Zstd 编解码（与 index.ts 中逻辑对齐）。

- decrypt / decode: Base64 -> Zstd 解压 -> UTF-8 JSON
- encrypt / encode: UTF-8 JSON -> Zstd 压缩（默认 level=1）-> Base64

依赖: 本目录 pip install -r requirements.txt；完整 data-tools 见上级目录 requirements.txt

文档: 同目录 ffa_README.md 中「crypt_zstd.py」小节。

说明: Python 的 zstd 帧与 Node 版 zstd-codec 可能逐字节不同，但与服务器/TS 侧一样可互解压。
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover
    print(
        "缺少依赖：在本目录执行 pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)

# 解压体积上限（含解密后较大 JSON / 响应体）
_DEFAULT_MAX_OUT = 512 * 1024 * 1024


def decrypt_body_base64(b64_text: str, max_out: int = _DEFAULT_MAX_OUT) -> bytes:
    """对应 decryptRequestBody 中 base64 解码 + zstd 解压后的原始 UTF-8 字节。"""
    compressed = base64.b64decode(b64_text.strip())
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(compressed, max_output_size=max_out)


def encrypt_body_to_base64(utf8_json: bytes, level: int = 1) -> str:
    """对应 prepareRequestData：zstd 压缩 + base64。"""
    cctx = zstd.ZstdCompressor(level=level)
    compressed = cctx.compress(utf8_json)
    return base64.b64encode(compressed).decode("ascii")


def _read_text_arg(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _read_bytes_arg(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    return Path(path).read_bytes()


def cmd_decrypt(args: argparse.Namespace) -> int:
    text = _read_text_arg(args.input)
    raw = decrypt_body_base64(text, max_out=args.max_output_size)
    if args.pretty:
        obj = json.loads(raw.decode("utf-8"))
        out = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        data = out.encode("utf-8")
    else:
        data = raw

    if args.output == "-":
        sys.stdout.buffer.write(data)
    else:
        Path(args.output).write_bytes(data)
    return 0


def cmd_encrypt(args: argparse.Namespace) -> int:
    blob = _read_bytes_arg(args.input)
    # 若希望严格 JSON，可在加密前校验
    if args.validate_json:
        json.loads(blob.decode("utf-8"))

    b64 = encrypt_body_to_base64(blob, level=args.level)
    line = b64 + ("\n" if args.newline else "")
    if args.output == "-":
        sys.stdout.write(line)
        if args.newline:
            pass
    else:
        Path(args.output).write_text(line, encoding="ascii", newline="")
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    """扫描 test_data 下所有 *_zstd_encrypt.txt，与同名 *_zstd_decrypt.txt 比对 JSON（允许空白差异）。"""
    root = Path(args.test_root)
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 1

    enc_suf = "_zstd_encrypt.txt"
    enc_files = sorted(root.glob(f"*{enc_suf}"))
    if not enc_files:
        print("未找到 *_zstd_encrypt.txt 文件", file=sys.stderr)
        return 1

    errs = 0
    ok = 0
    for enc in enc_files:
        name = enc.name[: -len(enc_suf)]
        dec = root / f"{name}_zstd_decrypt.txt"
        if not dec.is_file():
            print(f"缺少配对: {dec.name}（对应 {enc.name}）", file=sys.stderr)
            errs += 1
            continue
        plain = decrypt_body_base64(enc.read_text(encoding="utf-8"), max_out=args.max_output_size)
        ref_text = dec.read_text(encoding="utf-8")
        try:
            got = json.loads(plain.decode("utf-8"))
            want = json.loads(ref_text)
        except json.JSONDecodeError as exc:
            print(f"[{name}] JSON 解析失败: {exc}", file=sys.stderr)
            errs += 1
            continue
        if got != want:
            print(f"[{name}] 解密 JSON 与参照不一致", file=sys.stderr)
            errs += 1
            continue
        canon = json.dumps(got, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        round_plain = decrypt_body_base64(encrypt_body_to_base64(canon, level=1), max_out=args.max_output_size)
        if json.loads(round_plain.decode("utf-8")) != got:
            print(f"[{name}] Python 侧 zstd encode->decode 语义闭环失败", file=sys.stderr)
            errs += 1
            continue
        print(f"ok {name}")
        ok += 1

    if errs:
        print(f"self-test: {errs} 组失败，{ok} 组通过", file=sys.stderr)
        return 1
    print(f"self-test ok: {ok} 组全部通过（JSON 等价 + encode 闭环）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ParamModel body: Base64 <-> Zstd <-> UTF-8 JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("decrypt", aliases=["decode", "d"], help="Base64(body) -> 解压 -> 原始 UTF-8 / JSON")
    d.add_argument("-i", "--input", default="-", help="输入文件，或 - 为 stdin（整段 base64 文本）")
    d.add_argument("-o", "--output", required=True, help="输出；- 为 stdout（二进制 UTF-8 原文）")
    d.add_argument("--pretty", action="store_true", help="解压后若为 JSON，则格式化输出（UTF-8 文本）")
    d.add_argument("--max-output-size", type=int, default=_DEFAULT_MAX_OUT)
    d.set_defaults(func=cmd_decrypt)

    e = sub.add_parser("encrypt", aliases=["encode", "e"], help="UTF-8 JSON -> Zstd -> Base64 一行")
    e.add_argument("-i", "--input", default="-", help="输入 JSON 文件或 - 为 stdin")
    e.add_argument("-o", "--output", required=True, help="输出 base64 文本路径，或 -")
    e.add_argument("-l", "--level", type=int, default=1, help="Zstd 等级，与 TS 默认一致为 1")
    e.add_argument("--validate-json", action="store_true", help="加密前用 json.loads 校验")
    e.add_argument("--newline", action="store_true", help="输出末尾追加换行")
    e.set_defaults(func=cmd_encrypt)

    t = sub.add_parser("self-test", help="使用 test_data 目录跑内置校验")
    t.add_argument(
        "--test-root",
        default=str(Path(__file__).resolve().parent / "test_data"),
        help="存放成对的 *_zstd_encrypt.txt / *_zstd_decrypt.txt 的目录",
    )
    t.add_argument("--max-output-size", type=int, default=_DEFAULT_MAX_OUT)
    t.set_defaults(func=cmd_self_test)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
