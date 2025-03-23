#!/bin/bash

# 스크립트 경로 확인
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .zshrc 파일 위치
ZSHRC="$HOME/.zshrc"

# 추가할 aliases 내용
ALIASES=$(cat << EOF

# 업비트 트레이딩 봇 aliases
alias play="$PROJECT_ROOT/scripts/play.sh"
alias stop="$PROJECT_ROOT/scripts/stop.sh"
EOF
)

# .zshrc 파일에 aliases가 이미 있는지 확인
if grep -q "# 업비트 트레이딩 봇 aliases" "$ZSHRC"; then
    echo "⚠️ Aliases가 이미 .zshrc 파일에 있습니다!"
else
    # .zshrc 파일에 aliases 추가
    echo "$ALIASES" >> "$ZSHRC"
    echo "✅ Aliases가 .zshrc 파일에 추가되었습니다!"
    echo "새 터미널을 열거나 'source ~/.zshrc' 명령을 실행하여 aliases를 적용하세요."
fi 