"""
H5 API 返回数据的加解密（Vigenère 变种），对应 decrypt.js 的 Python 实现。

用法:
  python crypt_h5.py --all -i encrypted.txt -o output.txt
  python crypt_h5.py --all-no-gzip -i encrypted.txt -o output.txt
  python crypt_h5.py --vigenere -i encrypted.txt -o plain.txt
  python crypt_h5.py --encrypt -i plain.txt -o cipher.txt
  python crypt_h5.py --encrypt-all -i plain.json -o api_cipher.txt
  python crypt_h5.py --encrypt-all-no-gzip -i plain.txt -o cipher.txt
  python crypt_h5.py --auto -i data.txt
"""

from __future__ import annotations

import argparse
import base64
import gzip
import sys
from pathlib import Path
from typing import Union

# 512 字节密钥，与 @qunhe/tools-common/lang/VigenereCipher / decrypt.js 一致
KEY = bytes(
    (
        57, 125, 126, 68, 102, 93, 40, 64, 122, 49, 57, 115, 117, 77, 61, 45, 93, 99, 80, 95,
        40, 41, 46, 101, 103, 68, 123, 65, 41, 33, 61, 116, 108, 120, 114, 56, 45, 100, 51, 56,
        50, 125, 97, 100, 91, 74, 35, 58, 110, 62, 63, 115, 59, 37, 83, 123, 47, 81, 94, 60,
        49, 71, 125, 36, 64, 37, 49, 108, 47, 126, 45, 82, 98, 100, 115, 66, 113, 35, 80, 87,
        65, 48, 124, 60, 33, 87, 125, 48, 40, 57, 48, 35, 53, 63, 88, 121, 46, 126, 106, 53,
        61, 40, 125, 115, 35, 43, 45, 37, 123, 62, 35, 105, 42, 33, 40, 61, 76, 119, 39, 37,
        62, 114, 35, 114, 120, 40, 105, 112, 33, 41, 33, 55, 77, 118, 102, 93, 39, 70, 50, 56,
        37, 53, 81, 40, 95, 81, 115, 119, 41, 78, 100, 99, 109, 56, 126, 111, 78, 80, 57, 104,
        41, 101, 106, 35, 69, 111, 87, 53, 59, 74, 77, 34, 63, 78, 80, 67, 86, 109, 42, 32,
        108, 116, 96, 106, 74, 92, 49, 35, 96, 83, 76, 44, 107, 37, 52, 63, 91, 34, 73, 115,
        89, 98, 32, 79, 67, 92, 33, 115, 42, 36, 65, 78, 115, 65, 69, 107, 74, 37, 42, 89,
        83, 65, 32, 77, 73, 55, 86, 62, 107, 105, 70, 106, 56, 42, 49, 116, 114, 109, 53, 34,
        104, 40, 112, 49, 78, 88, 109, 44, 56, 104, 53, 85, 104, 43, 99, 76, 52, 41, 33, 35,
        52, 80, 66, 119, 69, 58, 96, 100, 85, 98, 60, 80, 71, 109, 87, 93, 35, 37, 124, 67,
        38, 33, 110, 36, 46, 95, 51, 99, 124, 64, 44, 96, 45, 78, 120, 89, 58, 79, 123, 44,
        43, 109, 102, 113, 114, 62, 34, 75, 49, 58, 55, 55, 39, 44, 35, 43, 85, 103, 40, 106,
        71, 38, 58, 58, 63, 39, 61, 88, 47, 90, 120, 65, 50, 118, 38, 61, 59, 65, 37, 47,
        38, 43, 43, 83, 56, 44, 99, 36, 82, 57, 56, 91, 51, 44, 77, 88, 45, 102, 56, 108,
        120, 34, 34, 77, 112, 91, 74, 55, 39, 60, 60, 103, 45, 77, 58, 59, 53, 91, 49, 107,
        97, 57, 52, 52, 48, 44, 80, 112, 62, 56, 45, 106, 121, 113, 48, 53, 105, 51, 67, 119,
        34, 41, 57, 60, 53, 106, 76, 37, 37, 119, 36, 118, 94, 104, 122, 60, 55, 49, 121, 74,
        43, 35, 104, 35, 58, 112, 88, 57, 90, 38, 40, 97, 89, 70, 50, 52, 56, 98, 46, 89,
        76, 96, 110, 34, 46, 110, 96, 51, 80, 106, 54, 101, 34, 126, 74, 100, 70, 32, 91, 49,
        62, 56, 110, 49, 35, 52, 55, 67, 41, 57, 105, 81, 55, 45, 33, 43, 83, 51, 113, 80,
        50, 98, 92, 55, 48, 81, 109, 54, 96, 119, 92, 90, 90, 48, 45, 49, 84, 53, 111, 41,
        46, 48, 56, 60, 83, 125, 36, 116, 70, 97, 111, 54,
    )
)


