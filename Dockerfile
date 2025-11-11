FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt
COPY . .
ENV PORT=10000
CMD gunicorn -w 1 -k sync -b 0.0.0.0:10000 app:app

