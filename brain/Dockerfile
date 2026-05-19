FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    paho-mqtt \
    psycopg2-binary \
    joblib \
    numpy \
    scikit-learn==1.5.2

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
