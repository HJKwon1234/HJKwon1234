# DDoS 모의 훈련 웹 모니터링 — 웹 UI
FROM python:3.12-slim

WORKDIR /app

# 의존성 먼저 (레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션
COPY web_monitor_drill.py monitor_service.py app.py sites.json ./
COPY templates/ ./templates/

ENV HOST=0.0.0.0 PORT=5000
EXPOSE 5000

CMD ["python", "app.py"]
