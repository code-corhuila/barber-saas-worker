FROM python:3.12.7-slim
WORKDIR /app
# Standard library only at runtime (ADR-012): nothing to install.
COPY src ./src
COPY apps ./apps
ENV PYTHONPATH=/app/src:/app PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "apps.worker"]
