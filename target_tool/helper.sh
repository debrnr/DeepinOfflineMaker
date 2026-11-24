#!/bin/bash
# 离线工具 - root 辅助脚本 (由 pkexec 调用)
# 用法:
#   helper.sh upgrade <updata目录>
#   helper.sh install <软件主目录> [依赖目录 ...]
#   helper.sh printer <驱动目录> [依赖目录 ...] [-- 指定deb文件名 ...]
# 通过固定路径日志与状态文件同 GUI 通信。

ACTION="$1"
shift
ALL=("$@")
DIRS=()
SELECTED=()
sep=0
for a in "${ALL[@]}"; do
    if [ "$a" = "--" ]; then
        sep=1
        continue
    fi
    if [ "$sep" -eq 0 ]; then
        DIRS+=("$a")
    else
        SELECTED+=("$a")
    fi
done

LOG="/tmp/deepin-offline-upgrade-install.log"
STATUS="/tmp/deepin-offline-upgrade.status"
mkdir -p "$(dirname "$LOG")"
: > "$LOG"
echo RUNNING > "$STATUS"

say() {
    echo "$@"
    echo "$@" >> "$LOG"
}

fail() {
    say "[FAIL] $1"
    echo "FAIL:$2" > "$STATUS"
    exit "$2"
}

if [ "${#DIRS[@]}" -eq 0 ] || [ ! -d "${DIRS[0]}" ]; then
    fail "目录不存在: ${DIRS[0]}" 2
fi

DEBS=()
for d in "${DIRS[@]}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*.deb; do
        [ -f "$f" ] && DEBS+=("$f")
    done
done

if [ "${#SELECTED[@]}" -gt 0 ]; then
    FILTERED=()
    for f in "${DEBS[@]}"; do
        b=$(basename "$f")
        for s in "${SELECTED[@]}"; do
            if [ "$b" = "$s" ] || [ "$b" = "$s.deb" ] || [[ "$b" == "$s"_*.deb ]]; then
                FILTERED+=("$f")
                break
            fi
        done
    done
    DEBS=("${FILTERED[@]}")
fi

DEB_COUNT=${#DEBS[@]}
if [ "$DEB_COUNT" -eq 0 ]; then
    fail "没有匹配的 .deb 文件" 2
fi
say "[OK] 找到 $DEB_COUNT 个 deb，目录：${DIRS[*]}"

TMP=$(mktemp -d /tmp/offline-tool.XXXXXX)
SRCLIST="$TMP/sources.list"
: > "$SRCLIST"
for d in "${DIRS[@]}"; do
    [ -d "$d" ] || continue
    ENC_PATH=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$d")
    printf 'deb [trusted=yes] file://%s ./\n' "$ENC_PATH" >> "$SRCLIST"
done

APT_OPTS=(
  -o Dir::Etc::sourcelist="$SRCLIST"
  -o Dir::Etc::sourceparts="-"
  -o APT::Get::List-Cleanup="0"
  -o Acquire::Languages="none"
)
export DEBIAN_FRONTEND=noninteractive
export DEBCONF_NONINTERACTIVE_SEEN=true

if [ "$ACTION" = "upgrade" ]; then
    say "[OK] 刷新离线升级源索引 ..."
    apt-get "${APT_OPTS[@]}" update >> "$LOG" 2>&1
    say "[OK] 开始系统升级（可能数分钟，请勿关机）..."
    apt-get "${APT_OPTS[@]}" -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold" \
        full-upgrade >> "$LOG" 2>&1
    RC=$?
    if [ "$RC" -ne 0 ]; then
        say "[WARN] full-upgrade 返回 $RC，尝试直接安装 ..."
        apt-get "${APT_OPTS[@]}" -y \
            -o Dpkg::Options::="--force-confdef" \
            -o Dpkg::Options::="--force-confold" \
            install "${DEBS[@]}" >> "$LOG" 2>&1
        RC=$?
    fi
elif [ "$ACTION" = "install" ]; then
    say "[OK] 刷新软件源索引（软件目录 + 依赖目录）..."
    apt-get "${APT_OPTS[@]}" update >> "$LOG" 2>&1
    say "[OK] 开始安装软件及依赖 ..."
    apt-get "${APT_OPTS[@]}" -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold" \
        install "${DEBS[@]}" >> "$LOG" 2>&1
    RC=$?
elif [ "$ACTION" = "printer" ]; then
    say "[OK] 刷新打印机驱动源索引 ..."
    apt-get "${APT_OPTS[@]}" update >> "$LOG" 2>&1
    say "[OK] 开始安装打印机驱动及依赖 ..."
    apt-get "${APT_OPTS[@]}" -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold" \
        install "${DEBS[@]}" >> "$LOG" 2>&1
    RC=$?
    if [ "$RC" -eq 0 ]; then
        say "[OK] 重启 CUPS 打印服务 ..."
        systemctl enable cups >> "$LOG" 2>&1 || true
        systemctl restart cups >> "$LOG" 2>&1 || service cups restart >> "$LOG" 2>&1 || true
    fi
else
    fail "未知操作: $ACTION" 3
fi

rm -rf "$TMP"

if [ "$RC" -eq 0 ]; then
    say "[OK] 全部完成。"
    echo "OK" > "$STATUS"
    exit 0
else
    say "[FAIL] 返回码 $RC，可重新运行重试。已装好的更新依然有效。"
    echo "FAIL:$RC" > "$STATUS"
    exit "$RC"
fi
