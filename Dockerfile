FROM python:3.13-alpine

WORKDIR /app

COPY entrypoint.sh .
COPY pyproject.toml .
COPY gitea_mirror_manager/ ./gitea_mirror_manager
COPY README.md .
COPY requirements.txt .

RUN apk add --no-cache curl entr
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir .

CMD ["./entrypoint.sh"]