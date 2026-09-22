#!/usr/bin/env bash
# 安全清理本地调试日志与临时评测产物（不触碰 git 跟踪文件与用户的真实翻译任务）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> Folith·译页 本地敏感日志与临时产物清理..."

# 1. 清理 tmp/ 下的临时运行日志与 probe 探针脚本
if [ -d "$ROOT/tmp" ]; then
    echo "清理 tmp/ 下的临时日志与探针..."
    rm -f "$ROOT"/tmp/*.log 2>/dev/null || true
    rm -f "$ROOT"/tmp/probe_*.py 2>/dev/null || true
fi

# 2. 清理回归 runner 历史残余失败记录
if [ -d "$ROOT/.regression-logs" ]; then
    echo "清理 .regression-logs/ 下的历史 tsv 记录..."
    rm -f "$ROOT"/.regression-logs/*.tsv 2>/dev/null || true
fi

# 3. 检查 outputs/ 目录下的凭据保护
if [ -f "$ROOT/outputs/provider_config.json" ]; then
    echo "[注意] outputs/provider_config.json 包含本地 API 密钥配置，已被 .gitignore 保护，请勿手动提交或外发。"
fi

# 4. 检查 outputs/ 下的真实任务目录
if [ -d "$ROOT/outputs" ]; then
    REAL_JOBS=$(find "$ROOT/outputs" -mindepth 1 -maxdepth 1 -type d ! -name "projects" -exec basename {} \;)
    if [ -n "$REAL_JOBS" ]; then
        echo "[提示] outputs/ 下存在本地任务：$REAL_JOBS"
        echo "       这些目录均被 .gitignore 忽略，不会进入 git 仓库。"
    fi
fi

echo "==> 清理完成！"
