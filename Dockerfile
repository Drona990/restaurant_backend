FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libpq-dev gcc netcat-traditional && \
    apt-get clean

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Folders for persistent data
RUN mkdir -p /app/logs /app/media /app/staticfiles
RUN touch /app/logs/django.log

COPY . .

# Permissions for Image uploads 8310267266 job 8971718072 techimaginia software
RUN chmod -R 755 /app/media /app/logs

EXPOSE 8000