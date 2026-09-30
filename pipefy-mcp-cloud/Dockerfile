FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --pre -r requirements.txt
COPY proxy.py run_server.py start.sh ./
RUN useradd -m app && chmod +x start.sh
USER app
EXPOSE 8080
CMD ["./start.sh"]
