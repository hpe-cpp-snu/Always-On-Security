FROM python:3.12-slim

WORKDIR /project

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY node/ .

CMD ["python", "-u", "node_agent.py"]