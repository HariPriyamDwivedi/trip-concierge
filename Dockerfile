FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
# pytest is included so the test suite can run inside the image.
RUN pip install --no-cache-dir -r requirements.txt pytest

RUN useradd --create-home app && chown app /app
COPY --chown=app . .
USER app

EXPOSE 8000 8001
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
