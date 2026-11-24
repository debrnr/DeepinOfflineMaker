#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成交付目录：修正本地源索引，拷入图形工具与说明，产出可直接拷U盘的文件夹。"""
import os, shutil, gzip, hashlib, datetime

def _digest(path, algo):
    h = hashlib.new(algo)
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def write_local_repo(updata_dir, stanzas, version_label='deepin 25.3.0 loong64'):
    """根据 stanzas 重建 Packages / Packages.gz / Release。
    Filename 全部写为平铺文件名，与下载时的命名一致。"""
    import re
    os.makedirs(updata_dir, exist_ok=True)
    lines = []
    for s in stanzas:
        fn = s.get('Filename', '')
        arch = s.get('Architecture', '')
        base_name = '%s_%s_%s.deb' % (re.sub(r'[^\w+.\-]', '_', s.get('Package', 'pkg')),
                                     re.sub(r'[^\w+.\-]', '_', s.get('Version', '0')),
                                     arch or 'all')
        for k, v in s.items():
            if k == 'Filename':
                continue
            lines.append('%s: %s\n' % (k, v))
        lines.append('Filename: %s\n' % base_name)
        lines.append('\n')
    pkg_path = os.path.join(updata_dir, 'Packages')
    with open(pkg_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(lines))
    gz_path = pkg_path + '.gz'
    with open(pkg_path, 'rb') as fi, gzip.open(gz_path, 'wb') as fo:
        fo.write(fi.read())

    p_size = os.path.getsize(pkg_path)
    gz_size = os.path.getsize(gz_path)
    date = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S UTC')
    rel = []
    rel.append('Origin: deepin-offline-upgrade\n')
    rel.append('Label: deepin-offline-upgrade\n')
    rel.append('Suite: stable\n')
    rel.append('Codename: offline\n')
    rel.append('Architectures: loong64 all\n')
    rel.append('Components: main\n')
    rel.append('Description: Offline upgrade packages for %s\n' % version_label)
    rel.append('Date: %s\n' % date)
    for algo in ('MD5Sum', 'SHA256'):
        rel.append(algo + ':\n')
        a = 'md5' if algo == 'MD5Sum' else 'sha256'
        rel.append(' %s %d %s\n' % (_digest(pkg_path, a), p_size, 'Packages'))
        rel.append(' %s %d %s\n' % (_digest(gz_path, a), gz_size, 'Packages.gz'))
    with open(os.path.join(updata_dir, 'Release'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(rel))
    return len(lines)


def build_delivery(out_dir, updata_dir, tool_deb_src, docs_src=None, soft_src=None,
                   readme_text=None, log=print):
    """组装交付目录：out_dir 下创建 updata / tool / docs，拷入所需文件。"""
    os.makedirs(out_dir, exist_ok=True)
    tool_dir = os.path.join(out_dir, 'tool')
    docs_dir = os.path.join(out_dir, 'docs')
    os.makedirs(tool_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    if tool_deb_src and os.path.isfile(tool_deb_src):
        shutil.copy2(tool_deb_src, os.path.join(tool_dir, os.path.basename(tool_deb_src)))
        log('已拷入图形工具: %s' % os.path.basename(tool_deb_src))
    if docs_src and os.path.isdir(docs_src):
        for fn in os.listdir(docs_src):
            fp = os.path.join(docs_src, fn)
            if os.path.isfile(fp):
                shutil.copy2(fp, os.path.join(docs_dir, fn))
    if soft_src and os.path.isdir(soft_src):
        dst = os.path.join(out_dir, 'soft')
        os.makedirs(dst, exist_ok=True)
        n = 0
        for fn in os.listdir(soft_src):
            fp = os.path.join(soft_src, fn)
            if os.path.isfile(fp):
                shutil.copy2(fp, os.path.join(dst, fn))
                n += 1
        log('已拷入软件目录: %d 个文件' % n)
    if readme_text:
        with open(os.path.join(out_dir, '使用说明.md'), 'w', encoding='utf-8') as f:
            f.write(readme_text)
    log('交付目录已生成: %s' % out_dir)
