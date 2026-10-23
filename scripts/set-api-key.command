#!/bin/bash
# 双击运行：把 DeepSeek API Key 安全写入本项目的 .env（权限 600，不回显、不进日志、不进 shell 历史）
set -u
cd "$(dirname "$0")" || exit 1
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo "找不到 .env，请确认本文件放在 resume-warehouse/ 根目录下。"
  read -r -n 1 -p "按任意键关闭…"; echo; exit 1
fi
echo "======================================================"
echo "  简历系统 · 配置 DeepSeek API Key"
echo "  粘贴后按回车，输入内容不会显示，也不会被记录"
echo "======================================================"
printf "请粘贴 API Key（sk- 开头）: "
IFS= read -r -s KEY
echo
case "$KEY" in
  sk-*) : ;;
  *) echo "✗ 这个值不是 sk- 开头，已取消，未做任何修改。"; read -r -n 1 -p "按任意键关闭…"; echo; exit 1 ;;
esac
if [ ${#KEY} -lt 20 ]; then
  echo "✗ key 太短，已取消，未做任何修改。"; read -r -n 1 -p "按任意键关闭…"; echo; exit 1
fi
TMP="$(mktemp)"
awk -v k="$KEY" '/^LLM_API_KEY=/{print "LLM_API_KEY=" k; found=1; next} {print} END{if(!found) print "LLM_API_KEY=" k}' "$ENV_FILE" > "$TMP"
mv "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"
KEY_LEN=${#KEY}
KEY_FP="$(printf '%s' "$KEY" | shasum -a 256 | cut -c1-8)"
unset KEY
echo "✓ 已写入 $PWD/.env（${KEY_LEN} 字符，指纹 ${KEY_FP}）"
echo "  指纹 = key 的 SHA-256 前 8 位，只用于核对「这次填的是不是原来那把」"
echo "  不含 key 的任何字符，截图或录屏都不会泄露"
read -r -n 1 -p "按任意键关闭这个窗口…"; echo
