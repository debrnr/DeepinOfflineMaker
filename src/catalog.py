#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""软件目录聚合：内置精选 + 星火商店 loong64 + deepin 官方源精选。

所有来源统一成同一个 item 结构，供 Windows 图形界面勾选、供 pipeline 下载：
  id       唯一标识（内置项直接用旧 id，保持 manifest 兼容）
  name     显示名
  cat      中文分类
  desc     说明
  source   builtin | spark | apt
  pkgs     需要下载的 apt 包名列表（builtin/apt 用）
  deb_url  deb 直链（spark / loongapps 用）
  deb_file 本地文件名（spark / loongapps 用）
  version / size / update / tags   展示信息
"""
import os, re, io, gzip, json, tarfile, urllib.parse, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SPARK_BASE = 'https://cdn.d.store.deepinos.org.cn'
SPARK_ROOT = 'loong64-store'

# 星火商店分类目录 -> 中文显示名（已确认 loong64-store 全部存在）
SPARK_CATS = [
    ('office', '办公'), ('tools', '系统工具'), ('development', '编程开发'),
    ('network', '网络应用'), ('chat', '社交沟通'), ('music', '音乐欣赏'),
    ('video', '视频播放'), ('image_graphics', '图形图像'), ('games', '游戏娱乐'),
    ('reading', '阅读翻译'), ('themes', '主题美化'), ('others', '其它'),
]

CAT_LABELS = dict(SPARK_CATS)
SOURCE_LABELS = {'builtin': '内置精选', 'spark': '星火商店', 'apt': 'deepin源'}


# --------------------------------------------------------------------------
# 内置精选（离线永远可用）
# --------------------------------------------------------------------------
def builtin_items():
    import software_list
    out = []
    for s in software_list.SOFTWARE:
        out.append({
            'id': s['id'], 'name': s['name'], 'cat': s['cat'], 'desc': s['desc'],
            'source': 'builtin', 'pkgs': list(s.get('pkgs') or []),
            'deb_url': software_list.WPS_DIRECT_URL if s.get('source') == 'loongapps' else '',
            'deb_file': s.get('deb') or '',
            'version': '', 'size': '约 790MB' if s.get('source') == 'loongapps' else '',
            'update': '', 'tags': '',
        })
    return out


# --------------------------------------------------------------------------
# 星火商店 loong64 目录
# --------------------------------------------------------------------------
def _get_json(url, timeout=40):
    from repo import _urlopen
    with _urlopen(url, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw.decode('utf-8', errors='replace'))


def _short_desc(app):
    bits = []
    if app.get('Version'):
        bits.append('版本 ' + str(app['Version']))
    if app.get('Size'):
        bits.append(str(app['Size']))
    if app.get('Update'):
        bits.append('更新 ' + str(app['Update'])[:10])
    more = str(app.get('More') or '').replace('\r', ' ').replace('\n', ' ').strip()
    more = re.sub(r'\s+', ' ', more)[:90]
    return ' · '.join(bits) + ('　' + more if more else '')


def _fetch_one_cat(code, label, log):
    url = '%s/%s/%s/applist.json' % (SPARK_BASE, SPARK_ROOT, code)
    try:
        data = _get_json(url)
    except Exception as e:
        log('  [警告] 星火分类 %s 获取失败: %s' % (label, e))
        return []
    items = []
    for app in data:
        pkg = str(app.get('Pkgname') or '').strip()
        fn = str(app.get('Filename') or '').strip()
        if not pkg or not fn:
            continue
        items.append({
            'id': 'spark:%s:%s' % (code, pkg),
            'name': str(app.get('Name') or pkg),
            'cat': label,
            'desc': _short_desc(app),
            'source': 'spark',
            'pkgs': [],
            'deb_url': '%s/%s/%s/%s/%s' % (
                SPARK_BASE, SPARK_ROOT, code,
                urllib.parse.quote(pkg), urllib.parse.quote(fn)),
            'deb_file': fn,
            'version': str(app.get('Version') or ''),
            'size': str(app.get('Size') or ''),
            'update': str(app.get('Update') or ''),
            'tags': str(app.get('Tags') or ''),
        })
    log('  星火 %s: %d 个应用' % (label, len(items)))
    return items


def fetch_spark(log=print):
    """并发抓取星火商店 loong64 全部 12 类应用目录。"""
    log('从星火商店抓取 loong64 软件目录（12 个分类）...')
    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch_one_cat, code, label, log) for code, label in SPARK_CATS]
        for fut in as_completed(futs):
            try:
                out.extend(fut.result())
            except Exception as e:
                log('  [警告] 分类抓取异常: %s' % e)
    # 按分类固定顺序、名称排序，界面更稳定
    order = {label: i for i, (_, label) in enumerate(SPARK_CATS)}
    out.sort(key=lambda x: (order.get(x['cat'], 99), x['name']))
    log('星火商店 loong64 目录共 %d 个应用' % len(out))
    return out


# --------------------------------------------------------------------------
# deepin 官方源精选（可选，数量多）
# --------------------------------------------------------------------------
APT_SECTIONS = {
    'office': '办公', 'editors': '办公', 'net': '网络应用', 'utils': '系统工具',
    'graphics': '图形图像', 'multimedia': '影音', 'fonts': '字体',
    'communication': '社交沟通', 'science': '科学教育', 'text': '文本',
    'web': '网络应用', 'database': '开发工具',
}
APT_KEYWORDS = (
    'wps', 'libreoffice', 'firefox', 'chrome', 'chromium', 'thunderbird',
    'filezilla', 'ftp', 'pdf', 'reader', 'compress', 'zip', 'rar', '7z',
    'gimp', 'inkscape', 'okular', 'evince', 'qpdfview', 'vim', 'emacs',
    'code', 'git', 'python3', 'syncthing', 'transmission', 'qbittorrent',
    'vlc', 'mpv', 'obs', 'audacity', 'screenshot', 'flameshot',
)


def apt_items(repo, limit=400, log=print):
    """从已加载的 deepin 源 Packages 索引里挑出面向用户的软件。"""
    picked = {}
    for s in repo.index.values():
        name = s.get('Package', '')
        arch = s.get('Architecture', '')
        if not name or arch not in ('loong64', 'all'):
            continue
        if name.endswith(('-dbg', '-dev', '-doc', '-data', '-common', '-i18n', '-l10n')):
            continue
        sec = s.get('Section', '')
        cat = APT_SECTIONS.get(sec)
        hit = any(k in name.lower() for k in APT_KEYWORDS)
        if not cat and not hit:
            continue
        desc = s.get('Description', '') or ''
        if not desc:
            continue
        short = desc.split(' - ', 1)[0]
        picked[name] = {
            'id': 'apt:' + name,
            'name': short or name,
            'cat': cat or '实用工具',
            'desc': '%s · 版本 %s · %s' % (name, s.get('Version', ''), desc[:100]),
            'source': 'apt',
            'pkgs': [name],
            'deb_url': '', 'deb_file': '',
            'version': s.get('Version', ''), 'size': s.get('Size', ''),
            'update': '', 'tags': sec,
        }
    items = [picked[k] for k in sorted(picked)][:limit]
    log('deepin 官方源目录精选 %d 个应用（共命中 %d）' % (len(items), len(picked)))
    return items


# --------------------------------------------------------------------------
# 缓存 / 过滤
# --------------------------------------------------------------------------
def cache_path(cache_dir):
    return os.path.join(cache_dir or '.', 'catalog-spark.json')


def save_cache(items, cache_dir):
    os.makedirs(cache_dir or '.', exist_ok=True)
    data = {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'count': len(items), 'items': items,
    }
    with open(cache_path(cache_dir), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_cache(cache_dir):
    p = cache_path(cache_dir)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def load_catalog(cache_dir, sources=('builtin', 'spark'), refresh=False, log=print, repo=None):
    """组装目录。sources 可取 builtin / spark / apt。"""
    items = builtin_items()
    if 'spark' in sources:
        cached = load_cache(cache_dir)
        spark = None
        if refresh:
            try:
                spark = fetch_spark(log)
                save_cache(spark, cache_dir)
            except Exception as e:
                log('刷新星火目录失败，改用缓存: %s' % e)
        if spark is None:
            if cached and cached.get('items'):
                spark = cached['items']
                log('使用缓存的星火目录（%s，%d 个应用）' % (cached.get('generated', '?'), len(spark)))
            elif refresh:
                spark = []
        if spark:
            have = {x['id'] for x in items}
            items.extend(x for x in spark if x['id'] not in have)
    if 'apt' in sources and repo is not None:
        try:
            have = {x['id'] for x in items}
            items.extend(x for x in apt_items(repo, log=log) if x['id'] not in have)
        except Exception as e:
            log('官方源目录加载失败: %s' % e)
    return items


def filter_items(items, keyword='', cat='', source=''):
    kw = (keyword or '').strip().lower()
    out = []
    for it in items:
        if source and it.get('source') != source:
            continue
        if cat and it.get('cat') != cat:
            continue
        if kw:
            hay = ' '.join(str(it.get(k) or '') for k in
                           ('name', 'desc', 'cat', 'version', 'tags', 'id')).lower()
            if kw not in hay:
                continue
        out.append(it)
    return out


# --------------------------------------------------------------------------
# 下载直链 + 读取 deb 依赖（标准库即可，不依赖目标机 ar/dpkg）
# --------------------------------------------------------------------------
def download_direct(url, dest, log=print):
    from repo import _urlopen
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    tmp = dest + '.part'
    with _urlopen(url, timeout=300) as r, open(tmp, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(tmp, dest)
    return dest


def _ar_members(path):
    """极小 ar 读取器：yield (成员名, bytes)。deb 成员名都是短名。"""
    with open(path, 'rb') as f:
        if f.read(8) != b'!<arch>\n':
            return
        while True:
            hdr = f.read(60)
            if len(hdr) < 60:
                return
            name = hdr[:16].decode('ascii', errors='replace').strip().rstrip('/')
            try:
                size = int(hdr[48:58].decode('ascii', errors='replace').strip())
            except ValueError:
                return
            data = f.read(size)
            if size % 2:
                f.read(1)
            yield name, data


def read_deb_fields(path):
    """读取 deb 内 control 字段，返回 dict（含 Depends）。失败返回 {}。"""
    try:
        for name, data in _ar_members(path):
            if name not in ('control.tar.gz', 'control.tar.xz', 'control.tar.zst'):
                continue
            if name.endswith('.gz'):
                raw = gzip.decompress(data)
            elif name.endswith('.xz'):
                import lzma
                raw = lzma.decompress(data)
            else:
                return {}
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tf:
                for m in tf.getmembers():
                    if os.path.basename(m.name) != 'control':
                        continue
                    txt = tf.extractfile(m).read().decode('utf-8', errors='replace')
                    fields, last = {}, None
                    for line in txt.splitlines():
                        if line.startswith((' ', '\t')) and last:
                            fields[last] += ' ' + line.strip()
                        elif ':' in line:
                            k, v = line.split(':', 1)
                            fields[k.strip()] = v.strip()
                            last = k.strip()
                    return fields
    except Exception:
        return {}
    return {}


def deb_depends(path):
    return read_deb_fields(path).get('Depends', '')


def item_to_manifest(it):
    """写入目标机 manifest.json 的条目（保持旧字段，附加来源与安装提示）。"""
    return {
        'id': it.get('id', ''), 'name': it.get('name', ''),
        'cat': it.get('cat', ''), 'desc': it.get('desc', ''),
        'source': it.get('source', ''), 'version': it.get('version', ''),
        'size': it.get('size', ''),
        'deb_file': it.get('deb_file', ''),
        'pkgs': list(it.get('pkgs') or []),
        'driver_type': it.get('driver_type', ''),
        'match': list(it.get('match') or []),
    }
