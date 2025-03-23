#!/bin/bash

# 스크립트 경로 확인
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 프로젝트 루트 디렉토리로 이동
cd "$PROJECT_ROOT" || exit

# 가상환경 확인 및 활성화
if [ -d "venv" ]; then
    echo "🚀 가상환경을 활성화합니다..."
    source venv/bin/activate
else
    echo "⚠️ 가상환경을 찾을 수 없습니다. 먼저 가상환경을 설정해주세요."
    exit 1
fi

# 이미 실행 중인 봇 확인
if pgrep -f "python src/main.py" > /dev/null; then
    echo "⚠️ 봇이 이미 실행 중입니다!"
    exit 0
fi

# 봇 실행
echo "🤖 업비트 트레이딩 봇 시작 중..."
python src/main.py > logs/bot_output.log 2>&1 &

# 실행된 프로세스 ID 확인
BOT_PID=$!
echo "✅ 봇이 성공적으로 시작되었습니다! (PID: $BOT_PID)"
echo "📊 대시보드에 접속하려면: http://localhost:8050"
echo "📝 로그를 확인하려면: tail -f logs/trading.log" 