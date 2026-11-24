#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deepin loong64 仓库索引解析、包匹配、依赖解析、多线程下载与校验。

索引来源：deepin 25 (crimson/beige) 的 main/commercial/community 三组件。
只使用标准库。
"""
import os, re, gzip, io, hashlib, urllib.request, ssl, time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = 'https://mirrors.ustc.edu.cn/deepin/beige'
# 下载兜底镜像：主源 403/失败时自动轮换
FALLBACK_BASES = (
    'https://mirrors.tuna.tsinghua.edu.cn/deepin/beige',
    'https://mirrors.huaweicloud.com/deepin/beige',
    'https://community-packages.deepin.com/deepin/beige',
)
SUITE = 'crimson'
COMPS = ('main', 'commercial', 'community')
ARCH = 'loong64'


def _urlopen(url, timeout=60, headers=None):
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def parse_packages_bytes(data):
    """解析 Debian Packages 文本 -> list[dict]。"""
    stanzas = []
    cur = {}
    for raw in data.splitlines():
        line = raw.decode('utf-8', errors='replace')
        if not line.strip():
            if cur:
                stanzas.append(cur)
                cur = {}
            continue
        if line.startswith(' '):
            continue
        if ':' in line:
            k, v = line.split(':', 1)
            cur[k.strip()] = v.strip()
    if cur:
        stanzas.append(cur)
    return stanzas


class Repo:
    def __init__(self, base=BASE, components=COMPS, log=print):
        self.base = base.rstrip('/')
        self.comps = components
        self.log = log
        self.index = {}   # (name, version) -> stanza dict
        self.by_name = {}  # name -> list[(version, stanza)]

    def load(self, cache_dir=None, force=False):
        """下载并解析三个组件的 Packages.gz。cache_dir 给定时可复用。"""
        all_stanzas = []
        for comp in self.comps:
            data = None
            cache = None
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                cache = os.path.join(cache_dir, 'Packages-%s.gz' % comp)
                if os.path.isfile(cache) and not force:
                    with open(cache, 'rb') as f:
                        data = f.read()
            if data is None:
                rel = 'dists/%s/%s/binary-%s/Packages.gz' % (SUITE, comp, ARCH)
                last = None
                for src in [self.base] + list(FALLBACK_BASES):
                    url = '%s/%s' % (src.rstrip('/'), rel)
                    try:
                        self.log('下载仓库索引 %s（%s）...' % (comp, src.split('/')[2]))
                        with _urlopen(url, timeout=180) as r:
                            got = r.read()
                        if got[:2] != b'\x1f\x8b':
                            raise RuntimeError('返回的不是 gzip 索引')
                        data = got
                        break
                    except Exception as e:
                        last = '%s: %s' % (src.split('/')[2], e)
                if data is None:
                    raise RuntimeError('仓库索引 %s 全部镜像失败：%s' % (comp, last))
                if cache:
                    with open(cache, 'wb') as f:
                        f.write(data)
            txt = gzip.decompress(data)
            st = parse_packages_bytes(txt)
            self.log('  组件 %s: %d 个包' % (comp, len(st)))
            all_stanzas.extend(st)
        for s in all_stanzas:
            name = s.get('Package', '')
            ver = s.get('Version', '')
            if not name or not ver:
                continue
            self.index[(name, ver)] = s
            self.by_name.setdefault(name, []).append((ver, s))
        return len(all_stanzas)

    def find_exact(self, name, version):
        s = self.index.get((name, version))
        if s:
            return s
        # 仓库版本比镜像更新时，尝试同包名的其他版本（取最新）
        cands = self.by_name.get(name, [])
        if cands:
            return sorted(cands, key=lambda x: x[0])[-1][1]
        return None

    def find_updates(self, iso_manifest, log=print):
        """找源里比 ISO 清单更新的包。

        iso_manifest: {包名: ISO内版本} —— 代表“刚装机、未联网”的状态。
        返回 [(包名, 源里最新版本, stanza), ...]，即装机后本应在线升级的包。
        """
        from vercmp import is_newer
        updates = []
        for name, iso_ver in iso_manifest.items():
            cands = self.by_name.get(name)
            if not cands:
                continue
            # 源里该包的最新版本（按 Debian 版本比较取最大）
            best_ver, best_st = cands[0]
            for v, s in cands[1:]:
                if is_newer(v, best_ver):
                    best_ver, best_st = v, s
            if is_newer(best_ver, iso_ver):
                updates.append((name, best_ver, best_st))
        log('源内比 ISO 更新的包: %d 个' % len(updates))
        return updates

    @staticmethod
    def parse_dep(dep):
        """解析 Depends 字段，返回 [(name, [alt...]) ...]，去掉版本约束/架构限定。"""
        groups = []
        for clause in dep.split(','):
            clause = clause.strip()
            if not clause:
                continue
            alts = []
            for alt in clause.split('|'):
                alt = alt.strip()
                alt = re.sub(r'\s*\(.*?\)\s*', '', alt)
                alt = re.sub(r'\s*\[.*?\]\s*', '', alt)
                alt = re.sub(r'\s*<.*?>\s*', '', alt)
                alt = alt.replace(':any', '').strip()
                if alt and re.match(r'^[a-zA-Z0-9+.\-]+$', alt):
                    alts.append(alt)
            if alts:
                groups.append(alts)
        return groups

    def resolve(self, wanted, installed=None, with_deps=True):
        """按包名集合解析出需要下载的 stanza 列表。

        wanted: [(name, version)] —— 这些是明确要升级/安装的包，一律纳入。
        installed: {name: version} —— 基准系统已装包，仅用于跳过"依赖包在基准里
                   已有同版本或更高版本"的情况；版本变化的目标包不会被跳过。
        """
        installed = installed or {}
        chosen = []           # list of stanza
        seen = set()
        # wanted 强制加入；用 is_wanted 标记避免被 installed 跳过
        queue = [(n, v, True) for n, v in wanted]

        while queue:
            name, ver, is_wanted = queue.pop(0)
            key = (name, ver)
            if key in seen:
                continue
            seen.add(key)
            # 仅依赖包才按基准版本跳过；目标包(含版本变化)必须纳入
            if not is_wanted and name in installed:
                inst_ver = installed[name]
                # 基准版本与目标版本相同 -> 无需重复下载
                if inst_ver == ver:
                    continue
            stanza = self.find_exact(name, ver)
            if not stanza:
                continue
            chosen.append(stanza)
            if not with_deps:
                continue
            deps = self.parse_dep(stanza.get('Depends', ''))
            for alts in deps:
                picked = None
                for alt in alts:
                    if self.by_name.get(alt):
                        picked = alt
                        break
                if picked:
                    cands = sorted(self.by_name[picked], key=lambda x: x[0])
                    dver = cands[-1][0]
                    if (picked, dver) not in seen:
                        queue.append((picked, dver, False))
        return chosen


def download_one(url_path, dest, base, sha256, retries=4):
    """下载单个 deb 并校验 SHA256。主源失败自动轮换兜底镜像。
    url_path 为 Packages 的 Filename 字段。"""
    bases = [base] + list(FALLBACK_BASES)
    tmp = dest + '.part'
    last = None
    for attempt in range(retries):
        src = bases[attempt % len(bases)]
        url = '%s/%s' % (src.rstrip('/'), url_path.lstrip('/'))
        try:
            with _urlopen(url, timeout=120) as r, open(tmp, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            if sha256:
                h = hashlib.sha256()
                with open(tmp, 'rb') as f:
                    for b in iter(lambda: f.read(1 << 20), b''):
                        h.update(b)
                if h.hexdigest().lower() != sha256.lower():
                    raise RuntimeError('SHA256 不匹配')
            os.replace(tmp, dest)
            return True, ''
        except Exception as e:
            last = '%s: %s' % (src.split('/')[2], e)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            time.sleep(0.8 * (attempt + 1))
    return False, last or '未知错误'


def download_all(stanzas, dest_dir, base=BASE, workers=8, log=print, progress=None):
    """多线程下载 deb。progress(done, total, name) 回调。"""
    os.makedirs(dest_dir, exist_ok=True)
    tasks = []
    for s in stanzas:
        fn = s.get('Filename', '')
        arch = s.get('Architecture', '')
        if not fn:
            continue
        base_name = os.path.basename(fn)
        # 避免同名不同组件覆盖，用 包名_版本_架构.deb 统一命名更稳
        safe = '%s_%s_%s.deb' % (re.sub(r'[^\w+.\-]', '_', s.get('Package', 'pkg')),
                                re.sub(r'[^\w+.\-]', '_', s.get('Version', '0')),
                                arch or 'all')
        tasks.append((s, safe))
    total = len(tasks)
    done = 0
    failed = []
    log('开始下载 %d 个 deb（%d 线程）...' % (total, workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for s, safe in tasks:
            dest = os.path.join(dest_dir, safe)
            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                done += 1
                if progress:
                    progress(done, total, safe + ' (已存在)')
                continue
            fut = ex.submit(download_one, s.get('Filename', ''), dest, base, s.get('SHA256', ''))
            futs[fut] = safe
        for fut in as_completed(futs):
            name = futs[fut]
            ok, err = fut.result()
            done += 1
            if not ok:
                failed.append((name, err))
            if progress:
                progress(done, total, name + ('' if ok else ' [失败]'))
    log('下载完成：成功 %d，失败 %d' % (total - len(failed), len(failed)))
    return failed
