from datetime import datetime, timedelta

class ExpiredDict(dict):
    """
    ExpiredDict 是一个带有过期时间的字典。每个键值对在插入时会被记录一个过期时间，超过指定秒数后自动失效。
    主要用于缓存等需要自动过期的数据场景。

    参数:
        expires_in_seconds: int，所有键值对的过期时间（秒）

    主要方法说明：
    - __setitem__(key, value): 设置键值对，并记录过期时间。
    - __getitem__(key): 获取键值对，如果已过期则抛出KeyError并删除该项。
    - get(key, default): 获取键值对，若不存在或已过期则返回default。
    - __contains__(key): 判断键是否存在且未过期。
    - keys(): 返回所有未过期的键。
    - items(): 返回所有未过期的键值对。
    - __iter__(): 迭代所有未过期的键。
    """

    def __init__(self, expires_in_seconds):
        super().__init__()
        self.expires_in_seconds = expires_in_seconds

    def __getitem__(self, key):
        # 获取键对应的值和过期时间，如果已过期则删除并抛出KeyError
        value, expiry_time = super().__getitem__(key)
        if datetime.now() > expiry_time:
            del self[key]
            raise KeyError("expired {}".format(key))
        # 刷新过期时间
        self.__setitem__(key, value)
        return value

    def __setitem__(self, key, value):
        # 设置键值对，并记录新的过期时间
        expiry_time = datetime.now() + timedelta(seconds=self.expires_in_seconds)
        super().__setitem__(key, (value, expiry_time))

    def get(self, key, default=None):
        # 获取键对应的值，若不存在或已过期则返回default
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        # 判断键是否存在且未过期
        try:
            self[key]
            return True
        except KeyError:
            return False

    def keys(self):
        # 返回所有未过期的键
        keys = list(super().keys())
        return [key for key in keys if key in self]

    def items(self):
        # 返回所有未过期的键值对
        return [(key, self[key]) for key in self.keys()]

    def __iter__(self):
        # 迭代所有未过期的键
        return self.keys().__iter__()
