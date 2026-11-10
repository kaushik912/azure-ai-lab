# Multi-stage, small, non-root. Built in Azure via `az acr build` (no local Docker).
FROM python:3.12-slim AS build
WORKDIR /w
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
RUN useradd -m -u 10001 app
COPY --from=build /install /usr/local
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
