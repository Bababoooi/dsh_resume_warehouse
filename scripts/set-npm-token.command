#!/bin/bash
# 双击运行：把新的 npm token 安全写入 ~/.npmrc
# - 输入不回显、不进 shell 历史
# - 只替换 //registry.npmjs.org/:_authToken= 这一行，其他配置原样保留
# - 写完立刻用 npm whoami 验证，并给出不可逆指纹（不打印 token 本体）

set +u
NPMRC="$HOME/.npmrc"

echo "=============================================="
echo " 写入 npm 发布令牌（只写本机 ~/.npmrc）"
echo "=============================================="
echo "请在下面粘贴 token（复制时前面不要带空格），回车确认："
printf 'npm token: '
IFS= read -rs TOKEN
echo
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"

case "$TOKEN" in
  npm_*) ;;
  *)
    echo "✗ 格式不对：npm token 以 npm_ 开头。已取消，未做任何修改。"
    exit 1
    ;;
esac

if [ "${#TOKEN}" -lt 20 ]; then
  echo "✗ 长度不对（${#TOKEN} 字符），像是没粘贴完整。已取消，未做任何修改。"
  exit 1
fi

FP="$(printf '%s' "$TOKEN" | shasum -a 256 | cut -c1-8)"

if [ -f "$NPMRC" ]; then
  BAK="$NPMRC.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$NPMRC" "$BAK"
  chmod 600 "$BAK"
  echo "· 已备份原配置到：${BAK}"
  TMP="$(mktemp)"
  grep -v '^//registry.npmjs.org/:_authToken=' "$NPMRC" > "$TMP" || true
  mv "$TMP" "$NPMRC"
else
  echo "· 之前没有 ~/.npmrc，将新建"
  : > "$NPMRC"
fi

printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" >> "$NPMRC"
chmod 600 "$NPMRC"

echo
echo "· 已写入 ${NPMRC} （权限 600，指纹 ${FP}）"
echo "· 正在验证身份……"
WHO="$(npm whoami 2>/dev/null || true)"
if [ -n "$WHO" ]; then
  echo "✓ 验证通过：npm 用户 = ${WHO}"
  echo
  echo "接下来告诉对话里的 agent「token 已写入，指纹 ${FP}」，它会用这份凭据发布。"
  echo "（发布完成后请到 npm 后台 revoke 掉这个 token）"
else
  echo "✗ npm whoami 失败：token 可能无效或已过期。已写入但请检查。"
  exit 1
fi
echo
printf '按任意键关闭窗口……'; read -n1 -s || true
