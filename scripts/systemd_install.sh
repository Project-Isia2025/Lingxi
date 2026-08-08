#!/usr/bin/env bash
# Linux systemd 安装脚本
# 用法: sudo bash scripts/systemd_install.sh [--check]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/deploy/systemd/ai-agent-matrix.service"
ENV_EXAMPLE="$ROOT/deploy/systemd/env.example"
UNIT_DST="/etc/systemd/system/ai-agent-matrix.service"
ENV_DST="/etc/ai-agent-matrix/env"
LOG_DIR="/var/log/ai-agent-matrix"

if [[ "${1:-}" == "--check" ]]; then
  echo "unit_template: $([ -f "$UNIT_SRC" ] && echo OK || echo MISSING)"
  echo "env_example: $([ -f "$ENV_EXAMPLE" ] && echo OK || echo MISSING)"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active ai-agent-matrix.service 2>/dev/null || true
    systemctl is-enabled ai-agent-matrix.service 2>/dev/null || true
  fi
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 sudo 运行: sudo bash scripts/systemd_install.sh" >&2
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "缺少 unit 文件: $UNIT_SRC" >&2
  exit 1
fi

install -d -m 0755 /etc/ai-agent-matrix "$LOG_DIR"
if [[ ! -f "$ENV_DST" ]]; then
  install -m 0640 "$ENV_EXAMPLE" "$ENV_DST"
  echo "已创建 $ENV_DST，请编辑后重启服务"
fi

sed "s|WorkingDirectory=/opt/ai-agent-matrix|WorkingDirectory=$ROOT|g" "$UNIT_SRC" > "$UNIT_DST"
systemctl daemon-reload
systemctl enable ai-agent-matrix.service
echo "已安装 systemd 单元: ai-agent-matrix.service"
echo "  启动: sudo systemctl start ai-agent-matrix"
echo "  状态: sudo systemctl status ai-agent-matrix"
echo "  日志: sudo journalctl -u ai-agent-matrix -f"
