# Sistema de Alertas de Soldadura

Aplicacion de monitoreo y alertas en tiempo real para una celda de soldadura.

El sistema actual incluye:

- `broker`: Mosquitto para recibir eventos MQTT.
- `db`: PostgreSQL para persistir estaciones, eventos y alertas.
- `cerebro`: servicio FastAPI que consume MQTT, genera alertas y sirve la interfaz web.
- `simulator.py`: simulador local que publica eventos al broker.

La interfaz principal queda disponible en `http://localhost:8000`.

## Requisitos del proyecto

- Docker con soporte para `docker compose`
- Python 3.10 o superior
- `uv` para crear el entorno virtual del simulador

## Estructura rapida

```text
docker-compose.yml   -> infraestructura principal
.env                 -> variables locales del proyecto
.env.example         -> plantilla de variables
brain/               -> servicio web y logica de alertas
simulator.py         -> emisor de eventos de prueba
db_init/init.sql     -> inicializacion de la base de datos
```

## 1. Instalacion en Linux

Estas instrucciones estan pensadas para Ubuntu 24.04 o 22.04.

### 1.1 Instalar Docker Engine y Docker Compose

Docker recomienda instalar Engine y el plugin de Compose desde su repositorio oficial:

Referencia oficial:
- https://docs.docker.com/engine/install/ubuntu/
- https://docs.docker.com/compose/install/

Ejecuta:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Valida la instalacion:

```bash
docker --version
docker compose version
sudo docker run hello-world
```

Opcional, para no usar `sudo` con Docker:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### 1.2 Instalar Python y uv

Referencia oficial de `uv`:
- https://docs.astral.sh/uv/getting-started/installation/

Primero valida Python:

```bash
python3 --version
```

Si no lo tienes:

```bash
sudo apt update
sudo apt install -y python3 python3-venv
```

Instala `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Recarga la sesion si el comando no aparece inmediatamente:

```bash
source ~/.bashrc
```

Valida:

```bash
uv --version
```

## 2. Instalacion en Windows

Estas instrucciones estan pensadas para Windows 10/11 con Docker Desktop.

### 2.1 Instalar Docker Desktop

Referencias oficiales:
- https://docs.docker.com/desktop/setup/install/windows-install/
- https://docs.docker.com/compose/install/

Pasos:

1. Instala o actualiza WSL si aun no lo tienes:

```powershell
wsl --install
wsl --update
```

2. Descarga e instala Docker Desktop desde la documentacion oficial.
3. Durante la instalacion, deja habilitada la opcion de backend `WSL 2`.
4. Abre Docker Desktop y espera a que quede en estado listo.

Valida en PowerShell:

```powershell
docker --version
docker compose version
docker run hello-world
```

### 2.2 Instalar Python y uv

Referencia oficial de `uv`:
- https://docs.astral.sh/uv/getting-started/installation/

Instala Python 3.10 o superior si aun no lo tienes.

Valida:

```powershell
python --version
```

Instala `uv` en PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Cierra y abre la terminal si `uv` no aparece de inmediato.

Valida:

```powershell
uv --version
```

## 3. Clonar el proyecto

```bash
git clone <URL_DEL_REPOSITORIO>
cd copate-26
```

En Windows, si usas PowerShell:

```powershell
git clone <URL_DEL_REPOSITORIO>
cd copate-26
```

## 4. Configurar variables de entorno

Crea tu archivo local a partir de la plantilla:

Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Variables actuales:

```env
POSTGRES_USER=admin
POSTGRES_PASSWORD=cambia_esta_password
POSTGRES_DB=soldadura_db
LINE_ID=linea1
LINE_LABEL=Control de linea 1
OPERATOR_NAME=Operador 01
OPERATOR_LINE_LABEL=Linea de soldadura alfa
```

`docker compose` leerá automaticamente este `.env` cuando levantes el proyecto.

## 5. Levantar la infraestructura

Desde la raiz del repositorio:

```bash
docker compose up --build -d
```

Valida que todo este arriba:

```bash
docker compose ps
```

Servicios esperados:

- `broker`
- `db`
- `cerebro`

Ver logs:

```bash
docker compose logs -f broker db cerebro
```

## 6. Preparar el entorno Python del simulador

El simulador se ejecuta fuera de Docker y publica eventos a `localhost:1883`.

### Linux

```bash
uv venv
source .venv/bin/activate
uv pip install paho-mqtt
```

### Windows PowerShell

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv pip install paho-mqtt
```

Si PowerShell bloquea la activacion:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\Activate.ps1
```

## 7. Ejecutar el sistema

### 7.1 Abrir la interfaz

Con Docker ya levantado, abre:

```text
http://localhost:8000
```

### 7.2 Ejecutar el simulador

Con el entorno virtual activo:

Linux:

```bash
python3 simulator.py
```

Windows:

```powershell
python simulator.py
```

El simulador enviara soldaduras al broker MQTT y la interfaz empezara a reflejar actividad, logs y alertas.

## 8. Comandos utiles

Levantar o reconstruir:

```bash
docker compose up --build -d
```

Detener:

```bash
docker compose down
```

Ver estado:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f broker db cerebro
```

Reiniciar solo el backend:

```bash
docker compose restart cerebro
```

## 9. Verificaciones rapidas

Si todo esta bien:

- `docker compose ps` muestra `broker`, `db` y `cerebro` en estado `Up`
- `http://localhost:8000` carga la interfaz
- `python simulator.py` publica eventos sin errores de conexion

## 10. Solucion de problemas

### Docker no arranca

Linux:

```bash
sudo systemctl status docker
sudo systemctl start docker
```

Windows:
- abre Docker Desktop y espera a que termine de iniciar
- valida que WSL 2 este habilitado

### `docker compose` no existe

Valida:

```bash
docker compose version
```

Si falla en Linux, normalmente falta el paquete `docker-compose-plugin`.

### Error de permisos con Docker en Linux

Usa temporalmente:

```bash
sudo docker compose ps
```

Y luego agrega tu usuario al grupo `docker`:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### El simulador no conecta al broker

Revisa que Docker este arriba y el puerto `1883` expuesto:

```bash
docker compose ps
docker compose logs --tail=100 broker
```

### El puerto 8000 o 5432 ya esta ocupado

Busca que otro proceso usa el puerto o cambia el mapeo en `docker-compose.yml`.

### La UI abre pero no hay datos

Verifica:

```bash
docker compose logs --tail=100 cerebro
```

Y luego ejecuta el simulador.

## 11. Resetear el entorno local

Detener contenedores:

```bash
docker compose down
```

Borrar volumen de Postgres y recrear desde cero:

```bash
docker compose down -v
docker compose up --build -d
```

Esto elimina la base de datos local del proyecto.

## 12. Notas del proyecto

- La UI principal ya no depende de Grafana.
- El sistema esta pensado para funcionar hoy con simulador y despues con una fuente real tipo PLC.
- El servicio `cerebro` ya normaliza eventos por estacion y guarda alertas en PostgreSQL.

## 13. Referencias oficiales usadas para esta guia

- Docker Engine en Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Docker Compose: https://docs.docker.com/compose/install/
- Docker Desktop en Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- uv: https://docs.astral.sh/uv/getting-started/installation/
