#!/bin/bash

# 프로젝트 디렉토리 생성 및 이동
mkdir -p /home/ubuntu/SyncTask
cd /home/ubuntu/SyncTask

# 가상환경 생성 및 의존성 설치
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ 서버 환경 설정 완료!"
echo "이제 .env 파일을 생성하고, synctask.service를 등록하세요."
