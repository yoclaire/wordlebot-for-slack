FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py logic.py commentary.json supplemental.json ./

CMD ["python", "-u", "app.py"]
