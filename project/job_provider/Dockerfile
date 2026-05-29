FROM python:3.11-slim

WORKDIR /project

RUN pip install pyzmq

COPY job_provider/ .

CMD ["python", "-u", "provider.py"]