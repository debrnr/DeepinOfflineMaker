#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debian 版本号比较（等价 dpkg --compare-versions 的常用规则）。

版本格式: [epoch:]upstream_version[-debian_revision]
用于判断仓库里的包是否比 ISO 清单里的版本更新。
"""
import re


def _order(c):
    if c.isalpha():
        return ord(c)
    if c == '~':
        return -1
    if c:
        return ord(c) + 256
    return 0


def _compare_part(a, b):
    """比较 upstream 或 revision 的非数字/数字交替串。
    关键规则: '~' 排在所有字符之前，且比“字符串结束”还小。"""
    i = j = 0
    while i < len(a) or j < len(b):
        # 跳过非字母数字(~不跳过，需参与比较)
        while i < len(a) and not (a[i].isalnum() or a[i] == '~'):
            i += 1
        while j < len(b) and not (b[j].isalnum() or b[j] == '~'):
            j += 1

        # 一方结束：若结束方没有 '~'，则结束方更大('~'比结束还小)
        if i >= len(a):
            if j < len(b) and b[j] == '~':
                return 1          # a 结束 vs b 的 '~' -> a 大
            if j >= len(b):
                return 0
            return -1
        if j >= len(b):
            if a[i] == '~':
                return -1         # a 的 '~' vs b 结束 -> a 小
            return 1

        a_num = a[i].isdigit()
        b_num = b[j].isdigit()
        if a_num != b_num:
            return 1 if a_num else -1
        if a_num:
            k = i
            while k < len(a) and a[k].isdigit():
                k += 1
            m = j
            while m < len(b) and b[m].isdigit():
                m += 1
            ia, ib = int(a[i:k]), int(b[j:m])
            if ia != ib:
                return 1 if ia > ib else -1
            i, j = k, m
        else:
            if a[i] != b[j]:
                return 1 if _order(a[i]) > _order(b[j]) else -1
            i += 1
            j += 1
    return 0


def parse_version(v):
    v = v.strip()
    epoch = 0
    if ':' in v:
        es, rest = v.split(':', 1)
        if es.isdigit():
            epoch = int(es)
            v = rest
    if '-' in v:
        upstream, revision = v.rsplit('-', 1)
    else:
        upstream, revision = v, ''
    return epoch, upstream, revision


def vercmp(a, b):
    """返回 1 表示 a>b, 0 相等, -1 表示 a<b。"""
    if a == b:
        return 0
    ea, ua, ra = parse_version(a)
    eb, ub, rb = parse_version(b)
    if ea != eb:
        return 1 if ea > eb else -1
    r = _compare_part(ua, ub)
    if r != 0:
        return r
    return _compare_part(ra, rb)


def is_newer(candidate, base):
    """candidate 是否比 base 新。"""
    return vercmp(candidate, base) > 0


if __name__ == '__main__':
    tests = [
        ('1:2.0.34-1', '1.9-5', 1),
        ('26.02+dfsg-2deepin2', '24.09+dfsg-1', 1),
        ('3.138', '3.137', 1),
        ('1.0~rc1-1', '1.0-1', -1),
        ('1.0-1', '1.0-1', 0),
        ('48.1-1deepin6', '48.1-1deepin9', -1),
    ]
    for a, b, want in tests:
        got = vercmp(a, b)
        print('%-28s vs %-20s = %2d  (want %2d) %s' % (a, b, got, want, 'OK' if got == want else 'FAIL'))
