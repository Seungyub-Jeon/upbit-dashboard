#!/bin/bash

# 스크립트 경로 확인
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 실행 중인 봇 프로세스 찾기
BOT_PID=$(pgrep -f "python src/main.py")

if [ -z "$BOT_PID" ]; then
    echo "⚠️ 실행 중인 봇을 찾을 수 없습니다!"
    exit 1
fi

# 봇 프로세스 종료
echo "🛑 봇 중지 중... (PID: $BOT_PID)"
kill "$BOT_PID"

# 종료 확인
sleep 2
if ! pgrep -f "python src/main.py" > /dev/null; then
    echo "✅ 봇이 성공적으로 종료되었습니다!"
else
    echo "⚠️ 봇 종료 실패! 강제 종료를 시도합니다..."
    kill -9 "$BOT_PID" 2>/dev/null
    sleep 1
    if ! pgrep -f "python src/main.py" > /dev/null; then
        echo "✅ 봇이 강제 종료되었습니다!"
    else
        echo "❌ 봇 종료에 실패했습니다. 수동으로 종료해주세요."
    fi
fi 