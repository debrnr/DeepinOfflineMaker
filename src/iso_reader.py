#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ISO 读取与包清单解析。

- 用 PowerShell Mount-DiskImage 挂载 ISO，读取 live/filesystem.packages
- 清单为 TAB 分隔的 "包名\t版本" 行；包名可能带 :loong64 架构后缀
"""
import os, re, subprocess, tempfile, shutil

MANIFEST_REL = os.path.join('live', 'filesystem.packages')


def _ps_exe():
    for c in ('powershell.exe', 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'):
        return c
    return 'powershell.exe'


def read_manifest_from_iso(iso_path, log=print):
    """挂载 ISO 并把 filesystem.packages 读成 dict。失败抛异常。"""
    iso = os.path.abspath(iso_path)
    if not os.path.isfile(iso):
        raise FileNotFoundError('ISO 不存在: %s' % iso)
    tmpdir = tempfile.mkdtemp(prefix='deepin-iso-')
    outfile = os.path.join(tmpdir, 'filesystem.packages')
    ps = (
        "$img = Mount-DiskImage -ImagePath '%s' -PassThru -ErrorAction Stop; "
        "$drive = ($img | Get-Volume).DriveLetter; "
        "Copy-Item -LiteralPath (\"${drive}:\\live\\filesystem.packages\") -Destination '%s' -Force; "
        "Dismount-DiskImage -ImagePath '%s' | Out-Null; "
        "Write-Output 'OK'" % (iso.replace("'", "''"), outfile.replace("'", "''"), iso.replace("'", "''"))
    )
    try:
        log('正在挂载 ISO 读取包清单（可能需要管理员权限）...')
        r = subprocess.run([_ps_exe(), '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=180)
        if 'OK' not in r.stdout or not os.path.isfile(outfile):
            msg = r.stderr.strip() or r.stdout.strip() or '未知错误'
            raise RuntimeError('读取 ISO 失败: %s' % msg[:500])
        log('ISO 清单读取成功。')
        return parse_manifest(outfile)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def read_manifest_from_file(path):
    return parse_manifest(path)


def parse_manifest(path):
    """解析 TAB 分隔的 packages 文件 -> {规范包名: 版本}。
    包名带 :loong64 等架构后缀会剥离；保留 epoch 版本号里的冒号。"""
    out = {}
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line or '\t' not in line:
                continue
            name, ver = line.split('\t', 1)
            name = name.strip()
            ver = ver.strip()
            if not name or not ver:
                continue
            # 剥离多架构限定后缀 :loong64 / :any / :amd64 等
            if ':' in name:
                name = name.split(':', 1)[0]
            out[name] = ver
    return out


def diff_manifests(new, old):
    """返回 (新增或版本变化 的包名列表, 移除的包名列表)。"""
    changed = [n for n, v in new.items() if old.get(n) != v]
    removed = [n for n in old if n not in new]
    return sorted(changed), sorted(removed)


if __name__ == '__main__':
    import sys
    p = sys.argv[1]
    m = read_manifest_from_iso(p) if p.lower().endswith('.iso') else parse_manifest(p)
    print('共 %d 个包' % len(m))
    for k in list(m)[:5]:
        print(' ', k, '=', m[k])
