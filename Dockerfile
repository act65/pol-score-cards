# Container for the public site. The site/ dir is self-contained (committed data,
# no API key needed), so we only need it in the image.
FROM python:3.12-slim
WORKDIR /app
COPY site/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY site/ .
ENV PORT=8080
EXPOSE 8080
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2
