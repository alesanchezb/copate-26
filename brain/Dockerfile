# 1. Usar una imagen de Python ligera
FROM python:3.10-slim

# 2. Crear una carpeta de trabajo dentro del contenedor
WORKDIR /app

# 3. Instalar las librerías necesarias
RUN pip install --no-cache-dir fastapi uvicorn paho-mqtt psycopg2-binary

# 4. Copiar nuestro código al contenedor
COPY main.py .

# 5. Comando para arrancar el cerebro
CMD ["python", "main.py"]
