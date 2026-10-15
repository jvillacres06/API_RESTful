# API RESTful para mantenimiento predictivo de bombas hidráulicas

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-Integración-660066)
![OPC UA](https://img.shields.io/badge/OPC%20UA-Integración-555555)

API desarrollada como parte de un proyecto académico de ingeniería para gestionar información del mantenimiento predictivo de bombas hidráulicas utilizadas en la producción de crudo. Centraliza datos de equipos, despliegues, mediciones y características, con integraciones industriales y consultas analíticas.

## Funcionalidades

- Gestión de activos, motores, variables, unidades y despliegues.
- Recepción y consulta de datos de mediciones.
- Soporte para registros de mediciones limpias y características.
- Rutas de análisis de mediciones, mediciones limpias y características.
- Integración mediante MQTT y OPC UA, sujeta a configuración.
- Documentación OpenAPI generada automáticamente por FastAPI.
- Protección mediante clave API en determinadas rutas.

> Este repositorio contiene la API. Para ponerla en marcha se necesitan una base de datos PostgreSQL compatible y los servicios externos configurados.

## Tecnologías

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy.
- **Base de datos:** PostgreSQL (psycopg2).
- **Comunicación industrial:** MQTT (paho-mqtt), OPC UA.
- **Servidor:** Uvicorn.

## Estructura del proyecto

```text
API_RESTful/
├── app/
│   ├── main.py            # Aplicación y registro de rutas
│   ├── config.py          # Configuración y variables de entorno
│   ├── database.py        # Conexión a PostgreSQL
│   ├── mqtt_client.py     # Cliente MQTT
│   ├── security.py        # Control de acceso por clave API
│   ├── models/            # Modelos de datos
│   ├── routers/           # Endpoints HTTP
│   ├── schemas/           # Esquemas de validación
│   └── services/          # Servicios e ingesta
└── requirements.txt
```

## Instalación y ejecución local

1. Clonar el repositorio:

```bash
git clone https://github.com/jvillacres06/API_RESTful.git
cd API_RESTful
```

2. Crear y activar un entorno virtual:

```bash
python -m venv .venv
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

3. Instalar dependencias:

```bash
python -m pip install fastapi "uvicorn[standard]" psycopg2-binary sqlalchemy pydantic python-dotenv "paho-mqtt==1.6.1" opcua pydantic-settings
```

> **Nota:** el archivo `requirements.txt` actual contiene comandos `pip install`, no el formato habitual de requisitos. Por eso, hasta corregirlo, se muestra arriba el comando de instalación equivalente.

4. Crear un archivo local `.env` con los datos de tu entorno. Ejemplo **sin credenciales reales**:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nombre_base_datos
DB_USER=usuario_local
DB_PASSWORD=tu_password
API_KEY=tu_clave_de_desarrollo

MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
OPCUA_ENDPOINT=opc.tcp://localhost:4840

OPCUA_INGEST_ENABLED=false
MQTT_INGEST_ENABLED=false
```

La base de datos debe contar con el esquema requerido por la aplicación. Además, el arranque conecta el cliente MQTT: configura un broker accesible antes de ejecutar el servicio.

5. Ejecutar desde la raíz:

```bash
uvicorn app.main:app --reload
```

La API se sirve por defecto en `http://127.0.0.1:8000`.

## Documentación de la API

Con el servicio iniciado:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Estado básico:** `GET /` devuelve `{"status":"ok"}`.

### Principales grupos de rutas

| Prefijo | Propósito |
|---|---|
| `/api/assets` | Gestión de activos |
| `/api/motores` | Gestión de motores |
| `/api/variables` | Variables registradas |
| `/api/unidades` | Unidades de medida |
| `/api/despliegues` | Despliegues de equipos |
| `/api/ingestas` | Ingesta de información |
| `/api/mediciones` | Mediciones |
| `/api/mediciones_limpias` | Mediciones procesadas |
| `/api/caracteristicas` | Características |
| `/api/indicador_calidad` | Indicadores de calidad |
| `/api/analytics` | Consultas analíticas |
| `/api/analytics_mediciones_limpias` | Análisis de datos limpios |
| `/api/analytics_caracteristicas` | Análisis de características |
| `/api/opcua` | Funcionalidades OPC UA |

Algunos grupos de rutas requieren una clave API. Revisa los parámetros, métodos y respuestas concretas en Swagger UI.

## Seguridad y configuración

- No publiques credenciales reales, certificados ni claves de producción.
- Mantén `.env` fuera de nuevos commits con `.gitignore`; si una credencial fue publicada, sustitúyela.
- Desactiva la ingesta industrial cuando no se utilice.
- Este repositorio está orientado a demostración y desarrollo académico; valida la configuración antes de exponerlo en Internet.

## Autor

**Jaime Marcelo Villacrés Espín**  
Ingeniero en Tecnologías de la Información — Universidad Técnica de Ambato, Ecuador.

[Perfil de GitHub](https://github.com/jvillacres06)
