FROM python:bookworm
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ARG BOT_VERSION
ENV BOT_VERSION=$BOT_VERSION
CMD ["python", "bot.py"]
