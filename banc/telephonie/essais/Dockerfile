# Image des tests Python du fork, pour un poste sans Python 3.13.
#
# Elle part de l'image de l'API construite par le banc (mêmes bibliothèques que
# la production, mêmes versions) et n'ajoute que les outils de test, aux versions
# de la CI comparée (.github/workflows/mark-ci-comparee.yml).
#
# Le dépôt est monté dans /app au lancement : rien du code n'est copié ici, les
# tests voient toujours l'arbre de travail du moment.
ARG IMAGE_API=banc-telephonie-mark/api:local
FROM ${IMAGE_API}

USER root
RUN /opt/venv/bin/python -m ensurepip --upgrade > /dev/null 2>&1 || true ; \
    /opt/venv/bin/python -m pip install --no-cache-dir \
        pytest==9.1.1 pytest-asyncio==1.4.0 pytest-timeout==2.4.0 \
        mutmut==3.8.1 ruff==0.16.9
USER dograh

# L'image de l'API retire les dossiers « tests » des bibliothèques installées,
# dont pipecat.tests (les utilitaires de test de Pipecat). Le sous-module monté
# passe donc devant : c'est aussi ce que fait la CI, qui installe Pipecat depuis
# le sous-module.
ENV PYTHONPATH=/app/pipecat/src:/app \
    ENVIRONMENT=test \
    DEPLOYMENT_MODE=oss \
    LOG_LEVEL=INFO \
    ENABLE_AWS_S3=false \
    ENABLE_TELEMETRY=false \
    MINIO_PUBLIC_ENDPOINT=http://stockage-absent:9000

WORKDIR /app/api
CMD ["pytest", "--version"]
