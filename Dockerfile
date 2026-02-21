# Trading Bot — minimal production image
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Do not copy .env in image; mount at runtime
ENV PYTHONUNBUFFERED=1

# Default: run live (override with backtest)
CMD ["python", "main.py", "live"]
