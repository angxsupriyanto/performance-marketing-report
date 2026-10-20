FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generate_report.py apply_analysis.py dashboard_template.html ./
COPY profiles ./profiles
COPY service ./service

ARG REPORT_GENERATOR_VERSION=dev
ENV REPORT_GENERATOR_VERSION=${REPORT_GENERATOR_VERSION}

RUN useradd --system --uid 10001 --no-create-home report
USER report

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('PORT','8080'),timeout=4)"

CMD ["python", "-m", "service.server"]