def encode_byte(byte: int, index: int) -> int:
    if byte < 32 or byte >= 127:
        return byte
    encoded = byte + (KEY[index % 512] - 32)
    if encoded >= 127:
        encoded -= 95
    return encoded & 0xFF


def decode_byte(byte: int, byte_index: int) -> int:
    if byte < 32 or byte >= 127:
        return byte
    decoded = byte - (KEY[byte_index % 512] - 32)
    if decoded < 32:
        decoded += 95
    return decoded


def encrypt(plain: str) -> str:
    utf8 = plain.encode("utf-8")
    out = bytearray(encode_byte(b, i) for i, b in enumerate(utf8))
    return out.decode("utf-8")


def decrypt(cipher: str) -> str:
    utf8_cipher = cipher.encode("utf-8")
    out = bytearray(decode_byte(b, i) for i, b in enumerate(utf8_cipher))
    return out.decode("utf-8")


def encrypt_buffer(buf: Union[bytes, bytearray, memoryview]) -> bytes:
    data = bytes(buf)
    return bytes(encode_byte(b, i) for i, b in enumerate(data))


def decrypt_buffer(buf: Union[bytes, bytearray, memoryview]) -> bytes:
    data = bytes(buf)
    return bytes(decode_byte(b, i) for i, b in enumerate(data))


def simple_decrypt(encrypted_str: str) -> str:
    return decrypt(encrypted_str)


def _b64decode_to_bytes(s: str, context: str) -> bytes:
    """Base64 解码：对 str 需先转为 ASCII bytes；失败时说明常见误用（如把明文当密文）。"""
    try:
        return base64.b64decode(s.encode("ascii"), validate=False)
    except UnicodeEncodeError as e:
        raise ValueError(
            f"{context} 中含非 ASCII 字符，无法作为 Base64 解码。"
            "若文件已是解密后的 JSON（例如 *dycrypt*.txt），请勿再使用 --all；"
            "--all 需要的是 API 密文（例如 bg_collections_h5_encrypt.txt）。"
        ) from e


def gunzip_and_decode(encoded_str: str) -> str:
    raw = _b64decode_to_bytes(encoded_str.strip(), context="GZIP 前的 Base64")
    return gzip.decompress(raw).decode("utf-8")


def full_encrypt(plain: str) -> str:
    """与 full_decrypt 互逆：JSON 文本 → GZIP → Base64 字符串 → Vigenère（gzip 使用固定 mtime=0 便于回归比对）。"""
    gz = gzip.compress(plain.encode("utf-8"), compresslevel=9, mtime=0)
    b64 = base64.b64encode(gz).decode("ascii")
    return encrypt(b64)


def full_encrypt_no_gzip(plain: str) -> str:
    """与 full_decrypt_no_gzip 互逆：UTF-8 文本 → Base64 → Vigenère。"""
    b64 = base64.b64encode(plain.encode("utf-8")).decode("ascii")
    return encrypt(b64)


def full_decrypt(encrypted_str: str) -> str:
    s = encrypted_str.strip()
    if s.startswith("{") or s.startswith("["):
        raise ValueError(
            "输入以 { 或 [ 开头，已是明文 JSON。--all 只处理三层包：Vigenère → Base64 → GZIP；"
            "请把 -i 换成密文（如 bg_collections_h5_encrypt.txt），不要对 *dycrypt*.txt 再用 --all。"
        )
    dec = decrypt(s)
    raw = _b64decode_to_bytes(dec, context="Vigenère 解密后、GZIP 前的 Base64")
    return gzip.decompress(raw).decode("utf-8")


def full_decrypt_no_gzip(encrypted_str: str) -> str:
    """与 full_decrypt 相同，但 Base64 解码后不再做 GZIP，按 UTF-8 解码为文本。"""
    s = encrypted_str.strip()
    if s.startswith("{") or s.startswith("["):
        raise ValueError(
            "输入以 { 或 [ 开头，已是明文 JSON。本模式为 Vigenère → Base64（无 GZIP）；"
            "请把 -i 换成密文。"
        )
    dec = decrypt(s)
    raw = _b64decode_to_bytes(dec, context="Vigenère 解密后、Base64 层")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
            raise ValueError(
                "Base64 解码后的内容是 GZIP（魔数 1f 8b）。应使用 --all（含 GZIP 解压），"
                "不要用 --all-no-gzip。"
            ) from e
        raise


def auto_decrypt(s: str) -> str:
    s_stripped = s.strip()
    if s_stripped.startswith("H4sIAAAAAAAA"):
        return gunzip_and_decode(s_stripped)

    try:
        raw = _b64decode_to_bytes(s_stripped, context="尝试 gzip 路径时的 Base64")
        text = gzip.decompress(raw).decode("utf-8")
        if text.startswith("{") or text.startswith("["):
            return text
    except (ValueError, OSError, EOFError):
        pass

    try:
        plain = simple_decrypt(s_stripped)
        if plain.startswith("{") or plain.startswith("["):
            return plain
    except (UnicodeDecodeError, ValueError):
        pass

    try:
        return full_decrypt(s_stripped)
    except ValueError:
        pass

    raise ValueError("无法自动检测加密格式")


