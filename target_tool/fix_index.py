#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 updata/Packages 的 Filename 修正为平铺文件名, 重建 Packages.gz 与 Release,
使 updata 目录成为可直接 apt file:// 使用的本地源。"""
import os, sys, gzip, hashlib

d = sys.argv[1] if len(sys.argv) > 1 else r'D:\DEBRNR\Desktop\deepin\updata'
pkg = os.path.join(d, 'Packages')

lines = []
fixed = 0
missing = []
for line in open(pkg, encoding='utf-8', errors='replace'):
    if line.startswith('Filename: '):
        fn = line[len('Filename: '):].strip()
        base = fn.split('/')[-1]
        if base != fn:
            fixed += 1
        if not os.path.exists(os.path.join(d, base)):
            missing.append(base)
        line = 'Filename: ' + base + '\n'
    lines.append(line)

out = ''.join(lines)
with open(pkg, 'w', encoding='utf-8', newline='\n') as f:
    f.write(out)

with open(pkg, 'rb') as fi, gzip.open(os.path.join(d, 'Packages.gz'), 'wb') as fo:
    fo.write(fi.read())

def digest(path, algo):
    h = hashlib.new(algo)
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

p_rel = 'Packages'
gz_rel = 'Packages.gz'
p_size = os.path.getsize(pkg)
gz_size = os.path.getsize(os.path.join(d, 'Packages.gz'))
rel = []
rel.append('Origin: deepin-offline-upgrade\n')
rel.append('Label: deepin-offline-upgrade\n')
rel.append('Suite: stable\n')
rel.append('Codename: offline\n')
rel.append('Architectures: loong64 all\n')
rel.append('Components: main\n')
rel.append('Description: Offline upgrade packages for deepin 25.3.0 loong64\n')
for algo in ('MD5Sum', 'SHA256'):
    rel.append(algo + ':\n')
    rel.append(' %s %d %s\n' % (digest(pkg, 'md5' if algo == 'MD5Sum' else 'sha256'), p_size, p_rel))
    rel.append(' %s %d %s\n' % (digest(os.path.join(d, 'Packages.gz'), 'md5' if algo == 'MD5Sum' else 'sha256'), gz_size, gz_rel))
with open(os.path.join(d, 'Release'), 'w', encoding='ascii', newline='\n') as f:
    f.write(''.join(rel))

print('fixed Filename lines:', fixed)
print('missing deb files:', len(missing))
for m in missing[:15]:
    print('  MISSING', m)
print('Packages size:', p_size, 'Packages.gz size:', gz_size)
