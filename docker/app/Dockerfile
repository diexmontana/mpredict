# Imagen de mpredict: Python 3.12.4 (el de las fichas de los modelos) + modelos de Hugging Face.
FROM python:3.12.4-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf MPREDICT_DATOS=/datos

# git: clonar y leer el historial de los proyectos registrados
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch 2.15.0 en su versión para CPU (sin CUDA); después, el resto con las versiones exactas
COPY requirements.txt .
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# Modelos de Hugging Face: se descargan AL CONSTRUIR la imagen (no van en el repositorio)
COPY scripts/descargar_modelos.py scripts/descargar_modelos.py
RUN python scripts/descargar_modelos.py

# Aplicación: módulo de los modelos, modelos de tipo y tamaño, configuración y paquete mpredict
COPY maint_predict.py .
COPY modelos/ modelos/
COPY config/ config/
COPY mpredict/ mpredict/
COPY scripts/ scripts/

VOLUME ["/datos"]
EXPOSE 8600
CMD ["uvicorn", "mpredict.web.main:app", "--host", "0.0.0.0", "--port", "8600"]