def _read_input(args: argparse.Namespace) -> str:
    if args.input is not None:
        if args.input == "-":
            return sys.stdin.read().strip()
        return Path(args.input).read_text(encoding="utf-8").strip()
    if args.input_string is not None:
        return args.input_string
    raise SystemExit("请指定输入：-i 文件 / - 为 stdin，或直接传入字符串")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="H5 Vigenère / Base64 / GZIP 加解密（crypt_h5）")
    p.add_argument(
        "--all",
        action="store_true",
        help="完整流程：Vigenère → Base64 → GZIP 解压",
    )
    p.add_argument(
        "--all-no-gzip",
        action="store_true",
        dest="all_no_gzip",
        help="与 --all 相同但最后不做 GZIP：Vigenère → Base64 → UTF-8 文本",
    )
    p.add_argument(
        "--gunzip",
        action="store_true",
        help="仅 Base64 → GZIP（无 Vigenère），适用于 H4sI… 开头",
    )
    p.add_argument(
        "--vigenere",
        action="store_true",
        help="仅 Vigenère 解密",
    )
    p.add_argument(
        "--auto",
        action="store_true",
        help="自动检测（默认）",
    )
    p.add_argument(
        "--encrypt",
        action="store_true",
        help="仅 Vigenère 加密（明文 UTF-8 → 密文串）",
    )
    p.add_argument(
        "--encrypt-all",
        action="store_true",
        dest="encrypt_all",
        help="完整加密：UTF-8 明文 → GZIP → Base64 → Vigenère（对应 --all 解密）",
    )
    p.add_argument(
        "--encrypt-all-no-gzip",
        action="store_true",
        dest="encrypt_all_no_gzip",
        help="Vigenère + Base64（无 GZIP），对应 --all-no-gzip 解密",
    )
    p.add_argument("-i", "--input", help="输入文件，或 - 为 stdin（与 crypt_zstd 一致）")
    p.add_argument("-o", "--output", metavar="PATH", help="写入结果到文件")
    p.add_argument("rest", nargs="*", help="输入字符串（未使用 -i 时）")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.input is None and args.rest:
        args.input_string = " ".join(args.rest)
    else:
        args.input_string = None

    mode_all = args.all
    mode_all_no_gzip = args.all_no_gzip
    mode_gunzip = args.gunzip
    mode_vigenere = args.vigenere
    mode_encrypt = args.encrypt
    mode_encrypt_all = args.encrypt_all
    mode_encrypt_all_no_gzip = args.encrypt_all_no_gzip
    mode_auto = args.auto

    mode_count = sum(
        bool(x)
        for x in (
            mode_all,
            mode_all_no_gzip,
            mode_gunzip,
            mode_vigenere,
            mode_encrypt,
            mode_encrypt_all,
            mode_encrypt_all_no_gzip,
            mode_auto,
        )
    )
    if mode_count == 0:
        mode_auto = True
    elif mode_count > 1:
        parser.error(
            "只能选择一种模式：--all / --all-no-gzip / --gunzip / --vigenere / "
            "--auto / --encrypt / --encrypt-all / --encrypt-all-no-gzip"
        )

    content = _read_input(args)

    try:
        if mode_encrypt or mode_encrypt_all or mode_encrypt_all_no_gzip:
            if mode_encrypt:
                result = encrypt(content)
            elif mode_encrypt_all:
                result = full_encrypt(content)
            else:
                result = full_encrypt_no_gzip(content)
            if args.output:
                Path(args.output).write_text(result, encoding="utf-8")
                print(f"密文已保存到: {args.output}", file=sys.stderr)
            else:
                sys.stdout.buffer.write(result.encode("utf-8"))
                if not result.endswith("\n"):
                    sys.stdout.buffer.write(b"\n")
            return

        if mode_all:
            result = full_decrypt(content)
        elif mode_all_no_gzip:
            result = full_decrypt_no_gzip(content)
        elif mode_gunzip:
            result = gunzip_and_decode(content)
        elif mode_vigenere:
            result = simple_decrypt(content)
        else:
            result = auto_decrypt(content)

        if args.output:
            Path(args.output).write_text(result, encoding="utf-8")
            print(f"结果已保存到: {args.output}", file=sys.stderr)
        else:
            sys.stdout.buffer.write(result.encode("utf-8"))
            if not result.endswith("\n"):
                sys.stdout.buffer.write(b"\n")
    except Exception as e:
        print(f"处理失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
