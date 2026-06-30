import math

# 自定义解密异常类（对应 Java BadDecryptException）
class BadDecryptException(ValueError):
    def __init__(self, message=None):
        super().__init__(message)

class LongCrypt:
    # 常量定义（与 Java 完全一致）
    DEFAULT_KEY = 818647634524367
    DEFAULT_RADIX = 31

    def __init__(self, key: int, radix: int):
        self.mKey = key
        self.mRadix = radix

    # 实例方法：加密 Long 类型
    def encrypt(self, id_val: int | None) -> str | None:
        if id_val is None:
            return None
        
        number = id_val
        # 4轮加密运算（与 Java 逻辑完全一致）
        for _ in range(4):
            number ^= self.mKey
            number <<= 3
            # Python 自动处理 64 位有符号整数，无需额外处理
        
        # 转换为指定进制并大写
        return self._long_to_radix(number, self.mRadix).upper()

    # 实例方法：解密字符串
    def decrypt(self, crypted_string: str | None) -> int:
        if crypted_string is None:
            raise ValueError("decrypt - The input string is null.")
        
        try:
            # 字符串转指定进制数字
            number = self._radix_to_long(crypted_string, self.mRadix)
        except ValueError:
            raise BadDecryptException(f"invalid input string:{crypted_string}")
        
        # 4轮逆运算解密
        for _ in range(4):
            number >>= 3
            number ^= self.mKey
        
        return number

    # 静态默认加密
    @staticmethod
    def default_encrypt(id_val: int) -> str:
        number = id_val
        for _ in range(4):
            number ^= LongCrypt.DEFAULT_KEY
            number <<= 3
        
        return LongCrypt._long_to_radix(number, LongCrypt.DEFAULT_RADIX).upper()

    # 静态默认解密
    @staticmethod
    def default_decrypt(crypted_string: str | None) -> int:
        if crypted_string is None:
            raise ValueError("defaultDecrypt - The input string is null.")
        
        number = LongCrypt._radix_to_long(crypted_string, LongCrypt.DEFAULT_RADIX)
        for _ in range(4):
            number >>= 3
            number ^= LongCrypt.DEFAULT_KEY
        
        return number

    # 重载加密方法
    def encrypt_with_params(self, id_val: int, key: int, radix: int) -> str:
        number = id_val
        for _ in range(4):
            number ^= key
            number <<= 3
        
        return self._long_to_radix(number, radix).upper()

    # 重载解密方法
    def decrypt_with_params(self, crypted_string: str | None, key: int, radix: int) -> int:
        if crypted_string is None:
            raise ValueError("decrypt - The input string is null.")
        
        number = self._radix_to_long(crypted_string, radix)
        for _ in range(4):
            number >>= 3
            number ^= key
        
        return number

    # ==================== 工具方法：数字 ↔ 任意进制字符串 ====================
    @staticmethod
    def _long_to_radix(num: int, radix: int) -> str:
        """将 64 位有符号整数转为指定进制字符串（完全兼容 Java BigInteger）"""
        if radix < 2 or radix > 36:
            raise ValueError("radix must be between 2 and 36")
        
        # 处理 0
        if num == 0:
            return "0"
        
        # Java 64 位有符号整数范围
        INT64_MIN = -9223372036854775808
        INT64_MAX = 9223372036854775807
        
        # 超出范围处理
        if num < INT64_MIN or num > INT64_MAX:
            num = num & 0xFFFFFFFFFFFFFFFF  # 转为无符号64位
            if num > INT64_MAX:
                num -= (INT64_MAX + 1) * 2
        
        digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        is_negative = num < 0
        num = abs(num)
        result = []
        
        while num > 0:
            result.append(digits[num % radix])
            num = num // radix
        
        if is_negative:
            result.append("-")
        
        return ''.join(reversed(result))

    @staticmethod
    def _radix_to_long(s: str, radix: int) -> int:
        """指定进制字符串转回 64 位有符号整数（兼容 Java）"""
        return int(s, radix)