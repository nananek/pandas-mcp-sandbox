FROM python:3.12-slim

RUN useradd --create-home --uid 1000 sandbox
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
USER sandbox
EXPOSE 8080
CMD ["python", "-m", "pandas_table_sandbox"]
